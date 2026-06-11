from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any

from .query_decomposition import build_search_queries


@dataclass
class RetrievalPlan:
    topic: str
    user_goal: str = "follow_up"
    strict_queries: list[str] = field(default_factory=list)
    broad_queries: list[str] = field(default_factory=list)
    recall_queries: list[str] = field(default_factory=list)
    filters: dict[str, Any] = field(default_factory=dict)
    rerank_signals: list[str] = field(default_factory=list)
    strategy_note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "user_goal": self.user_goal,
            "strict_queries": list(self.strict_queries),
            "broad_queries": list(self.broad_queries),
            "recall_queries": list(self.recall_queries),
            "filters": dict(self.filters),
            "rerank_signals": list(self.rerank_signals),
            "strategy_note": self.strategy_note,
        }

    def all_queries(self) -> list[str]:
        return _dedupe([*self.strict_queries, *self.broad_queries])


def build_retrieval_plan(
    *,
    topic: str,
    query_intent: dict[str, Any] | None,
    workspace_queries: list[str] | None = None,
    knowledge_queries: list[str] | None = None,
    recent_queries: list[str] | None = None,
    mode: str = "default",
) -> RetrievalPlan:
    intent = dict(query_intent or {})
    clean_topic = " ".join(str(intent.get("core_topic", "") or topic).split()).strip() or str(topic).strip()
    user_goal = " ".join(str(intent.get("user_goal", "follow_up")).split()).strip() or "follow_up"
    focus_terms = _clean_items(list(intent.get("focus_terms", []) or [])[:3])
    paper_scope = _clean_items(list(intent.get("paper_scope", []) or [])[:3])
    rerank_signals = _dedupe([*focus_terms, *paper_scope])

    family_strict, family_broad, family_recall = _academic_query_family(
        clean_topic,
        focus_terms=focus_terms,
        paper_scope=paper_scope,
    )
    strict_queries = [*family_strict, clean_topic]
    for focus in focus_terms[:2]:
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
        user_goal=user_goal,
        strict_queries=_dedupe(strict_queries),
        broad_queries=_dedupe(broad_queries),
        recall_queries=_dedupe(
            [
                *family_recall,
                *_compact_recall_queries(focus_terms, paper_scope),
            ]
        )[:4],
        filters=filters,
        rerank_signals=rerank_signals,
        strategy_note=strategy_note,
    )


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


def relevance_query(plan: dict[str, Any] | RetrievalPlan, *, fallback_topic: str = "") -> str:
    payload = plan.to_dict() if isinstance(plan, RetrievalPlan) else dict(plan or {})
    topic = " ".join(str(payload.get("topic", "") or fallback_topic).split()).strip()
    rerank_signals = _clean_items(list(payload.get("rerank_signals", []) or [])[:3])
    return " ".join(_dedupe([topic, *rerank_signals])).strip() or topic or fallback_topic


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


def _dedupe(items: list[str]) -> list[str]:
    return _clean_items(items)


def _as_year(value: Any) -> int | None:
    text = str(value or "").strip()
    if text.isdigit() and len(text) == 4:
        return int(text)
    if isinstance(value, int):
        return value
    return None
