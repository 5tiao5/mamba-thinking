from __future__ import annotations

from typing import Any, List

from llm_client import call_openai_json
from observability import StageTimer, record_decision, record_error_event, record_tool_event
from pipeline_utils import balanced_mode, build_agent_plan, dedupe, fast_mode

from ..models import ResearchState
from ..query_decomposition import infer_research_facets, is_broad_topic
from ..retrieval_plan import build_retrieval_plan, summarize_retrieval_plan


def planner_node(state: ResearchState) -> ResearchState:
    """Generate a retrieval plan, then derive grounded search queries from it."""

    intent = _query_intent(state)
    topic = _planner_topic(state, intent)
    workspace_queries = _workspace_context_queries(topic, state.get("conversation_workspace_context", []) or [])
    working_memory_queries = _working_memory_queries(
        topic,
        summary=str(state.get("working_memory_summary", "") or ""),
        findings=state.get("working_memory_findings", []) or [],
        open_questions=state.get("working_memory_open_questions", []) or [],
    )
    knowledge_queries = _knowledge_context_queries(topic, state.get("knowledge_hits", []) or [])
    recent_queries = _recent_context_queries(topic, state.get("recent_context", []) or [])
    retrieval_plan = build_retrieval_plan(
        topic=topic,
        query_intent=intent,
        workspace_queries=dedupe([*workspace_queries, *working_memory_queries]),
        knowledge_queries=knowledge_queries,
        recent_queries=recent_queries,
        mode=str(state.get("mode", "default") or "default"),
    )
    context_note = _context_grounding_note(
        query_intent=intent,
        retrieval_plan=retrieval_plan.to_dict(),
        knowledge_hits=state.get("knowledge_hits", []) or [],
        workspace_hints=state.get("conversation_workspace_context", []) or [],
        working_memory_summary=str(state.get("working_memory_summary", "") or ""),
        working_memory_findings=state.get("working_memory_findings", []) or [],
        working_memory_open_questions=state.get("working_memory_open_questions", []) or [],
        working_memory_constraints=state.get("working_memory_constraints", []) or [],
        recent_context=state.get("recent_context", []) or [],
    )
    updated = dict(state)
    updated["retrieval_plan"] = retrieval_plan.to_dict()

    if fast_mode(state):
        queries = _queries_for_mode(retrieval_plan, mode="fast")
        updated["search_queries"] = queries
        updated["agent_plan"] = _augment_agent_plan(build_agent_plan(topic, ["ArXiv"], "fast"), context_note)
        record_decision(
            updated,
            stage="planner",
            decision="Use a compact retrieval plan.",
            reason="Fast mode keeps planning cheap while still preserving hard constraints and rerank signals.",
            next_step="searcher",
        )
        updated.setdefault("logs", []).append(
            "Planner fast mode: built retrieval plan with "
            + (summarize_retrieval_plan(retrieval_plan) or "basic grounded defaults")
            + "."
        )
        return updated

    if balanced_mode(state):
        queries = _queries_for_mode(retrieval_plan, mode="balanced")
        updated["search_queries"] = queries
        updated["agent_plan"] = _augment_agent_plan(
            build_agent_plan(topic, ["ArXiv", "DeepSeek ideas"], "balanced"),
            context_note,
        )
        record_decision(
            updated,
            stage="planner",
            decision="Use a focused retrieval plan.",
            reason="Balanced mode preserves core constraints while limiting query count for runtime stability.",
            next_step="searcher",
        )
        updated.setdefault("logs", []).append(
            "Planner balanced mode: built retrieval plan with "
            + (summarize_retrieval_plan(retrieval_plan) or "grounded defaults")
            + "."
        )
        return updated

    prompt = f"""
Please expand the retrieval plan into 4-6 English academic search queries.
Respect the hard constraints in the context, especially time windows and paper scope.
Use the existing plan as the baseline rather than restarting from zero.
Return JSON only: {{"queries": ["...", "..."]}}
Topic: {topic}
Context:
{_planner_context_block(state, retrieval_plan.to_dict())}
"""
    timer = StageTimer()
    data = call_openai_json(
        prompt,
        system="You are an academic search planning assistant. Return valid JSON only.",
    )
    llm_queries: List[str] = []
    if data and isinstance(data.get("queries"), list):
        llm_queries = [str(query).strip() for query in data["queries"] if str(query).strip()]

    heuristic_queries = retrieval_plan.all_queries()
    queries = dedupe([*heuristic_queries, *llm_queries]) if llm_queries else heuristic_queries
    if not llm_queries:
        record_error_event(
            updated,
            stage="planner",
            error_type="LLMPlanningFallback",
            message="LLM did not return valid retrieval plan query JSON.",
            recovery="Used grounded retrieval plan queries.",
        )

    updated["search_queries"] = queries[:6]
    updated["agent_plan"] = _augment_agent_plan(
        build_agent_plan(
            topic,
            ["ArXiv", "Semantic Scholar", "DeepSeek", "PDF parser"],
            "full",
        ),
        context_note,
    )
    record_tool_event(
        updated,
        tool_name="DeepSeek/OpenAI planner",
        input_summary=topic,
        status="success" if data else "fallback",
        output_count=len(updated["search_queries"]),
        duration_sec=timer.elapsed(),
        note=(
            f"retrieval_plan={summarize_retrieval_plan(retrieval_plan) or 'basic'}; "
            f"broad_topic={is_broad_topic(topic)}; facets={', '.join(infer_research_facets(topic)[:4])}"
        ),
    )
    record_decision(
        updated,
        stage="planner",
        decision=f"Prepared retrieval plan with {len(updated['search_queries'])} search queries.",
        reason="The agent needs structured retrieval before taxonomy and graph construction.",
        next_step="searcher",
    )
    updated.setdefault("logs", []).append(
        "Planner full mode: built retrieval plan with "
        + (summarize_retrieval_plan(retrieval_plan) or "grounded defaults")
        + "."
    )
    return updated


