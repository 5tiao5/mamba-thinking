from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any

from .query_decomposition import build_search_queries


@dataclass
class RetrievalPlan:
    topic: str
    topic_anchor: str = ""
    user_goal: str = "follow_up"
    focus_facets: list[dict[str, Any]] = field(default_factory=list)
    strict_queries: list[str] = field(default_factory=list)
    broad_queries: list[str] = field(default_factory=list)
    recall_queries: list[str] = field(default_factory=list)
    filters: dict[str, Any] = field(default_factory=dict)
    rerank_signals: list[str] = field(default_factory=list)
    query_coverage: dict[str, Any] = field(default_factory=dict)
    strategy_note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "topic_anchor": self.topic_anchor,
            "user_goal": self.user_goal,
            "focus_facets": [dict(facet) for facet in self.focus_facets],
            "strict_queries": list(self.strict_queries),
            "broad_queries": list(self.broad_queries),
            "recall_queries": list(self.recall_queries),
            "filters": dict(self.filters),
            "rerank_signals": list(self.rerank_signals),
            "query_coverage": dict(self.query_coverage),
            "strategy_note": self.strategy_note,
        }

    def all_queries(self) -> list[str]:
        return _dedupe([*self.strict_queries, *self.broad_queries])


def build_retrieval_plan(
    *,
    topic: str,
    query_intent: dict[str, Any] | None,
    evidence_queries: list[str] | None = None,
    workspace_queries: list[str] | None = None,
    knowledge_queries: list[str] | None = None,
    recent_queries: list[str] | None = None,
    mode: str = "default",
) -> RetrievalPlan:
    intent = dict(query_intent or {})
    clean_topic = " ".join(str(intent.get("core_topic", "") or topic).split()).strip() or str(topic).strip()
    user_goal = " ".join(str(intent.get("user_goal", "follow_up")).split()).strip() or "follow_up"
    raw_user_request = " ".join(str(intent.get("raw_user_request", "") or "").split()).strip()
    focus_facets = _clean_focus_facets(intent.get("focus_facets", []))
    facet_labels = [
        str(facet.get("label", ""))
        for facet in focus_facets
        if str(facet.get("label", "")).strip()
    ]
    facet_search_terms = _clean_items(
        [
            term
            for facet in focus_facets
            for term in list(facet.get("search_terms", []) or [])
        ]
    )
    facet_queries = _clean_items(
        [
            query
            for facet in focus_facets
            for query in list(facet.get("query_candidates", []) or [])
        ]
    )
    request_focus_terms = _clean_items(
        [
            *facet_labels,
            *list(intent.get("request_focus_terms", []) or []),
        ][:6]
    )
    focus_terms = _clean_items(
        [
            *facet_labels,
            *list(intent.get("focus_terms", []) or []),
        ][:6]
    )
    paper_scope = _clean_items(list(intent.get("paper_scope", []) or [])[:3])
    rerank_signals = _dedupe([*facet_search_terms, *focus_terms, *paper_scope])

    family_strict, family_broad, family_recall = _academic_query_family(
        clean_topic,
        focus_terms=focus_terms,
        paper_scope=paper_scope,
    )
    topic_alias_queries = _topic_alias_queries(clean_topic)
    topic_anchor = _topic_search_anchor(clean_topic, topic_alias_queries)
    for facet in focus_facets:
        candidates = [
            _anchor_query(query, topic_anchor)
            for query in list(facet.get("query_candidates", []) or [])
            if str(query).strip()
        ]
        if candidates:
            facet["query_candidates"] = candidates
    facet_queries = _clean_items(
        [
            query
            for facet in focus_facets
            for query in list(facet.get("query_candidates", []) or [])
        ]
    )
    grounded_evidence_queries = _clean_items(list(evidence_queries or []))
    is_follow_up = bool(
        raw_user_request
        and _normalize_query_text(raw_user_request) != _normalize_query_text(clean_topic)
    )
    priority_queries = (
        _follow_up_priority_queries(
            topic_anchor=topic_anchor,
            request_focus_terms=request_focus_terms,
            user_goal=user_goal,
        )
        if is_follow_up
        else []
    )
    strict_queries = [
        *priority_queries,
        *facet_queries,
        *topic_alias_queries[:1],
        *grounded_evidence_queries[:2],
        *topic_alias_queries[1:],
        *family_strict,
        clean_topic,
    ]
    for focus in focus_terms[:2]:
        if _english_search_terms(focus):
            strict_queries.append(f"{clean_topic} {focus}")
    for scope in paper_scope[:2]:
        strict_queries.append(f"{clean_topic} {scope}")
    if focus_terms and paper_scope:
        strict_queries.append(f"{clean_topic} {focus_terms[0]} {paper_scope[0]}")

    broad_queries = [
        *family_broad,
        *build_search_queries(clean_topic, fast=(mode == "fast"), balanced=(mode == "balanced")),
        *(workspace_queries or []),
        *(knowledge_queries or []),
        *(recent_queries or []),
    ]

    filters = _filters_from_intent(intent)
    strategy_note = _strategy_note(user_goal=user_goal, filters=filters, rerank_signals=rerank_signals)
    return RetrievalPlan(
        topic=clean_topic,
        topic_anchor=topic_anchor,
        user_goal=user_goal,
        focus_facets=focus_facets,
        strict_queries=_dedupe(strict_queries),
        broad_queries=_dedupe(broad_queries),
        recall_queries=_dedupe(
            [
                *family_recall,
                *[
                    _anchor_query(query, topic_anchor)
                    for query in _compact_recall_queries(
                        [*facet_search_terms, *focus_terms],
                        paper_scope,
                    )
                ],
            ]
        )[:4],
        filters=filters,
        rerank_signals=rerank_signals,
        strategy_note=strategy_note,
    )


