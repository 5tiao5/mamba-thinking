from __future__ import annotations

import json
from typing import Dict, List

from observability import record_decision, record_tool_event
from product_agent.services.idea_generation_service import (
    IdeaGenerationInput,
    IdeaGenerationOutput,
    IdeaGenerationService,
)
from product_agent.services.report_generation_service import (
    ReportGenerationInput,
    ReportGenerationOutput,
    ReportGenerationService,
)
from product_agent.services.summary_generation_service import (
    SummaryGenerationInput,
    SummaryGenerationOutput,
    SummaryGenerationService,
)

from ..models import EvolutionEdge, PaperNode, ResearchState


def synthesizer_node(state: ResearchState) -> ResearchState:
    """
    Convert the internal analysis state into user-facing deliverables:
    report text, research ideas, a Mermaid graph, and a structured summary.

    This implementation delegates actual generation logic to service classes.
    """

    papers = state.get("paper_nodes", {})
    edges = state.get("evolution_graph", [])
    mermaid = build_mermaid_graph(papers, edges)
    logs = list(state.get("logs", []))

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
    report_text = report_output.report_text
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
    summary = summary_output.summary
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