def _query_intent(state: ResearchState) -> dict[str, Any]:
    raw = state.get("query_intent", {}) or {}
    return raw if isinstance(raw, dict) else {}


def _planner_topic(state: ResearchState, query_intent: dict[str, Any]) -> str:
    core_topic = " ".join(str(query_intent.get("core_topic", "")).split()).strip()
    if core_topic:
        return core_topic
    return " ".join(str(state.get("topic", "")).split()).strip()


def _queries_for_mode(plan, *, mode: str) -> list[str]:
    if mode == "fast":
        return dedupe([*plan.strict_queries[:2], *plan.broad_queries[:1]])[:3]
    if mode == "balanced":
        return dedupe([*plan.strict_queries[:3], *plan.broad_queries[:2]])[:5]
    return plan.all_queries()


def _augment_agent_plan(agent_plan: str, context_note: str) -> str:
    if not context_note:
        return agent_plan
    return f"{agent_plan} {context_note}".strip()


def _planner_context_block(state: ResearchState, retrieval_plan: dict[str, Any]) -> str:
    lines: list[str] = []
    query_intent = _query_intent(state)

    user_goal = " ".join(str(query_intent.get("user_goal", "")).split()).strip()
    if user_goal:
        lines.append(f"- User goal: {user_goal}")

    time_range = query_intent.get("time_range") if isinstance(query_intent.get("time_range"), dict) else None
    if time_range:
        label = " ".join(str(time_range.get("label", "")).split()).strip()
        if label:
            lines.append(f"- Time constraint: {label}")

    plan_summary = summarize_retrieval_plan(retrieval_plan)
    if plan_summary:
        lines.append(f"- Retrieval plan: {plan_summary}")

    strict_queries = [str(query).strip() for query in list(retrieval_plan.get("strict_queries", []) or [])[:3] if str(query).strip()]
    if strict_queries:
        lines.append(f"- Strict queries: {' | '.join(strict_queries)}")

    paper_scope = [
        str(scope).strip()
        for scope in list(query_intent.get("paper_scope", []) or [])[:3]
        if str(scope).strip()
    ]
    if paper_scope:
        lines.append(f"- Paper scope: {', '.join(paper_scope)}")

    focus_terms = [
        str(term).strip()
        for term in list(query_intent.get("focus_terms", []) or [])[:3]
        if str(term).strip()
    ]
    if focus_terms:
        lines.append(f"- Focus terms: {', '.join(focus_terms)}")

    workspace_summary = str(state.get("conversation_workspace_summary", "") or "").strip()
    if workspace_summary:
        lines.append(f"- Workspace summary: {workspace_summary[:220]}")

    working_memory_summary = str(state.get("working_memory_summary", "") or "").strip()
    if working_memory_summary:
        lines.append(f"- Working memory summary: {working_memory_summary[:220]}")

    for finding in (state.get("working_memory_findings", []) or [])[:3]:
        clean_finding = " ".join(str(finding).split()).strip()
        if clean_finding:
            lines.append(f"- Working memory finding: {clean_finding}")

    for question in (state.get("working_memory_open_questions", []) or [])[:2]:
        clean_question = " ".join(str(question).split()).strip()
        if clean_question:
            lines.append(f"- Open question: {clean_question}")

    for constraint in (state.get("working_memory_constraints", []) or [])[:3]:
        clean_constraint = " ".join(str(constraint).split()).strip()
        if clean_constraint:
            lines.append(f"- Active constraint: {clean_constraint}")

    for hint in (state.get("conversation_workspace_context", []) or [])[:3]:
        clean_hint = " ".join(str(hint).split()).strip()
        if clean_hint:
            lines.append(f"- Workspace hint: {clean_hint}")

    for hit in (state.get("knowledge_hits", []) or [])[:3]:
        title = " ".join(str(hit.get("title", "")).split()).strip()
        snippet = " ".join(str(hit.get("snippet", "")).split()).strip()
        if title:
            lines.append(f"- Knowledge hit: {title}")
        if snippet:
            lines.append(f"- Knowledge clue: {snippet[:160]}")

    for entry in (state.get("recent_context", []) or [])[-3:]:
        if str(entry.get("role", "")).lower() != "user":
            continue
        content = " ".join(str(entry.get("content", "")).split()).strip()
        if content:
            lines.append(f"- Recent user turn: {content[:160]}")

    if not lines:
        return "- No prior context provided."
    return "\n".join(lines)