def _follow_up_priority_queries(
    *,
    topic_anchor: str,
    request_focus_terms: list[str],
    user_goal: str,
) -> list[str]:
    focuses = {item.casefold() for item in request_focus_terms}
    queries: list[str] = []

    if "failure recovery" in focuses:
        if _is_agent_tool_anchor(topic_anchor):
            queries.extend(
                [
                    "LLM agent tool use failure recovery evaluation",
                    "tool calling error recovery robustness benchmark",
                ]
            )
        else:
            queries.extend(
                [
                    f"{topic_anchor} failure recovery evaluation",
                    f"{topic_anchor} error recovery robustness benchmark",
                ]
            )

    efficiency_focuses = {
        "cost efficiency",
        "latency",
        "task success rate",
    }
    if focuses & efficiency_focuses:
        if _is_agent_tool_anchor(topic_anchor):
            queries.extend(
                [
                    "LLM agent tool use cost latency task success rate evaluation",
                    "tool calling efficiency versus task success benchmark",
                ]
            )
        else:
            queries.extend(
                [
                    f"{topic_anchor} cost latency task success rate evaluation",
                    f"{topic_anchor} efficiency versus task success benchmark",
                ]
            )

    if "tool selection" in focuses and not queries:
        queries.append(f"{topic_anchor} tool selection function calling evaluation")

    if not queries and request_focus_terms:
        compact = " ".join(
            term
            for term in request_focus_terms[:3]
            if _english_search_terms(term)
        )
        if compact:
            suffix = " evaluation" if user_goal == "benchmark_evaluation" else ""
            queries.append(f"{topic_anchor} {compact}{suffix}")

    if user_goal == "compare" and len(queries) > 2:
        return _dedupe(queries)[:2]
    return _dedupe(queries)


