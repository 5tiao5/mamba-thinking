from __future__ import annotations

import itertools
import os
from typing import Dict, Tuple

from observability import StageTimer, record_decision, record_graph_event, record_tool_event
from pipeline_utils import (
    balanced_fallback_pairs,
    balanced_mode,
    canonical,
    keyword_overlap,
    order_by_date,
)
from product_agent.services.relationship_evidence_service import RelationshipEvidenceService
from product_agent.services.fulltext_relationship_service import FullTextRelationshipService

from ..models import EvolutionEdge, PaperNode, ResearchState


OVERLAP_THRESHOLD = 0.40
EXPLICIT_REFERENCE_CONFIDENCE = 1.0
MAX_SIMILARITY_CONFIDENCE = 0.69
MAX_FALLBACK_CONFIDENCE = 0.39


def _similarity_confidence(*, overlap: float, same_category: bool) -> float:
    """Return a bounded heuristic score, not a calibrated probability."""
    score = 0.35 + (overlap * 0.35) + (0.08 if same_category else 0.0)
    return round(min(MAX_SIMILARITY_CONFIDENCE, score), 3)


def _fallback_confidence(overlap: float) -> float:
    return round(min(MAX_FALLBACK_CONFIDENCE, 0.2 + (overlap * 0.3)), 3)


def evolution_node(state: ResearchState) -> ResearchState:
    """根据引用、taxonomy 和关键词重叠构建论文演进图。"""

    papers = state.get("paper_nodes", {})
    edges: Dict[Tuple[str, str], EvolutionEdge] = {}
    evidence_service = RelationshipEvidenceService()
    paper_lookup: Dict[str, PaperNode] = dict(papers)
    for paper in papers.values():
        paper_lookup.setdefault(paper.paper_id, paper)
        if paper.doi:
            paper_lookup.setdefault(paper.doi, paper)

    for paper in papers.values():
        for ref_id in paper.references:
            ref_paper = paper_lookup.get(ref_id)
            if ref_paper and ref_paper.paper_id != paper.paper_id:
                edges[(ref_paper.paper_id, paper.paper_id)] = EvolutionEdge(
                    source=ref_paper.paper_id,
                    target=paper.paper_id,
                    relationship="citation",
                    reasoning=(
                        "The target paper's reference metadata explicitly contains "
                        "the source paper identifier. The arrow follows knowledge flow "
                        "from the cited predecessor to the citing successor."
                    ),
                    weight=EXPLICIT_REFERENCE_CONFIDENCE,
                    evidence="Explicit reference metadata.",
                    provenance="explicit_reference",
                    confidence=EXPLICIT_REFERENCE_CONFIDENCE,
                    evidence_level="confirmed",
                    evidence_snippets=[
                        f"{paper.title or paper.paper_id} references {ref_paper.title or ref_paper.paper_id}."
                    ],
                )
                record_graph_event(
                    state,
                    event_type="reference_edge",
                    source=ref_paper.paper_id,
                    target=paper.paper_id,
                    relationship=edges[(ref_paper.paper_id, paper.paper_id)].relationship,
                    reason="Created from explicit reference metadata.",
                    score=1.0,
                )

    for left, right in itertools.combinations(papers.values(), 2):
        older, newer = order_by_date(left, right)
        if older.paper_id == newer.paper_id:
            continue
        pair = (older.paper_id, newer.paper_id)
        if pair in edges:
            continue
        inferred_edge = evidence_service.infer_landscape_edge(older, newer)
        if inferred_edge is None:
            continue
        edges[pair] = inferred_edge
        record_graph_event(
            state,
            event_type="landscape_relation",
            source=inferred_edge.source,
            target=inferred_edge.target,
            relationship=inferred_edge.relationship,
            reason=inferred_edge.reasoning,
            score=inferred_edge.confidence,
        )

    for left, right in itertools.permutations(papers.values(), 2):
        if left.paper_id == right.paper_id:
            continue
        older, newer = order_by_date(left, right)
        if older.paper_id == newer.paper_id or (older.paper_id, newer.paper_id) in edges:
            continue
        shared_expert_branches = set(left.expert_taxonomy_branches) & set(
            right.expert_taxonomy_branches
        )
        same_source_category = canonical(left.taxonomy_category) and (
            canonical(left.taxonomy_category) == canonical(right.taxonomy_category)
        )
        same_category = bool(shared_expert_branches) or bool(same_source_category)
        overlap = keyword_overlap(left, right)
        if same_category or overlap >= OVERLAP_THRESHOLD:
            edges[(older.paper_id, newer.paper_id)] = EvolutionEdge(
                source=older.paper_id,
                target=newer.paper_id,
                relationship="related",
                reasoning=(
                    "Candidate thematic connection only: papers share a taxonomy "
                    f"branch or keywords; keyword_overlap={overlap:.2f}. "
                    "This does not establish citation, extension, or improvement."
                ),
                weight=_similarity_confidence(overlap=overlap, same_category=bool(same_category)),
                evidence=(
                    "Shared taxonomy branch and/or lexical overlap; no direct "
                    "relationship evidence has been verified."
                ),
                provenance="taxonomy_similarity" if same_category else "keyword_similarity",
                confidence=_similarity_confidence(
                    overlap=overlap,
                    same_category=bool(same_category),
                ),
                evidence_level="inferred",
                evidence_snippets=[
                    f"keyword_overlap={overlap:.2f}",
                    f"shared_expert_taxonomy={', '.join(sorted(shared_expert_branches)) or 'none'}",
                    f"same_source_category={bool(same_source_category)}",
                ],
            )
            record_graph_event(
                state,
                event_type="similarity_edge",
                source=older.paper_id,
                target=newer.paper_id,
                relationship=edges[(older.paper_id, newer.paper_id)].relationship,
                reason="Created from same category or keyword overlap.",
                score=overlap,
            )

    if balanced_mode(state) and not edges:
        fallback_pairs = balanced_fallback_pairs(list(papers.values()), state.get("topic", ""))
        for source, target, overlap in fallback_pairs:
            edges[(source.paper_id, target.paper_id)] = EvolutionEdge(
                source=source.paper_id,
                target=target.paper_id,
                relationship="related",
                reasoning=(
                    "Weak candidate connection: reference metadata was unavailable, "
                    "so the pair was selected from topic relevance, shared keywords, "
                    f"and publication order; weak_overlap={overlap:.2f}. "
                    "This edge must not be read as a verified evolution claim."
                ),
                weight=_fallback_confidence(overlap),
                evidence="Fallback similarity signal without direct relationship evidence.",
                provenance="balanced_fallback",
                confidence=_fallback_confidence(overlap),
                evidence_level="candidate",
                evidence_snippets=[f"weak_overlap={overlap:.2f}"],
            )
            record_graph_event(
                state,
                event_type="balanced_fallback_edge",
                source=source.paper_id,
                target=target.paper_id,
                relationship=edges[(source.paper_id, target.paper_id)].relationship,
                reason="No reference edges available; inferred from topic relevance and publication order.",
                score=overlap,
            )
        if fallback_pairs:
            record_decision(
                state,
                stage="evolution",
                decision="Added balanced-mode weak inferred edges.",
                reason="ArXiv metadata often lacks references; an empty graph would hide state flow.",
                next_step="auditor",
            )

    sparse_edges = _sparsify_candidate_edges(papers, list(edges.values()))
    verified_edges = evidence_service.verify(papers, sparse_edges)
    fulltext_limit = _fulltext_verification_limit(state)
    if fulltext_limit > 0:
        with StageTimer() as timer:
            fulltext_result = FullTextRelationshipService().verify(
                papers,
                verified_edges,
                max_edges=fulltext_limit,
            )
        verified_edges = fulltext_result.edges
        record_tool_event(
            state,
            tool_name="Open Full-text Relationship Verifier",
            input_summary=(
                f"citation_edges={fulltext_result.attempted_edges}; "
                f"max_edges={fulltext_limit}"
            ),
            status=(
                "success"
                if fulltext_result.upgraded_edges
                else (
                    "fallback"
                    if fulltext_result.attempted_edges
                    else "skipped"
                )
            ),
            output_count=fulltext_result.upgraded_edges,
            duration_sec=timer.elapsed(),
            note=(
                f"resolved_papers={fulltext_result.resolved_papers}; "
                f"parsed_documents={fulltext_result.parsed_documents}; "
                f"failures={fulltext_result.failures}"
            ),
        )
    updated = dict(state)
    updated["evolution_graph"] = verified_edges
    record_decision(
        updated,
        stage="evolution",
        decision=f"Built and verified graph with {len(verified_edges)} edges.",
        reason=(
            "Candidate edges come from references or similarity, then a separate "
            "evidence service upgrades only directly supported semantic claims."
        ),
        next_step="auditor",
    )
    updated.setdefault("logs", []).append(
        f"Evolution graph built and evidence-verified with {len(verified_edges)} edges."
    )
    return updated