def _workspace_context_queries(topic: str, hints: list[str]) -> list[str]:
    clean_topic = " ".join(str(topic).split()).strip()
    queries: list[str] = []
    for hint in hints[:3]:
        clean_hint = " ".join(str(hint).split()).strip()
        if not clean_hint:
            continue
        queries.append(f"{clean_topic} {clean_hint}")
    return dedupe(queries)


def _knowledge_context_queries(topic: str, hits: list[dict[str, Any]]) -> list[str]:
    clean_topic = " ".join(str(topic).split()).strip()
    queries: list[str] = []
    for hit in hits[:2]:
        title = " ".join(str(hit.get("title", "")).split()).strip()
        snippet = " ".join(str(hit.get("snippet", "")).split()).strip()
        if title:
            queries.append(f"{clean_topic} {title[:120]}")
        if snippet:
            queries.append(f"{clean_topic} {snippet[:120]}")
    return dedupe(queries)


def _recent_context_queries(topic: str, recent_context: list[dict[str, Any]]) -> list[str]:
    clean_topic = " ".join(str(topic).split()).strip()
    queries: list[str] = []
    for entry in recent_context[-3:]:
        if str(entry.get("role", "")).lower() != "user":
            continue
        content = " ".join(str(entry.get("content", "")).split()).strip()
        if not content:
            continue
        queries.append(f"{clean_topic} {content[:120]}")
    return dedupe(queries)


def _working_memory_queries(
    topic: str,
    *,
    summary: str,
    findings: list[str],
    open_questions: list[str],
) -> list[str]:
    clean_topic = " ".join(str(topic).split()).strip()
    queries: list[str] = []
    clean_summary = " ".join(str(summary).split()).strip()
    if clean_summary:
        queries.append(f"{clean_topic} {clean_summary[:120]}")
    for finding in findings[:2]:
        clean_finding = " ".join(str(finding).split()).strip()
        if clean_finding:
            queries.append(f"{clean_topic} {clean_finding[:120]}")
    for question in open_questions[:1]:
        clean_question = " ".join(str(question).split()).strip()
        if clean_question:
            queries.append(f"{clean_topic} {clean_question[:120]}")
    return dedupe(queries)


def _context_grounding_note(
    *,
    query_intent: dict[str, Any],
    retrieval_plan: dict[str, Any],
    knowledge_hits: list[dict[str, Any]],
    workspace_hints: list[str],
    working_memory_summary: str,
    working_memory_findings: list[str],
    working_memory_open_questions: list[str],
    working_memory_constraints: list[str],
    recent_context: list[dict[str, Any]],
) -> str:
    user_turns = sum(1 for entry in recent_context if str(entry.get("role", "")).lower() == "user")
    parts: list[str] = []
    if query_intent:
        goal = " ".join(str(query_intent.get("user_goal", "")).split()).strip()
        time_range = query_intent.get("time_range") if isinstance(query_intent.get("time_range"), dict) else None
        if goal and goal != "follow_up":
            parts.append(f"goal={goal}")
        if time_range and str(time_range.get("label", "")).strip():
            parts.append(f"time={str(time_range.get('label', '')).strip()}")
    plan_summary = summarize_retrieval_plan(retrieval_plan)
    if plan_summary:
        parts.append(f"plan={plan_summary}")
    if knowledge_hits:
        parts.append(f"{len(knowledge_hits)} knowledge hits")
    if workspace_hints:
        parts.append(f"{len(workspace_hints)} workspace hints")
    if working_memory_summary:
        parts.append("explicit working memory")
    if working_memory_findings:
        parts.append(f"{len(working_memory_findings)} stable findings")
    if working_memory_open_questions:
        parts.append(f"{len(working_memory_open_questions)} open questions")
    if working_memory_constraints:
        parts.append(f"{len(working_memory_constraints)} active constraints")
    if user_turns:
        parts.append(f"{user_turns} recent user turns")
    if not parts:
        return ""
    return "Context grounding: " + ", ".join(parts) + "."