def _academic_query_family(
    topic: str,
    *,
    focus_terms: list[str],
    paper_scope: list[str],
) -> tuple[list[str], list[str], list[str]]:
    base = _english_search_terms(topic)
    combined = " ".join([topic, *focus_terms, *paper_scope]).casefold()
    strict: list[str] = []
    broad: list[str] = []
    recall: list[str] = []

    if _contains_any(
        combined,
        (
            "agent-centric",
            "agent centric",
            "agent-oriented",
            "agent oriented",
            "software development methodology",
            "development methodologies",
            "agent methodology",
        ),
    ):
        strict.extend(
            [
                "agentic software engineering methodology",
                "AI agent software development lifecycle",
                "multi-agent software development process",
            ]
        )
        broad.extend(
            [
                "agent-oriented software engineering",
                "AI agent teams development workflow",
                "agentic development methodology",
            ]
        )
        recall.extend(
            [
                "agent software development methodology",
                "agentic software lifecycle",
                "multi-agent development process",
            ]
        )

    if _contains_any(
        combined,
        (
            "scientific research assistant",
            "research assistant",
            "scientific literature",
            "literature synthesis",
            "literature review",
            "evidence citation",
            "scholarly",
        ),
    ) and _contains_any(combined, ("retrieval augmented", "retrieval-augmented", "rag")):
        strict.extend(
            [
                "scientific literature synthesis retrieval augmented",
                "research assistant evidence citation RAG",
                "automated literature review retrieval augmented",
            ]
        )
        broad.extend(
            [
                "scientific research agent grounded citations",
                "literature review agent retrieval evidence",
                "scholarly question answering citation attribution",
            ]
        )
        recall.extend(
            [
                "scholarly research assistant citation",
                "literature review agent",
                "scientific literature source attribution",
            ]
        )
    elif _contains_any(
        combined,
        (
            "scientific research assistant",
            "research assistant",
            "scientific literature",
            "literature synthesis",
            "literature review",
            "verifiable citation",
            "evidence citation",
            "scholarly",
        ),
    ):
        strict.extend(
            [
                "scientific literature synthesis retrieval augmented",
                "research assistant scholarly papers verifiable citations",
                "automated paper reading literature synthesis agent",
            ]
        )
        broad.extend(
            [
                "automated literature review citation reliability",
                "scientific research agent source attribution",
                "literature review assistant grounded citations",
            ]
        )
        recall.extend(
            [
                "scholarly research assistant citation",
                "literature review agent",
                "paper reading assistant",
            ]
        )

    if _contains_any(combined, ("tool use", "tool usage", "tool-using", "工具使用", "工具调用")):
        strict.extend(
            [
                "LLM agent tool use evaluation",
                "tool-using language agents benchmark",
            ]
        )
        broad.extend(
            [
                "agent tool calling reliability",
                "function calling robustness benchmark",
                "API tool use failure modes agents",
            ]
        )
        recall.extend(
            [
                "agent tool calling",
                "tool-using agents benchmark",
                "function calling robustness",
            ]
        )
    elif _contains_any(combined, ("tool calling", "function calling", "api calling", "函数调用")):
        strict.extend(
            [
                "agent tool calling evaluation",
                "function calling benchmark language models",
            ]
        )
        broad.extend(
            [
                "function calling robustness",
                "API calling failure modes agents",
            ]
        )
        recall.extend(
            [
                "agent function calling",
                "tool calling benchmark",
                "function calling robustness",
            ]
        )

    if _contains_any(combined, ("code agent", "coding agent", "software engineering agent", "代码 agent")):
        strict.append("software engineering agents evaluation benchmark")
        broad.extend(["coding agents benchmark", "repository agents evaluation"])
        recall.extend(["software engineering agents", "coding agent benchmark"])

    if _contains_any(combined, ("benchmark", "evaluation", "评测", "评估", "基准")):
        if base:
            strict.append(f"{base} benchmark evaluation")
            broad.append(f"{base} reliability robustness failure modes")
    elif base:
        strict.append(base)

    return _dedupe(strict)[:4], _dedupe(broad)[:5], _dedupe(recall)[:4]


def _topic_alias_queries(topic: str) -> list[str]:
    """Provide deterministic English anchors for common Chinese research topics."""

    compact = re.sub(r"\s+", "", str(topic or "")).casefold()
    queries: list[str] = []
    if (
        "agent" in compact
        and (
            "\u5de5\u5177\u4f7f\u7528" in compact
            or "\u5de5\u5177\u8c03\u7528" in compact
            or "tooluse" in compact
            or "toolcalling" in compact
        )
    ):
        queries.extend(
            [
                "LLM agent tool use",
                "tool calling language agents",
            ]
        )
    elif "大模型" in compact and "多模态" in compact:
        queries.extend(
            [
                "multimodal large language model fusion",
                "vision language multimodal fusion",
            ]
        )
    elif "多模态" in compact and "融合" in compact:
        queries.extend(
            [
                "multimodal fusion",
                "adaptive multimodal fusion",
            ]
        )
    return _dedupe(queries)


def _topic_search_anchor(topic: str, aliases: list[str] | None = None) -> str:
    candidates = list(aliases or _topic_alias_queries(topic))
    if candidates:
        return candidates[0]
    english_topic = _english_search_terms(topic)
    return english_topic or " ".join(str(topic).split()).strip()


def _is_agent_tool_anchor(topic_anchor: str) -> bool:
    lowered = str(topic_anchor or "").casefold()
    return "agent" in lowered and ("tool" in lowered or "function calling" in lowered)


def _anchor_query(query: str, topic_anchor: str) -> str:
    clean_query = " ".join(str(query).split()).strip()
    clean_anchor = " ".join(str(topic_anchor).split()).strip()
    if not clean_query or not clean_anchor:
        return clean_query or clean_anchor
    query_tokens = set(_english_search_terms(clean_query).split())
    anchor_tokens = set(_english_search_terms(clean_anchor).split())
    distinctive_anchor_tokens = anchor_tokens - {
        "large",
        "language",
        "model",
        "models",
        "method",
        "methods",
        "evaluation",
    }
    overlap = query_tokens & distinctive_anchor_tokens
    if clean_anchor.casefold() in clean_query.casefold() or (
        "multimodal" in overlap
        or len(overlap) >= 2
    ):
        return clean_query
    return f"{clean_anchor} {clean_query}"


def _compact_recall_queries(
    focus_terms: list[str],
    paper_scope: list[str],
) -> list[str]:
    compact: list[str] = []
    for item in [*focus_terms, *paper_scope]:
        terms = _english_search_terms(item).split()
        if 2 <= len(terms) <= 5:
            compact.append(" ".join(terms))
    return _dedupe(compact)


