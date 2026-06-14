from __future__ import annotations

from typing import Any, Dict, List

from product_agent.observability import record_decision, record_tool_event
from product_agent.services.idea_generation_service import IdeaGenerationInput, IdeaGenerationService
from product_agent.services.evidence_snapshot_service import EvidenceSnapshotService
from product_agent.services.report_generation_service import ReportGenerationInput, ReportGenerationService
from product_agent.services.summary_generation_service import SummaryGenerationInput, SummaryGenerationService
from product_agent.services.text_cleaning import clean_internal_context_text

from ..models import EvolutionEdge, PaperNode, ResearchState
from ..retrieval_plan import summarize_retrieval_plan


def synthesizer_node(state: ResearchState) -> ResearchState:
    """
    Convert the internal analysis state into user-facing deliverables:
    report text, research ideas, a Mermaid graph, and a structured summary.
    """

    papers = state.get("paper_nodes", {})
    edges = state.get("evolution_graph", [])
    mermaid = build_mermaid_graph(papers, edges)
    logs = list(state.get("logs", []))
    context_grounding = _build_context_grounding(state)
    evidence_snapshot = EvidenceSnapshotService().build(
        topic=str(state.get("topic", "")),
        papers=papers,
        taxonomy=state.get("expert_taxonomy", {}),
        edges=edges,
        gaps=state.get("detected_gaps", []),
        retrieval_plan=state.get("retrieval_plan", {}),
        retrieval_outcome=state.get("retrieval_outcome", {}),
        alignment_score=float(state.get("alignment_score", 0.0) or 0.0),
        audit_reports=state.get("audit_reports", []),
    )
    snapshot_papers = list(evidence_snapshot.get("papers", []))
    snapshot_gaps = list(evidence_snapshot.get("gaps", []))
    snapshot_taxonomy = dict(evidence_snapshot.get("taxonomy", {}) or {})
    snapshot_audits = list(evidence_snapshot.get("audit_reports", []))

    conclusion_contract = dict(
        evidence_snapshot.get("conclusion_contract", {}) or {}
    )
    claimable_paper_ids = {
        str(paper_id)
        for paper_id in list(
            conclusion_contract.get("claimable_paper_ids", []) or []
        )
        if str(paper_id)
    }
    claimable_papers = [
        paper
        for paper in snapshot_papers
        if str(paper.get("paper_id", "")) in claimable_paper_ids
    ]
    suppress_ideas = (
        _should_suppress_research_ideas(state)
        or not bool(conclusion_contract.get("recommendations_allowed", False))
    )
    if suppress_ideas:
        ideas = []
        idea_source = "suppressed_insufficient_direct_evidence"
    else:
        idea_input = IdeaGenerationInput(
            task_id=str(state.get("task_id", "")),
            topic=str(state.get("topic", "")),
            papers=claimable_papers,
            gaps=snapshot_gaps,
            evidence_snapshot=evidence_snapshot,
        )
        idea_output = IdeaGenerationService().run(idea_input)
        ideas, idea_admission = _ground_ideas(
            idea_output.ideas,
            claimable_paper_ids=claimable_paper_ids,
            taxonomy_branches=list(snapshot_taxonomy.get("branches", []) or []),
            gaps=snapshot_gaps,
        )
        idea_source = idea_output.source
        if not ideas:
            suppress_ideas = True
            idea_source = f"{idea_source}+rejected_ungrounded"
    if suppress_ideas:
        idea_admission = {
            "supported_count": 0,
            "exploratory_count": 0,
            "rejected_count": 0,
        }

    supported_idea_count = int(idea_admission.get("supported_count", 0) or 0)
    exploratory_idea_count = int(
        idea_admission.get("exploratory_count", 0) or 0
    )
    recommendation_allowed = supported_idea_count > 0
    supported_idea_ids = {
        str(idea_id)
        for idea_id in list(idea_admission.get("supported_idea_ids", []) or [])
        if str(idea_id)
    }
    recommendable_ideas = [
        idea
        for idea in ideas
        if str(getattr(idea, "idea_id", "") or "") in supported_idea_ids
    ]

    report_input = ReportGenerationInput(
        topic=str(state.get("topic", "")),
        alignment_score=float(state.get("alignment_score", 0.0) or 0.0),
        expert_taxonomy=snapshot_taxonomy,
        audit_reports=snapshot_audits,
        detected_gaps=snapshot_gaps,
        ideas=ideas,
        mermaid=mermaid,
        evidence_snapshot=evidence_snapshot,
        allow_research_ideas=bool(ideas),
    )
    report_output = ReportGenerationService().run(report_input)
    report_text = _append_context_grounding(report_output.report_text, context_grounding)
    report_source = report_output.source
    report_id = report_output.report_id

    summary_input = SummaryGenerationInput(
        topic=str(state.get("topic", "")),
        alignment_score=float(state.get("alignment_score", 0.0) or 0.0),
        paper_nodes=snapshot_papers,
        detected_gaps=snapshot_gaps,
        ideas=recommendable_ideas,
        report_text=report_text,
        evidence_snapshot=evidence_snapshot,
        allow_recommendation=recommendation_allowed,
    )
    summary_output = SummaryGenerationService().run(summary_input)
    summary = dict(summary_output.summary or {})
    evidence_pool = state.get("evidence_pool") or papers
    counts = dict(summary.get("counts", {}) or {})
    counts["papers"] = len(evidence_pool)
    counts["papers_retrieved"] = len(evidence_pool)
    counts["papers_analyzed"] = len(papers)
    counts["ideas"] = len(ideas)
    counts["supported_ideas"] = supported_idea_count
    counts["exploratory_ideas"] = exploratory_idea_count
    summary["counts"] = counts
    summary["context_grounding"] = context_grounding
    summary["evidence_snapshot"] = evidence_snapshot
    summary["idea_admission"] = idea_admission
    summary_source = summary_output.source

    updated = dict(state)
    updated["generated_ideas"] = ideas
    updated["evidence_snapshot"] = evidence_snapshot
    updated["final_report"] = report_text
    updated["final_report_id"] = report_id
    updated["final_report_text"] = report_text
    updated["final_report_summary"] = summary
    updated["mermaid_graph"] = mermaid
    if suppress_ideas:
        updated["degraded_reason"] = (
            str(updated.get("degraded_reason", "") or "").strip()
            or _idea_suppression_reason(
                conclusion_contract=conclusion_contract,
                idea_source=idea_source,
            )
        )
    elif exploratory_idea_count and not supported_idea_count:
        updated["degraded_reason"] = (
            str(updated.get("degraded_reason", "") or "").strip()
            or "Generated research directions are exploratory because their target "
            "taxonomy branches lack direct supporting papers."
        )

    record_tool_event(
        updated,
        tool_name="Idea generation",
        input_summary=f"papers={len(papers)}, gaps={len(state.get('detected_gaps', []))}",
        status="success" if idea_source.startswith("llm") else "fallback",
        output_count=len(ideas),
        note=(
            f"{idea_source}; supported={supported_idea_count}; "
            f"exploratory={exploratory_idea_count}; "
            f"rejected={int(idea_admission.get('rejected_count', 0) or 0)}"
        ),
    )
    record_tool_event(
        updated,
        tool_name="Report generation",
        input_summary=f"ideas={len(ideas)}",
        status="success" if report_source == "llm" else "fallback",
        output_count=1,
        note=report_source,
    )
    record_tool_event(
        updated,
        tool_name="Summary generation",
        input_summary=f"ideas={len(ideas)}, report_length={len(report_text)}",
        status="success" if summary_source.startswith("llm") else "fallback",
        output_count=1,
        note=summary_source,
    )
    record_decision(
        updated,
        stage="synthesizer",
        decision=f"Generated {len(ideas)} ideas, final report, and structured summary.",
        reason=(
            "Freeze audited evidence into one snapshot, then use it for all "
            "user-facing outputs."
        ),
        next_step="outputs",
    )

    logs.append(f"Synthesizer generated {len(ideas)} ideas via {idea_source}.")
    logs.append(f"Synthesizer generated report via {report_source}.")
    logs.append(f"Synthesizer generated summary via {summary_source}.")
    logs.append(
        "Synthesizer froze evidence snapshot "
        f"{evidence_snapshot.get('snapshot_id', '')}."
    )
    if context_grounding.get("knowledge_hit_count") or context_grounding.get("workspace_hint_count"):
        logs.append("Synthesizer attached context grounding metadata to report summary.")
    updated["logs"] = logs
    return updated


