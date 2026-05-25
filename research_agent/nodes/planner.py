from __future__ import annotations

from typing import List

from llm_client import call_openai_json
from observability import StageTimer, record_decision, record_error_event, record_tool_event
from pipeline_utils import balanced_mode, build_agent_plan, dedupe, fast_mode

from ..models import ResearchState
from ..query_decomposition import build_search_queries, infer_research_facets, is_broad_topic


def planner_node(state: ResearchState) -> ResearchState:
    """生成检索计划与查询列表。"""

    topic = state.get("topic", "").strip()
    updated = dict(state)

    if fast_mode():
        queries = build_search_queries(topic, fast=True)
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
        queries = build_search_queries(topic, balanced=True)
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
Please expand the research topic into 4-6 English academic search queries.
If the topic is broad, decompose it into evidence-seeking facets such as methods, evaluation, applications, limitations, and future directions.
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

    heuristic_queries = build_search_queries(topic, balanced=False)
    if data and queries:
        queries = dedupe([*heuristic_queries, *queries])
    if not queries:
        queries = heuristic_queries
        record_error_event(
            updated,
            stage="planner",
            error_type="LLMPlanningFallback",
            message="LLM did not return valid query JSON.",
            recovery="Used rule-based query expansion.",
        )

    updated["search_queries"] = dedupe(queries)[:6]
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
        note=(
            f"Evidence-oriented query decomposition; broad_topic={is_broad_topic(topic)}; "
            f"facets={', '.join(infer_research_facets(topic)[:4])}"
        ),
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