def _english_search_terms(text: str) -> str:
    stopwords = {
        "the", "and", "for", "with", "from", "that", "this", "are", "was",
        "were", "have", "has", "been", "recent", "latest", "paper", "papers",
        "study", "studies", "research", "only", "into", "about", "around",
    }
    tokens = [
        token.casefold()
        for token in re.findall(r"[A-Za-z][A-Za-z0-9-]{1,}", str(text or ""))
        if token.casefold() not in stopwords
    ]
    return " ".join(list(dict.fromkeys(tokens))[:6])


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(needle.casefold() in text for needle in needles)


def _normalize_query_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").casefold()).strip()


def relevance_query(plan: dict[str, Any] | RetrievalPlan, *, fallback_topic: str = "") -> str:
    payload = plan.to_dict() if isinstance(plan, RetrievalPlan) else dict(plan or {})
    topic = " ".join(str(payload.get("topic", "") or fallback_topic).split()).strip()
    rerank_signals = _clean_items(list(payload.get("rerank_signals", []) or [])[:3])
    strict_queries = _clean_items(list(payload.get("strict_queries", []) or [])[:2])
    return (
        " ".join(_dedupe([topic, *strict_queries, *rerank_signals])).strip()
        or topic
        or fallback_topic
    )


def summarize_retrieval_plan(plan: dict[str, Any] | RetrievalPlan) -> str:
    payload = plan.to_dict() if isinstance(plan, RetrievalPlan) else dict(plan or {})
    filters = payload.get("filters", {}) if isinstance(payload.get("filters"), dict) else {}
    parts = []
    user_goal = " ".join(str(payload.get("user_goal", "")).split()).strip()
    if user_goal and user_goal != "follow_up":
        parts.append(f"goal={user_goal}")
    year_filter = filters.get("year_range") if isinstance(filters.get("year_range"), dict) else None
    if year_filter:
        start = year_filter.get("start_year")
        end = year_filter.get("end_year")
        if start or end:
            parts.append(f"years={start or '*'}-{end or '*'}")
    rerank_signals = _clean_items(list(payload.get("rerank_signals", []) or [])[:2])
    if rerank_signals:
        parts.append("signals=" + ", ".join(rerank_signals))
    return "; ".join(parts)


def _filters_from_intent(intent: dict[str, Any]) -> dict[str, Any]:
    filters: dict[str, Any] = {}
    time_range = intent.get("time_range")
    if isinstance(time_range, dict):
        start_year = _as_year(time_range.get("start_year"))
        end_year = _as_year(time_range.get("end_year"))
        if start_year or end_year:
            filters["year_range"] = {
                "start_year": start_year,
                "end_year": end_year,
                "strict": bool(time_range.get("strict", True)),
            }
    return filters


def _strategy_note(*, user_goal: str, filters: dict[str, Any], rerank_signals: list[str]) -> str:
    parts = []
    if user_goal and user_goal != "follow_up":
        parts.append(f"goal={user_goal}")
    if "year_range" in filters:
        parts.append("apply_year_filter")
    if rerank_signals:
        parts.append(f"rerank={', '.join(rerank_signals[:2])}")
    return "; ".join(parts)


def _clean_items(items: list[Any]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = " ".join(str(item).split()).strip()
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(text)
    return cleaned


def _clean_focus_facets(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    facets: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            continue
        label = " ".join(str(item.get("label", "")).split()).strip()
        if not label:
            continue
        key = label.casefold()
        if key in seen:
            continue
        seen.add(key)
        facets.append(
            _copy_focus_facet_fields(item, {
                "label": label,
                "kind": str(item.get("kind", "research_dimension") or "research_dimension"),
                "source": str(item.get("source", "explicit_user") or "explicit_user"),
                "required": bool(item.get("required", True)),
            })
        )
    return facets[:6]


def _copy_focus_facet_fields(
    source: dict[str, Any],
    target: dict[str, Any],
) -> dict[str, Any]:
    search_terms = _clean_items(list(source.get("search_terms", []) or []))[:2]
    query_candidates = _clean_items(list(source.get("query_candidates", []) or []))[:2]
    expansion_source = " ".join(str(source.get("expansion_source", "")).split()).strip()
    if search_terms:
        target["search_terms"] = search_terms
    if query_candidates:
        target["query_candidates"] = query_candidates
    if expansion_source:
        target["expansion_source"] = expansion_source
    return target


def _dedupe(items: list[str]) -> list[str]:
    return _clean_items(items)


def _as_year(value: Any) -> int | None:
    text = str(value or "").strip()
    if text.isdigit() and len(text) == 4:
        return int(text)
    if isinstance(value, int):
        return value
    return None