def _should_suppress_research_ideas(state: ResearchState) -> bool:
    outcome = state.get("retrieval_outcome", {})
    if not isinstance(outcome, dict):
        return False
    return (
        int(outcome.get("real_paper_count", 0) or 0) > 0
        and int(outcome.get("direct_paper_count", 0) or 0) == 0
    )


def _ground_ideas(
    ideas: List[Any],
    *,
    claimable_paper_ids: set[str],
    taxonomy_branches: List[Dict[str, Any]],
    gaps: List[Dict[str, Any]],
) -> tuple[List[Any], Dict[str, Any]]:
    """Admit recommendations at branch level and downgrade unsupported gaps."""

    grounded: List[Any] = []
    stats = {
        "supported_count": 0,
        "exploratory_count": 0,
        "rejected_count": 0,
        "supported_idea_ids": [],
        "exploratory_idea_ids": [],
    }
    gap_branch_evidence: Dict[str, set[str]] = {}
    for branch in taxonomy_branches:
        direct_ids = {
            str(paper_id)
            for paper_id in list(
                branch.get(
                    "claimable_paper_ids",
                    branch.get("direct_paper_ids", []),
                )
                or []
            )
            if str(paper_id)
        }
        for gap_id in list(branch.get("matched_gap_ids", []) or []):
            normalized_gap_id = str(gap_id).strip()
            if normalized_gap_id:
                gap_branch_evidence.setdefault(normalized_gap_id, set()).update(
                    direct_ids
                )
        branch_name = str(branch.get("name", "") or "").strip()
        if not branch_name:
            continue
        normalized_branch_name = _normalized_binding_text(branch_name)
        for gap in gaps:
            gap_id = str(gap.get("gap_id", "") or "").strip()
            gap_summary = _normalized_binding_text(
                str(gap.get("summary", "") or "")
            )
            if gap_id and normalized_branch_name in gap_summary:
                gap_branch_evidence.setdefault(gap_id, set()).update(direct_ids)

    for idea in ideas:
        related = [
            str(paper_id)
            for paper_id in list(getattr(idea, "related_papers", []) or [])
            if str(paper_id) in claimable_paper_ids
        ]
        if not related:
            stats["rejected_count"] += 1
            continue
        idea.related_papers = list(dict.fromkeys(related))[:3]
        derived_gap_ids = [
            str(gap_id).strip()
            for gap_id in list(getattr(idea, "derived_from_gaps", []) or [])
            if str(gap_id).strip()
        ]
        linked_gap_ids = [
            gap_id for gap_id in derived_gap_ids if gap_id in gap_branch_evidence
        ]
        unsupported_gap_ids = [
            gap_id
            for gap_id in linked_gap_ids
            if not gap_branch_evidence.get(gap_id)
        ]
        mismatched_gap_ids = [
            gap_id
            for gap_id in linked_gap_ids
            if gap_branch_evidence.get(gap_id)
            and not (
                set(idea.related_papers) & gap_branch_evidence.get(gap_id, set())
            )
        ]
        if unsupported_gap_ids or mismatched_gap_ids:
            _mark_idea_exploratory(
                idea,
                reason=(
                    "target branch lacks direct evidence"
                    if unsupported_gap_ids
                    else "cited papers do not support the target branch"
                ),
            )
            stats["exploratory_count"] += 1
            stats["exploratory_idea_ids"].append(
                str(getattr(idea, "idea_id", "") or "")
            )
        else:
            stats["supported_count"] += 1
            stats["supported_idea_ids"].append(
                str(getattr(idea, "idea_id", "") or "")
            )
        grounded.append(idea)
    return grounded, stats


