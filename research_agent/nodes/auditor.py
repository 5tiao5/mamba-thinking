from __future__ import annotations

import os
from typing import Any, Dict, Iterable, List, Mapping, Sequence

from llm_client import call_openai_json
from observability import record_audit_event, record_decision, record_tool_event

from product_agent.schemas.audit import AuditGap, AuditReport, AuditSummary
from product_agent.services.audit_common import (
    EVALUATION_TERMS,
    IMPROVEMENT_TERMS,
    LOW_CONFIDENCE_THRESHOLD,
    OVERLAP_THRESHOLD,
    TaxonomyBranch,
    canonical,
    contains_phrase,
    keyword_overlap,
    paper_search_text,
)
from product_agent.services.graph_audit_service import GraphAuditService
from product_agent.services.llm_audit_service import LLMAuditService
from product_agent.services.taxonomy_audit_service import TaxonomyAuditService

from ..models import EvolutionEdge, PaperNode, ResearchState


def auditor_node(state: ResearchState) -> ResearchState:
    """
    Audit the current analysis result and convert hidden quality issues into
    explicit reports and gaps.

    This implementation now lives inside `product_agent/research_agent/`,
    which means the new pipeline no longer depends on the legacy root-level
    `auditor.py` node wrapper.
    """

    papers = _normalize_papers(state.get("paper_nodes", {}))
    edges = _normalize_edges(state.get("evolution_graph", []))
    taxonomy = _normalize_taxonomy(state.get("expert_taxonomy", {}))

    _enrich_edge_reasoning(papers, edges)

    # 使用拆分的 service
    taxonomy_service = TaxonomyAuditService()
    graph_service = GraphAuditService()
    llm_service = LLMAuditService()

    taxonomy_result = taxonomy_service.audit(papers, taxonomy)
    graph_result = graph_service.audit(papers, edges)
    llm_result = llm_service.audit(papers, edges)

    if os.environ.get("SKIP_AUDITOR_LLM") == "1":
        record_tool_event(
            state,
            tool_name="LLM edge auditor",
            input_summary=f"edges={len(edges[:8])}",
            status="skipped",
            note="Current mode skips LLM edge auditing.",
        )
    elif any(
        edge.relationship.lower()
        in {"improves", "improvement", "extends", "extension", "solves"}
        for edge in edges[:8]
    ):
        record_tool_event(
            state,
            tool_name="LLM edge auditor",
            input_summary=f"edges={len(edges[:8])}",
            status="success" if llm_result.gaps or llm_result.reports else "fallback",
            output_count=len(llm_result.reports) + len(llm_result.gaps),
            note="Semantic audit over improvement-style edges.",
        )

    # 合并结果
    reports = taxonomy_result.reports + graph_result.reports + llm_result.reports
    gaps = _dedupe_gaps(taxonomy_result.gaps + graph_result.gaps + llm_result.gaps)
    _mark_gap_candidates(papers, gaps)

    for gap in gaps[:20]:
        record_audit_event(
            state,
            event_type="gap_detected",
            summary=gap.description,
            severity=gap.severity,
            recovery="Use the gap in Corrector or Synthesizer for follow-up analysis.",
        )

    alignment_score = round(
        (taxonomy_result.score * 0.5) + (graph_result.score * 0.3) + (llm_result.score * 0.2), 3
    )
    record_audit_event(
        state,
        event_type="alignment_score",
        summary=f"taxonomy_score={taxonomy_result.score:.3f}, graph_score={graph_result.score:.3f}, llm_score={llm_result.score:.3f}, final={alignment_score:.3f}",
        severity="info",
        recovery="Pass the result to Corrector for repair or acceptance.",
    )

    if not reports:
        reports = [
            AuditReport(
                type="general",
                severity="info",
                description="Audit passed: no obvious taxonomy or graph consistency issues were found.",
                affected_items=[],
            )
        ]

    # 建立 report 和 gap 的关联
    gap_ids_by_items = {}
    for gap in gaps:
        for item in gap.affected_items:
            if item not in gap_ids_by_items:
                gap_ids_by_items[item] = []
            gap_ids_by_items[item].append(gap.id)
    
    for report in reports:
        related_gap_ids = set()
        for item in report.affected_items:
            related_gap_ids.update(gap_ids_by_items.get(item, []))
        report.related_gap_ids = list(related_gap_ids)

    # 生成 audit_summary
    severity_dist = {
        "error": sum(1 for g in gaps if g.severity == "error"),
        "warning": sum(1 for g in gaps if g.severity == "warning"),
        "info": sum(1 for g in gaps if g.severity == "info"),
    }
    gap_types_dist = {}
    for gap in gaps:
        gap_types_dist[gap.type] = gap_types_dist.get(gap.type, 0) + 1
    
    audit_summary = AuditSummary(
        score=alignment_score,
        gap_count=len(gaps),
        report_count=len(reports),
        severity_distribution=severity_dist,
        actionable_gap_count=sum(1 for g in gaps if g.actionable),
        gap_types=gap_types_dist,
    )

    updated = dict(state)
    updated["paper_nodes"] = papers
    updated["evolution_graph"] = edges
    updated["alignment_score"] = alignment_score
    updated["audit_reports"] = [report.to_dict() for report in reports]  # 使用 to_dict() 控制 API contract
    updated["detected_gaps"] = [gap.to_dict() for gap in gaps]  # 使用 to_dict() 控制 API contract
    updated["audit_summary"] = audit_summary.to_dict()  # 添加摘要给前端仪表盘

    record_decision(
        updated,
        stage="auditor",
        decision=f"Detected {len(gaps)} gaps with score {alignment_score}.",
        reason="Compare the paper graph against taxonomy coverage and graph consistency rules.",
        next_step="corrector",
    )
    updated.setdefault("logs", []).append(f"Auditor completed with alignment_score={alignment_score}.")
    return updated







