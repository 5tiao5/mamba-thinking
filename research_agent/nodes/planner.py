from __future__ import annotations

from typing import List

from llm_client import call_openai_json
from observability import StageTimer, record_decision, record_error_event, record_tool_event
from pipeline_utils import balanced_mode, build_agent_plan, dedupe, fast_mode

from ..models import ResearchState


def planner_node(state: ResearchState) -> ResearchState:
    """生成检索计划与查询列表。"""

    topic = state.get("topic", "").strip()
    updated = dict(state)

    if fast_mode():
        queries = [topic]
        updated["search_queries"] = queries
        updated["agent_plan"] = build_agent_plan(topic, ["ArXiv"], "fast")
        record_decision(
            updated,
            stage="planner",
            decision="Use original topic only.",
            reason="Fast mode prioritizes speed and disables LLM planning.",
            next_step="searcher",
        )
        updated.setdefault("logs", []).append("Planner fast mode: using original topic only.")
        return updated

    if balanced_mode():
        queries = [topic, f"{topic} benchmark evaluation", f"{topic} survey"]
        updated["search_queries"] = dedupe(queries)
        updated["agent_plan"] = build_agent_plan(topic, ["ArXiv", "DeepSeek ideas"], "balanced")
        record_decision(
            updated,
            stage="planner",
            decision="Use rule-based focused queries.",
            reason="Balanced mode keeps one DeepSeek call for ideas and avoids slow planning.",
            next_step="searcher",
        )
        updated.setdefault("logs", []).append("Planner balanced mode: using rule-based queries.")
        return updated

    prompt = f"""
Please expand the research topic into 3-5 English academic search queries.
Return JSON only: {{"queries": ["...", "..."]}}
Topic: {topic}
"""
    timer = StageTimer()
    data = call_openai_json(
        prompt,
        system="You are an academic search planning assistant. Return valid JSON only.",
    )
    queries: List[str] = []
    if data and isinstance(data.get("queries"), list):
        queries = [str(query).strip() for query in data["queries"] if str(query).strip()]

    if not queries:
        queries = [
            topic,
            f"{topic} survey",
            f"{topic} benchmark evaluation",
            f"{topic} limitations future work",
        ]
        record_error_event(
            updated,
            stage="planner",
            error_type="LLMPlanningFallback",
            message="LLM did not return valid query JSON.",
            recovery="Used rule-based query expansion.",
        )

    updated["search_queries"] = dedupe(queries)[:4]
    updated["agent_plan"] = build_agent_plan(
        topic,
        ["ArXiv", "Semantic Scholar", "DeepSeek", "PDF parser"],
        "full",
    )
    record_tool_event(
        updated,
        tool_name="DeepSeek/OpenAI planner",
        input_summary=topic,
        status="success" if data else "fallback",
        output_count=len(updated["search_queries"]),
        duration_sec=timer.elapsed(),
        note="LLM query expansion" if data else "Rule-based query fallback.",
    )
    record_decision(
        updated,
        stage="planner",
        decision=f"Prepared {len(updated['search_queries'])} search queries.",
        reason="The agent needs survey, benchmark, and limitation coverage before auditing gaps.",
        next_step="searcher",
    )
    updated.setdefault("logs", []).append(f"Planner generated {len(updated['search_queries'])} queries.")
    return updated