def _normalized_binding_text(value: str) -> str:
    return " ".join(
        "".join(
            character.casefold() if character.isalnum() else " "
            for character in str(value or "")
        ).split()
    )


def _mark_idea_exploratory(idea: Any, *, reason: str) -> None:
    title = str(getattr(idea, "title", "") or "").strip()
    if title and not title.startswith("探索性方向："):
        idea.title = f"探索性方向：{title}"
    disclaimer = (
        "该方向当前缺少分支级直接论文证据，以下内容仅作为待验证假设，"
        "不应视为已有研究结论。"
    )
    motivation = str(getattr(idea, "motivation", "") or "").strip()
    if disclaimer not in motivation:
        idea.motivation = f"{disclaimer}{motivation}"
    idea.confidence = min(float(getattr(idea, "confidence", 0.0) or 0.0), 0.45)
    tags = list(getattr(idea, "tags", []) or [])
    idea.tags = list(dict.fromkeys(["exploratory", reason, *tags]))[:5]


def _idea_suppression_reason(
    *,
    conclusion_contract: Dict[str, Any],
    idea_source: str,
) -> str:
    if not bool(conclusion_contract.get("recommendations_allowed", False)):
        return (
            "No direct paper evidence remained after retrieval repair; "
            "research ideas were suppressed."
        )
    if "rejected_ungrounded" in idea_source:
        return (
            "Generated research ideas could not be bound to the audited direct "
            "paper evidence and were rejected."
        )
    return "Research ideas were suppressed by the evidence admission policy."


