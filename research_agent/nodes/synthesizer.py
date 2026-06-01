from __future__ import annotations

from typing import Any, Dict, List

from observability import record_decision, record_tool_event
from product_agent.services.idea_generation_service import IdeaGenerationInput, IdeaGenerationService
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

    idea_input = IdeaGenerationInput(
        task_id=str(state.get("task_id", "")),
        topic=str(state.get("topic", "")),
        papers=list(papers.values()),
        gaps=state.get("detected_gaps", []),
    )
    idea_output = IdeaGenerationService().run(idea_input)
    ideas = idea_output.ideas
    idea_source = idea_output.source

    report_input = ReportGenerationInput(
        topic=str(state.get("topic", "")),
        alignment_score=float(state.get("alignment_score", 0.0) or 0.0),
        expert_taxonomy=state.get("expert_taxonomy", {}),
        audit_reports=state.get("audit_reports", []),
        detected_gaps=state.get("detected_gaps", []),
        ideas=ideas,
        mermaid=mermaid,
    )
    report_output = ReportGenerationService().run(report_input)
    report_text = _append_context_grounding(report_output.report_text, context_grounding)
    report_source = report_output.source
    report_id = report_output.report_id

    summary_input = SummaryGenerationInput(
        topic=str(state.get("topic", "")),
        alignment_score=float(state.get("alignment_score", 0.0) or 0.0),
        paper_nodes=list(papers.values()),
        detected_gaps=state.get("detected_gaps", []),
        ideas=ideas,
        report_text=report_text,
    )
    summary_output = SummaryGenerationService().run(summary_input)
    summary = dict(summary_output.summary or {})
    summary["context_grounding"] = context_grounding
    summary_source = summary_output.source

    updated = dict(state)
    updated["generated_ideas"] = ideas
    updated["final_report"] = report_text
    updated["final_report_id"] = report_id
    updated["final_report_text"] = report_text
    updated["final_report_summary"] = summary
    updated["mermaid_graph"] = mermaid

    record_tool_event(
        updated,
        tool_name="Idea generation",
        input_summary=f"papers={len(papers)}, gaps={len(state.get('detected_gaps', []))}",
        status="success" if idea_source.startswith("llm") else "fallback",
        output_count=len(ideas),
        note=idea_source,
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
        reason="Turn audited evidence into user-facing outputs for the workspace and report.",
        next_step="outputs",
    )

    logs.append(f"Synthesizer generated {len(ideas)} ideas via {idea_source}.")
    logs.append(f"Synthesizer generated report via {report_source}.")
    logs.append(f"Synthesizer generated summary via {summary_source}.")
    if context_grounding.get("knowledge_hit_count") or context_grounding.get("workspace_hint_count"):
        logs.append("Synthesizer attached context grounding metadata to report summary.")
    updated["logs"] = logs
    return updated


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
    retrieval_plan_summary = summarize_retrieval_plan(retrieval_plan)

    return {
        "knowledge_scope": str(state.get("knowledge_scope", "shared") or "shared"),
        "retrieval_plan": retrieval_plan_summary,
        "retrieval_outcome": retrieval_outcome,
        "knowledge_hit_count": len(knowledge_hits),
        "knowledge_hits": [
            {
                "title": str(hit.get("title", "")).strip(),
                "scope": str(hit.get("scope", "")).strip(),
                "source_type": str(hit.get("source_type", "")).strip(),
                "score": float(hit.get("score", 0.0) or 0.0),
            }
            for hit in knowledge_hits[:3]
        ],
        "workspace_hint_count": len(workspace_hints),
        "workspace_hints": [str(hint).strip() for hint in workspace_hints[:3] if str(hint).strip()],
        "workspace_summary": workspace_summary,
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
