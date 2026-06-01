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
                        description=f"关系边 {edge.source} -> {edge.target} 指向了缺失的论文节点。",
                        affected_items=[edge.source, edge.target],
                        suggestion="请检查节点是否存在，或移除这条悬空关系边。",
                    )
                )
                gaps.append(
                    AuditGap(
                        type="graph",
                        severity="error",
                        description=f"发现悬空关系边：{edge.source} -> {edge.target}。",
                        affected_items=[edge.source, edge.target],
                        actionable=True,
                        related_papers=[edge.source, edge.target],
                        suggestion="确认相关论文是否缺失，必要时补齐或删除该关系。",
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
                        description=f"关系边 {edge.source} -> {edge.target} 跨越不同分类，且关键词重合度仅为 {overlap:.2f}。",
                        affected_items=[edge.source, edge.target],
                        suggestion="请复核这条跨方向关系是否真的成立。",
                    )
                )
                gaps.append(
                    AuditGap(
                        type="graph",
                        severity="warning",
                        description=f"跨方向关系证据偏弱：{edge.source} -> {edge.target}（重合度 {overlap:.2f}）。",
                        affected_items=[edge.source, edge.target],
                        actionable=True,
                        related_papers=[edge.source, edge.target],
                        suggestion="补充更直接的证据，或重新判断这条关系是否需要保留。",
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
                            description=f"关系边 {edge.source} -> {edge.target} 被标记为“改进”，但当前缺少清晰证据支撑。",
                            affected_items=[edge.source, edge.target],
                            suggestion="请核对目标论文是否真的在方法、实验或结果上改进了前作。",
                        )
                    )
                    gaps.append(
                        AuditGap(
                            type="graph",
                            severity="warning",
                            description=f"“{edge.source}”到“{edge.target}”的改进关系缺少证据支持。",
                            affected_items=[edge.source, edge.target],
                            actionable=True,
                            related_papers=[edge.source, edge.target],
                            suggestion="补充摘要、实验或对比结果中的证据，或调整关系类型。",
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
                            description=f"论文 {paper.paper_id} 引用了 {ref_id}，但演进图中缺少对应关系边。",
                            affected_items=[paper.paper_id, ref_id],
                            suggestion="可以补上这条引用关系边，增强演进图完整性。",
                        )
                    )
                    gaps.append(
                        AuditGap(
                            type="graph",
                            severity="warning",
                            description=f"引用关系缺失：{ref_id} -> {paper.paper_id}。",
                            affected_items=[ref_id, paper.paper_id],
                            actionable=True,
                            related_papers=[ref_id, paper.paper_id],
                            suggestion="根据引用信息补上这条关系边。",
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
                        description=f"论文 {paper.paper_id} 的可信度较低（confidence={confidence_score:.2f}）。",
                        affected_items=[paper.paper_id],
                        suggestion="建议复核这篇论文的质量与相关性。",
                    )
                )
                gaps.append(
                    AuditGap(
                        type="graph",
                        severity="warning",
                        description=f"低置信论文节点：{paper.paper_id}。",
                        affected_items=[paper.paper_id],
                        actionable=True,
                        related_papers=[paper.paper_id],
                        suggestion="补充更强证据，或考虑移除这篇低质量论文。",
                    )
                )

        score = 1.0 - (failed_checks / total_checks) if total_checks else 0.0
        return AuditResult(
            score=max(0.0, min(1.0, score)),
            reports=reports,
            gaps=gaps,
        )