def build_mermaid_graph(papers: Dict[str, PaperNode], edges: List[EvolutionEdge]) -> str:
    lines = ["graph LR"]
    if not papers:
        return "graph LR\n  empty[No papers]"

    node_ids = {paper_id: _mermaid_id(paper_id) for paper_id in papers}

    def label(paper: PaperNode) -> str:
        title = paper.title[:45].replace('"', "'") or paper.paper_id
        return f'{node_ids[paper.paper_id]}["{title}"]'

    for paper in list(papers.values())[:30]:
        lines.append(f"  {label(paper)}")
    for edge in edges[:50]:
        if edge.source not in node_ids or edge.target not in node_ids:
            continue
        rel = edge.relationship.replace('"', "'")
        lines.append(f'  {node_ids[edge.source]} -- "{rel}" --> {node_ids[edge.target]}')
    return "\n".join(lines)


def _append_context_grounding(report_text: str, context_grounding: dict[str, Any]) -> str:
    note = _context_grounding_note(context_grounding)
    if not note:
        return report_text
    return report_text.rstrip() + "\n\n## Context Grounding\n\n" + note + "\n"


def _build_context_grounding(state: ResearchState) -> dict[str, Any]:
    knowledge_hits = state.get("knowledge_hits", []) or []
    workspace_hints = state.get("conversation_workspace_context", []) or []
    recent_context = state.get("recent_context", []) or []
    retrieval_plan = state.get("retrieval_plan", {}) if isinstance(state.get("retrieval_plan"), dict) else {}
    retrieval_outcome = state.get("retrieval_outcome", {}) if isinstance(state.get("retrieval_outcome"), dict) else {}
    workspace_summary = clean_internal_context_text(
        str(state.get("conversation_workspace_summary", "") or ""),
        max_length=240,
    )
    working_memory_summary = clean_internal_context_text(
        str(state.get("working_memory_summary", "") or ""),
        max_length=240,
    )
    retrieval_plan_summary = summarize_retrieval_plan(retrieval_plan)

    return {
        "knowledge_scope": str(state.get("knowledge_scope", "shared") or "shared"),
        "retrieval_plan": retrieval_plan_summary,
        "retrieval_outcome": retrieval_outcome,
        "knowledge_hit_count": len(knowledge_hits),
        "knowledge_hits": [
            {
                "title": str(hit.get("title", "")).strip(),
                "snippet": clean_internal_context_text(str(hit.get("snippet", "") or ""), max_length=1200),
                "scope": str(hit.get("scope", "")).strip(),
                "source_type": str(hit.get("source_type", "")).strip(),
                "score": float(hit.get("score", 0.0) or 0.0),
                "evidence_level": str(hit.get("evidence_level", "")).strip() or "candidate",
                "matched_chunk_count": int(hit.get("matched_chunk_count", 0) or 0),
                "supporting_snippets": [
                    clean_internal_context_text(str(snippet), max_length=1200)
                    for snippet in list(hit.get("supporting_snippets", []) or [])[:3]
                    if clean_internal_context_text(str(snippet), max_length=1200)
                ],
            }
            for hit in knowledge_hits[:3]
        ],
        "workspace_hint_count": len(workspace_hints),
        "workspace_hints": [str(hint).strip() for hint in workspace_hints[:3] if str(hint).strip()],
        "workspace_summary": workspace_summary,
        "working_memory_summary": working_memory_summary,
        "working_memory_current_focus": clean_internal_context_text(
            str(state.get("working_memory_current_focus", "") or ""),
            max_length=180,
        ),
        "working_memory_findings": [
            clean_internal_context_text(str(item), max_length=140)
            for item in list(state.get("working_memory_findings", []) or [])[:3]
            if clean_internal_context_text(str(item), max_length=140)
        ],
        "working_memory_open_questions": [
            clean_internal_context_text(str(item), max_length=160)
            for item in list(state.get("working_memory_open_questions", []) or [])[:2]
            if clean_internal_context_text(str(item), max_length=160)
        ],
        "working_memory_constraints": [
            clean_internal_context_text(str(item), max_length=120)
            for item in list(state.get("working_memory_constraints", []) or [])[:3]
            if clean_internal_context_text(str(item), max_length=120)
        ],
        "recent_turn_count": len(recent_context),
        "recent_user_turns": [
            clean_internal_context_text(str(entry.get("content", "")), max_length=160)
            for entry in recent_context
            if str(entry.get("role", "")).lower() == "user"
        ][:2],
    }


