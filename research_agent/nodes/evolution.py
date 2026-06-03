from __future__ import annotations

import itertools
from typing import Dict, Tuple

from observability import record_decision, record_graph_event
from pipeline_utils import (
    balanced_fallback_pairs,
    balanced_mode,
    canonical,
    infer_relationship,
    keyword_overlap,
    order_by_date,
)

from ..models import EvolutionEdge, PaperNode, ResearchState


OVERLAP_THRESHOLD = 0.40


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
                    relationship=infer_relationship(ref_paper, paper),
                    reasoning="Created from explicit reference metadata.",
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
        same_category = canonical(left.taxonomy_category) and (
            canonical(left.taxonomy_category) == canonical(right.taxonomy_category)
        )
        overlap = keyword_overlap(left, right)
        if same_category or overlap >= OVERLAP_THRESHOLD:
            older, newer = order_by_date(left, right)
            if older.paper_id != newer.paper_id:
                edges[(older.paper_id, newer.paper_id)] = EvolutionEdge(
                    source=older.paper_id,
                    target=newer.paper_id,
                    relationship=infer_relationship(older, newer),
                    reasoning=(
                        "Created because papers share taxonomy or keywords; "
                        f"keyword_overlap={overlap:.2f}."
                    ),
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
                relationship=infer_relationship(source, target),
                reasoning=(
                    "Balanced-mode fallback edge: ArXiv metadata has no references, "
                    "so this edge is inferred from topic relevance, shared keywords, "
                    f"and publication order; weak_overlap={overlap:.2f}."
                ),
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

    updated = dict(state)
    updated["evolution_graph"] = list(edges.values())
    record_decision(
        updated,
        stage="evolution",
        decision=f"Built graph with {len(edges)} edges.",
        reason="Edges are inferred from references, taxonomy, keyword overlap, or balanced fallback.",
        next_step="auditor",
    )
    updated.setdefault("logs", []).append(f"Evolution graph built with {len(edges)} edges.")
    return updated
