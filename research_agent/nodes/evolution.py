from __future__ import annotations

import itertools
from typing import Dict, Tuple

from observability import record_decision, record_graph_event
from pipeline_utils import (
    balanced_fallback_pairs,
    balanced_mode,
    canonical,
    keyword_overlap,
    order_by_date,
)
from product_agent.services.relationship_evidence_service import RelationshipEvidenceService

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

    for left, right in itertools.permutations(papers.values(), 2):
        if left.paper_id == right.paper_id or (left.paper_id, right.paper_id) in edges:
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
            older, newer = order_by_date(left, right)
            if older.paper_id != newer.paper_id:
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

    verified_edges = RelationshipEvidenceService().verify(papers, edges.values())
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