def _fulltext_verification_limit(state: ResearchState) -> int:
    if os.environ.get("FULLTEXT_RELATIONSHIP_VERIFICATION", "1") == "0":
        return 0
    mode = str(state.get("mode", "default") or "default").strip().lower()
    if mode == "fast":
        return 0
    configured = os.environ.get("FULLTEXT_RELATIONSHIP_MAX_EDGES", "").strip()
    if configured:
        try:
            return max(0, int(configured))
        except ValueError:
            pass
    return 1 if mode == "balanced" else 2


def _sparsify_candidate_edges(
    papers: Dict[str, PaperNode],
    edges: list[EvolutionEdge],
) -> list[EvolutionEdge]:
    """Keep every explicit citation while limiting similarity hairballs.

    A dense all-to-all similarity graph looks authoritative but communicates
    very little. Two strongest inferred neighbors per paper are enough to show
    the local thematic backbone; direct reference edges are never discarded.
    """

    explicit = [edge for edge in edges if edge.provenance == "explicit_reference"]
    inferred = sorted(
        (edge for edge in edges if edge.provenance != "explicit_reference"),
        key=lambda edge: (float(edge.confidence or edge.weight or 0.0), edge.source, edge.target),
        reverse=True,
    )
    degree: Dict[str, int] = {paper_id: 0 for paper_id in papers}
    for edge in explicit:
        degree[edge.source] = degree.get(edge.source, 0) + 1
        degree[edge.target] = degree.get(edge.target, 0) + 1

    selected: list[EvolutionEdge] = []
    max_inferred_edges = max(len(papers), 1)
    relationship_caps = {
        "addresses": 3,
        "scope_extension": 3,
        "complements": 2,
        "related": 2,
    }
    relationship_counts: Dict[str, int] = {}
    for edge in inferred:
        if len(selected) >= max_inferred_edges:
            break
        relationship = str(edge.relationship or "related")
        cap = relationship_caps.get(relationship, max_inferred_edges)
        if relationship_counts.get(relationship, 0) >= cap:
            continue
        if degree.get(edge.source, 0) >= 2 and degree.get(edge.target, 0) >= 2:
            continue
        selected.append(edge)
        relationship_counts[relationship] = relationship_counts.get(relationship, 0) + 1
        degree[edge.source] = degree.get(edge.source, 0) + 1
        degree[edge.target] = degree.get(edge.target, 0) + 1
    return [*explicit, *selected]
