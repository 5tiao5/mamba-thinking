from __future__ import annotations

import re
from typing import Any, Dict, List

from product_agent.domain import GapRecord, PaperRecord, ResearchIdeaRecord, ResearchWorkspace


def workspace_from_agent_state(*, task_id: str, topic: str, state: Dict[str, Any]) -> ResearchWorkspace:
    """
    将旧版 Agent state 转成产品工作台对象。

    这是前后端契约稳定化的关键步骤。

    TODO(iter3-workspace-mapper):
    1. 继续补全 taxonomy summary / recommended papers / key comparisons
    2. 为前端增加 section-level payload
    3. 增加引用来源与 evidence mapping
    """

    papers = [_map_paper(paper) for paper in state.get("paper_nodes", {}).values()]
    gaps = [_map_gap(task_id, gap) for gap in state.get("detected_gaps", [])]
    ideas = [_map_idea(task_id, idea) for idea in state.get("generated_ideas", [])]
    graph_edges = [
        edge.model_dump() if hasattr(edge, "model_dump") else dict(edge)
        for edge in state.get("evolution_graph", [])
    ]

    return ResearchWorkspace(
        task_id=task_id,
        topic=topic,
        summary=state.get("final_report", "")[:400],
        papers=papers,
        taxonomy=state.get("expert_taxonomy", {}),
        graph_edges=graph_edges,
        gaps=gaps,
        ideas=ideas,
        alignment_score=float(state.get("alignment_score", 0.0) or 0.0),
        trace={
            "thought_trace": state.get("thought_trace", []),
            "action_history": state.get("action_history", []),
            "context_inputs": [],
        },
    )


def _map_paper(paper: Any) -> PaperRecord:
    if hasattr(paper, "model_dump"):
        payload = paper.model_dump()
    elif isinstance(paper, dict):
        payload = paper
    else:
        payload = paper.__dict__
    return PaperRecord(
        paper_id=str(payload.get("paper_id", "")),
        title=str(payload.get("title", "")),
        abstract=str(payload.get("abstract", "")),
        authors=list(payload.get("authors", [])),
        publish_date=str(payload.get("publish_date", "")),
        source=str(payload.get("source", "")),
        taxonomy_category=str(payload.get("taxonomy_category", "")),
        citation_count=int(payload.get("citation_count", 0) or 0),
        url=str(payload.get("url", "")),
    )


def _map_gap(task_id: str, raw_gap: str) -> GapRecord:
    severity = "high" if any(token in raw_gap.lower() for token in ["missing", "unsupported", "dangling"]) else "medium"
    return GapRecord(
        gap_id=f"gap_{abs(hash((task_id, raw_gap))) % 10_000_000}",
        task_id=task_id,
        summary=raw_gap,
        severity=severity,
        evidence=[],
    )


def _map_idea(task_id: str, raw_idea: str) -> ResearchIdeaRecord:
    title = _extract_title(raw_idea)
    return ResearchIdeaRecord(
        idea_id=f"idea_{abs(hash((task_id, raw_idea))) % 10_000_000}",
        task_id=task_id,
        title=title,
        motivation="",
        approach="",
        feasibility="",
        contribution="",
    )


def _extract_title(raw_idea: str) -> str:
    first_line = raw_idea.strip().splitlines()[0] if raw_idea.strip() else "Untitled Idea"
    first_line = re.sub(r"^\s*\d+[\.\、)]\s*", "", first_line).strip()
    return first_line[:120] or "Untitled Idea"
