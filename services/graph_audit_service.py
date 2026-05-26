from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List

from product_agent.schemas.audit import AuditGap, AuditReport, AuditResult

from .audit_common import (
    EVALUATION_TERMS,
    IMPROVEMENT_TERMS,
    LOW_CONFIDENCE_THRESHOLD,
    OVERLAP_THRESHOLD,
    canonical,
    keyword_overlap,
    paper_search_text,
)

if TYPE_CHECKING:
    from product_agent.research_agent.models import EvolutionEdge, PaperNode


class GraphAuditService:
    """图逻辑审计服务"""

    def audit(
        self, papers: Dict[str, PaperNode], edges: List[EvolutionEdge]
    ) -> AuditResult:
        reports: List[AuditReport] = []
        gaps: List[AuditGap] = []
        if not edges:
            return AuditResult(
                score=0.0,
                reports=[
                    AuditReport(
                        type="graph",
                        severity="info",
                        description="Evolution graph is empty.",
                        affected_items=[],
                        suggestion="Ensure edges are generated.",
                    )
                ],
                gaps=[
                    AuditGap(
                        type="graph",
                        severity="warning",
                        description="No evolution_graph edges found.",
                        affected_items=[],
                        actionable=False,
                    )
                ],
            )

        total_checks = 0
        failed_checks = 0
        existing_pairs = {(edge.source, edge.target) for edge in edges}

        for edge in edges:
            total_checks += 1
            source = papers.get(edge.source)
            target = papers.get(edge.target)
            if source is None or target is None:
                failed_checks += 1
                reports.append(
                    AuditReport(
                        type="graph",
                        severity="error",
                        description=f"Edge {edge.source} -> {edge.target} references missing paper node(s).",
                        affected_items=[edge.source, edge.target],
                        suggestion="Remove or fix dangling edges.",
                    )
                )
                gaps.append(
                    AuditGap(
                        type="graph",
                        severity="error",
                        description=f"Dangling edge: {edge.source} -> {edge.target}.",
                        affected_items=[edge.source, edge.target],
                        actionable=True,
                        related_papers=[edge.source, edge.target],
                        suggestion="Ensure all referenced papers exist.",
                    )
                )
                continue

            same_category = canonical(source.taxonomy_category) == canonical(target.taxonomy_category)
            overlap = keyword_overlap(source, target)
            if not same_category and overlap < OVERLAP_THRESHOLD:
                failed_checks += 1
                reports.append(
                    AuditReport(
                        type="graph",
                        severity="warning",
                        description=f"Edge {edge.source} -> {edge.target} crosses taxonomy categories with keyword overlap {overlap:.2f}.",
                        affected_items=[edge.source, edge.target],
                        suggestion="Review edge validity.",
                    )
                )
                gaps.append(
                    AuditGap(
                        type="graph",
                        severity="warning",
                        description=f"Weak cross-category edge: {edge.source} -> {edge.target} overlap={overlap:.2f}.",
                        affected_items=[edge.source, edge.target],
                        actionable=True,
                        related_papers=[edge.source, edge.target],
                        suggestion="Strengthen overlap or reconsider relationship.",
                    )
                )

            relationship = edge.relationship.lower().strip()
            if relationship in {"improves", "improve", "extends", "solves"}:
                total_checks += 1
                evidence_text = paper_search_text(target)
                has_claim = any(term in evidence_text for term in IMPROVEMENT_TERMS)
                has_eval = any(term in evidence_text for term in EVALUATION_TERMS)
                if not (has_claim and has_eval):
                    failed_checks += 1
                    reports.append(
                        AuditReport(
                            type="graph",
                            severity="warning",
                            description=f"Edge {edge.source} -> {edge.target} is marked as improvement but lacks clear evidence.",
                            affected_items=[edge.source, edge.target],
                            suggestion="Verify improvement claims.",
                        )
                    )
                    gaps.append(
                        AuditGap(
                            type="graph",
                            severity="warning",
                            description=f"Unsupported improvement claim: {edge.source} -> {edge.target}.",
                            affected_items=[edge.source, edge.target],
                            actionable=True,
                            related_papers=[edge.source, edge.target],
                            suggestion="Add evidence or adjust relationship.",
                        )
                    )

        for paper in papers.values():
            references = getattr(paper, "references", []) or []
            for ref_id in references:
                if ref_id in papers and (ref_id, paper.paper_id) not in existing_pairs:
                    total_checks += 1
                    failed_checks += 1
                    reports.append(
                        AuditReport(
                            type="graph",
                            severity="warning",
                            description=f"Paper {paper.paper_id} references {ref_id}, but no graph edge exists.",
                            affected_items=[paper.paper_id, ref_id],
                            suggestion="Add missing reference edge.",
                        )
                    )
                    gaps.append(
                        AuditGap(
                            type="graph",
                            severity="warning",
                            description=f"Missing reference edge: {ref_id} -> {paper.paper_id}.",
                            affected_items=[ref_id, paper.paper_id],
                            actionable=True,
                            related_papers=[ref_id, paper.paper_id],
                            suggestion="Create edge for citation.",
                        )
                    )

            confidence_score = getattr(paper, "confidence_score", 1.0)
            if confidence_score and confidence_score < LOW_CONFIDENCE_THRESHOLD:
                total_checks += 1
                failed_checks += 1
                reports.append(
                    AuditReport(
                        type="graph",
                        severity="warning",
                        description=f"Paper {paper.paper_id} has low confidence_score={confidence_score:.2f}.",
                        affected_items=[paper.paper_id],
                        suggestion="Review paper quality.",
                    )
                )
                gaps.append(
                    AuditGap(
                        type="graph",
                        severity="warning",
                        description=f"Low-confidence paper node: {paper.paper_id}.",
                        affected_items=[paper.paper_id],
                        actionable=True,
                        related_papers=[paper.paper_id],
                        suggestion="Improve data or remove low-quality paper.",
                    )
                )

        score = 1.0 - (failed_checks / total_checks) if total_checks else 0.0
        return AuditResult(
            score=max(0.0, min(1.0, score)),
            reports=reports,
            gaps=gaps,
        )