def _context_grounding_note(context_grounding: dict[str, Any]) -> str:
    parts: list[str] = []
    knowledge_hit_count = int(context_grounding.get("knowledge_hit_count", 0) or 0)
    workspace_hint_count = int(context_grounding.get("workspace_hint_count", 0) or 0)
    recent_turn_count = int(context_grounding.get("recent_turn_count", 0) or 0)
    knowledge_scope = str(context_grounding.get("knowledge_scope", "shared") or "shared")
    retrieval_plan = str(context_grounding.get("retrieval_plan", "") or "").strip()
    retrieval_outcome = context_grounding.get("retrieval_outcome", {}) if isinstance(context_grounding.get("retrieval_outcome"), dict) else {}

    if knowledge_hit_count:
        parts.append(f"reused {knowledge_hit_count} knowledge hits from scope `{knowledge_scope}`")
    if workspace_hint_count:
        parts.append(f"inherited {workspace_hint_count} workspace hints")
    working_memory_summary = str(context_grounding.get("working_memory_summary", "") or "").strip()
    if working_memory_summary:
        parts.append("used explicit working memory")
    if recent_turn_count:
        parts.append(f"referenced {recent_turn_count} recent dialogue turns")
    if retrieval_plan:
        parts.append(f"used retrieval plan `{retrieval_plan}`")
    outcome_message = " ".join(str(retrieval_outcome.get("message", "")).split()).strip()
    if outcome_message:
        parts.append(outcome_message)
    if not parts:
        return ""

    note = "This round did not start from zero. It " + ", ".join(parts) + "."
    workspace_summary = str(context_grounding.get("workspace_summary", "") or "").strip()
    if workspace_summary:
        note += f" Prior workspace summary: {workspace_summary}"
    if working_memory_summary:
        note += f" Working memory summary: {working_memory_summary}"
    return note


def _paper_brief(paper: PaperNode) -> Dict[str, str]:
    return {
        "id": paper.paper_id,
        "title": paper.title,
        "category": paper.taxonomy_category,
        "abstract": paper.abstract[:500],
    }


def _mermaid_id(value: str) -> str:
    safe = "".join(ch if ch.isalnum() else "_" for ch in value)
    return "n_" + safe