def _normalize_papers(raw: Any) -> Dict[str, PaperNode]:
    if isinstance(raw, Mapping):
        items = raw.items()
    else:
        items = ((getattr(item, "paper_id", str(index)), item) for index, item in enumerate(raw or []))

    papers = {}
    for key, value in items:
        if isinstance(value, PaperNode):
            paper = value
        else:
            payload = dict(value)
            payload.setdefault("paper_id", key)
            paper = PaperNode(**payload)
        papers[paper.paper_id] = paper
    return papers


def _normalize_edges(raw: Any) -> List[EvolutionEdge]:
    return [edge if isinstance(edge, EvolutionEdge) else EvolutionEdge(**dict(edge)) for edge in raw or []]


def _normalize_taxonomy(raw: Any) -> List[TaxonomyBranch]:
    if not raw:
        return []
    taxonomy = raw.get("taxonomy", raw) if isinstance(raw, Mapping) else raw
    branches: List[TaxonomyBranch] = []
    if isinstance(taxonomy, Mapping):
        for name, payload in taxonomy.items():
            payload = payload if isinstance(payload, Mapping) else {"description": str(payload)}
            branches.append(
                TaxonomyBranch(
                    name=str(name),
                    description=str(payload.get("description", "")),
                    required_concepts=tuple(str(x) for x in payload.get("required_concepts", [])),
                )
            )
    return branches


def _enrich_edge_reasoning(papers: Dict[str, PaperNode], edges: List[EvolutionEdge]) -> None:
    for edge in edges:
        if edge.reasoning:
            continue
        source = papers.get(edge.source)
        target = papers.get(edge.target)
        if not source or not target:
            continue
        edge.reasoning = (
            f"Audited as '{edge.relationship}' because source and target share taxonomy or keywords; "
            f"keyword_overlap={keyword_overlap(source, target):.2f}."
        )


def _mark_gap_candidates(papers: Dict[str, PaperNode], gaps: Sequence[AuditGap]) -> None:
    """标记 gap 相关的 paper，使用结构化引用而非文本匹配"""
    for gap in gaps:
        for item in gap.affected_items:
            if item in papers:
                papers[item].is_gap_candidate = True


def _paper_search_text(paper: PaperNode) -> str:
    return paper_search_text(paper)


def _keyword_overlap(left: PaperNode, right: PaperNode) -> float:
    return keyword_overlap(left, right)


def _contains_phrase(text: str, phrase: str) -> bool:
    return contains_phrase(text, phrase)


def _canonical(value: str) -> str:
    return canonical(value)


def _dedupe_gaps(items: Iterable[AuditGap]) -> List[AuditGap]:
    """使用稳定的 gap id 进行去重"""
    result: List[AuditGap] = []
    seen = set()
    for item in items:
        if item.id not in seen:
            seen.add(item.id)
            result.append(item)
    return result
