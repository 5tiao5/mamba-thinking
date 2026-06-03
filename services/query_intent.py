from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from product_agent.services.text_cleaning import clean_internal_context_items, clean_internal_context_text


_GOAL_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("compare", ("compare", "comparison", "versus", "vs", "\u5bf9\u6bd4", "\u6bd4\u8f83")),
    (
        "narrow_literature_scope",
        (
            "narrow",
            "focus",
            "zoom in",
            "recent",
            "latest",
            "only",
            "\u7f29\u5c0f",
            "\u805a\u7126",
            "\u8fd1\u4e24\u5e74",
            "\u6700\u8fd1",
            "\u53ea\u770b",
        ),
    ),
    ("survey", ("survey", "review", "overview", "landscape", "\u7efc\u8ff0", "\u8c03\u7814", "\u6982\u89c8")),
    (
        "gap_analysis",
        ("gap", "gaps", "limitation", "limitations", "challenge", "\u7a7a\u767d", "\u5c40\u9650", "\u6311\u6218"),
    ),
    (
        "benchmark_evaluation",
        ("benchmark", "evaluation", "eval", "\u8bc4\u6d4b", "\u8bc4\u4f30", "\u57fa\u51c6"),
    ),
    ("extend_context", ("extend", "expand", "add", "\u6269\u5c55", "\u8865\u5145", "\u52a0\u4e0a")),
)

_PAPER_SCOPE_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("benchmark evaluation", ("benchmark", "evaluation", "eval", "\u8bc4\u6d4b", "\u8bc4\u4f30", "\u57fa\u51c6")),
    ("survey review", ("survey", "review", "overview", "\u7efc\u8ff0", "\u8c03\u7814")),
    ("methods", ("method", "methods", "approach", "technique", "\u65b9\u6cd5", "\u65b9\u6848")),
    ("datasets", ("dataset", "datasets", "corpus", "\u6570\u636e\u96c6", "\u8bed\u6599")),
    ("applications", ("application", "applications", "deployment", "\u5e94\u7528", "\u843d\u5730")),
    ("limitations", ("limitation", "limitations", "failure", "challenge", "\u5c40\u9650", "\u6311\u6218")),
)

_DOMAIN_FOCUS_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("tool use", ("tool use", "tool usage", "tool-using", "\u5de5\u5177\u4f7f\u7528", "\u5de5\u5177\u8c03\u7528")),
    ("tool calling", ("tool calling", "api calling", "function calling", "\u51fd\u6570\u8c03\u7528", "api \u8c03\u7528")),
    ("benchmark evaluation", ("benchmark", "evaluation", "\u8bc4\u6d4b", "\u57fa\u51c6")),
    ("survey review", ("survey", "review", "\u7efc\u8ff0", "\u8c03\u7814")),
    ("rag", ("rag", "retrieval augmented generation")),
    ("code agent", ("code agent", "coding agent", "software engineering agent", "\u4ee3\u7801 agent")),
)

_RECENT_YEAR_PATTERNS: tuple[tuple[int, tuple[str, ...]], ...] = (
    (
        2,
        (
            "last two years",
            "past two years",
            "recent two years",
            "\u8fd1\u4e24\u5e74",
            "\u6700\u8fd1\u4e24\u5e74",
            "\u8fc7\u53bb\u4e24\u5e74",
        ),
    ),
    (
        3,
        (
            "last three years",
            "past three years",
            "recent three years",
            "\u8fd1\u4e09\u5e74",
            "\u6700\u8fd1\u4e09\u5e74",
            "\u8fc7\u53bb\u4e09\u5e74",
        ),
    ),
    (
        5,
        (
            "last five years",
            "past five years",
            "recent five years",
            "\u8fd1\u4e94\u5e74",
            "\u6700\u8fd1\u4e94\u5e74",
            "\u8fc7\u53bb\u4e94\u5e74",
        ),
    ),
)

_ENGLISH_TOKEN_PATTERN = re.compile(r"\b[A-Za-z][A-Za-z0-9+/_-]{1,}\b")
_YEAR_RANGE_PATTERN = re.compile(r"\b(20\d{2})\s*(?:-|~|to)\s*(20\d{2})\b")
_YEAR_AFTER_PATTERN = re.compile(
    r"(20\d{2})\s*(?:and later|or later|onward|after|\u4ee5\u540e|\u4e4b\u540e|\u4ee5\u6765)",
    flags=re.IGNORECASE,
)
_YEAR_BEFORE_PATTERN = re.compile(
    r"(20\d{2})\s*(?:and earlier|or earlier|before|\u4ee5\u524d|\u4e4b\u524d)",
    flags=re.IGNORECASE,
)
_YEAR_LITERAL_PATTERN = re.compile(r"\b(20\d{2})\b")
_META_FOCUS_HINTS = {
    "focus",
    "narrow",
    "recent",
    "latest",
    "survey",
    "review",
    "compare",
    "evaluation",
    "benchmark",
}
_ENGLISH_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "that",
    "this",
    "are",
    "was",
    "were",
    "have",
    "has",
    "been",
    "focus",
    "narrow",
    "latest",
    "recent",
    "years",
    "paper",
    "papers",
    "study",
    "studies",
    "only",
    "into",
    "about",
    "around",
}


@dataclass
class QueryIntent:
    raw_user_request: str
    task_topic: str
    conversation_topic: str
    core_topic: str
    user_goal: str
    knowledge_scope: str
    focus_terms: list[str] = field(default_factory=list)
    paper_scope: list[str] = field(default_factory=list)
    soft_hints: list[str] = field(default_factory=list)
    time_range: dict[str, Any] | None = None
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_user_request": self.raw_user_request,
            "task_topic": self.task_topic,
            "conversation_topic": self.conversation_topic,
            "core_topic": self.core_topic,
            "user_goal": self.user_goal,
            "knowledge_scope": self.knowledge_scope,
            "focus_terms": list(self.focus_terms),
            "paper_scope": list(self.paper_scope),
            "soft_hints": list(self.soft_hints),
            "time_range": dict(self.time_range) if isinstance(self.time_range, dict) else None,
            "summary": self.summary,
        }

    def to_context_input(self) -> dict[str, Any]:
        payload = self.to_dict()
        payload["kind"] = "query_intent"
        return payload


def derive_query_intent(
    *,
    raw_user_request: str,
    task_topic: str,
    conversation_topic: str,
    knowledge_scope: str,
    workspace_hints: list[str] | None = None,
    knowledge_hints: list[str] | None = None,
    recent_context: list[dict[str, Any]] | None = None,
    reference_year: int | None = None,
) -> QueryIntent:
    clean_request = clean_internal_context_text(raw_user_request, max_length=220)
    clean_task_topic = clean_internal_context_text(task_topic, max_length=180)
    clean_conversation_topic = clean_internal_context_text(conversation_topic, max_length=180)
    workspace_clues = clean_internal_context_items(list(workspace_hints or []), max_length=90)
    knowledge_clues = clean_internal_context_items(list(knowledge_hints or []), max_length=90)
    recent_clues = _recent_user_clues(list(recent_context or []))

    combined_text = " ".join(
        part
        for part in (
            clean_request,
            clean_task_topic,
            clean_conversation_topic,
            " ".join(workspace_clues[:2]),
            " ".join(knowledge_clues[:2]),
            " ".join(recent_clues[:2]),
        )
        if part
    ).strip()

    focus_terms = _dedupe(
        [
            *_domain_focus_terms(combined_text),
            *_quoted_or_acronym_terms(clean_request),
        ]
    )
    paper_scope = _dedupe(_matching_labels(combined_text, _PAPER_SCOPE_PATTERNS))
    time_range = _extract_time_range(clean_request or combined_text, reference_year=reference_year)
    user_goal = _infer_user_goal(clean_request or combined_text, time_range=time_range, paper_scope=paper_scope)
    soft_hints = _dedupe([*workspace_clues[:2], *knowledge_clues[:2], *recent_clues[:1]])
    core_topic = clean_conversation_topic or clean_task_topic or clean_request

    intent = QueryIntent(
        raw_user_request=clean_request or clean_task_topic or clean_conversation_topic,
        task_topic=clean_task_topic or clean_conversation_topic,
        conversation_topic=clean_conversation_topic or clean_task_topic,
        core_topic=core_topic,
        user_goal=user_goal,
        knowledge_scope=knowledge_scope or "shared",
        focus_terms=focus_terms[:4],
        paper_scope=paper_scope[:4],
        soft_hints=soft_hints[:4],
        time_range=time_range,
    )
    intent.summary = _build_intent_summary(intent)
    return intent


def build_search_seed(intent: QueryIntent | dict[str, Any], *, fallback_topic: str = "") -> str:
    if isinstance(intent, QueryIntent):
        payload = intent.to_dict()
    else:
        payload = dict(intent or {})

    parts: list[str] = []
    for value in (
        payload.get("core_topic"),
        *list(payload.get("focus_terms", []) or [])[:2],
        *list(payload.get("paper_scope", []) or [])[:2],
    ):
        clean = clean_internal_context_text(value, max_length=140)
        if clean:
            parts.append(clean)

    if not parts:
        return clean_internal_context_text(fallback_topic, max_length=180) or fallback_topic
    return " ".join(_dedupe(parts))


def _infer_user_goal(text: str, *, time_range: dict[str, Any] | None, paper_scope: list[str]) -> str:
    lowered = text.casefold()
    for label, patterns in _GOAL_PATTERNS:
        if any(pattern.casefold() in lowered for pattern in patterns):
            return label
    if time_range:
        return "narrow_literature_scope"
    if "benchmark evaluation" in paper_scope:
        return "benchmark_evaluation"
    return "follow_up"


def _extract_time_range(text: str, *, reference_year: int | None) -> dict[str, Any] | None:
    clean_text = " ".join(str(text).split()).strip()
    if not clean_text:
        return None

    current_year = reference_year or datetime.now(timezone.utc).year
    lowered = clean_text.casefold()

    for lookback_years, patterns in _RECENT_YEAR_PATTERNS:
        if any(pattern.casefold() in lowered for pattern in patterns):
            return {
                "mode": "recent_window",
                "label": f"recent_{lookback_years}_years",
                "lookback_years": lookback_years,
                "start_year": current_year - lookback_years,
                "end_year": current_year,
                "strict": True,
            }

    range_match = _YEAR_RANGE_PATTERN.search(clean_text)
    if range_match:
        start_year, end_year = sorted((int(range_match.group(1)), int(range_match.group(2))))
        return {
            "mode": "year_range",
            "label": f"{start_year}-{end_year}",
            "start_year": start_year,
            "end_year": end_year,
            "strict": True,
        }

    after_match = _YEAR_AFTER_PATTERN.search(clean_text)
    if after_match:
        start_year = int(after_match.group(1))
        return {
            "mode": "year_after",
            "label": f"{start_year}+",
            "start_year": start_year,
            "end_year": current_year,
            "strict": True,
        }

    before_match = _YEAR_BEFORE_PATTERN.search(clean_text)
    if before_match:
        end_year = int(before_match.group(1))
        return {
            "mode": "year_before",
            "label": f"<= {end_year}",
            "start_year": None,
            "end_year": end_year,
            "strict": True,
        }

    explicit_years = sorted({int(match) for match in _YEAR_LITERAL_PATTERN.findall(clean_text)})
    if len(explicit_years) == 1:
        year = explicit_years[0]
        return {
            "mode": "single_year",
            "label": str(year),
            "start_year": year,
            "end_year": year,
            "strict": True,
        }
    return None


def _matching_labels(text: str, patterns: tuple[tuple[str, tuple[str, ...]], ...]) -> list[str]:
    lowered = text.casefold()
    matches: list[str] = []
    for label, hints in patterns:
        if any(hint.casefold() in lowered for hint in hints):
            matches.append(label)
    return matches


def _domain_focus_terms(text: str) -> list[str]:
    terms = _matching_labels(text, _DOMAIN_FOCUS_PATTERNS)
    terms.extend(_technical_english_terms(text))
    return _dedupe(terms)


def _technical_english_terms(text: str) -> list[str]:
    tokens: list[str] = []
    for token in _ENGLISH_TOKEN_PATTERN.findall(text):
        lowered = token.casefold()
        if lowered in _ENGLISH_STOPWORDS or lowered in _META_FOCUS_HINTS:
            continue
        if lowered.startswith("20") and lowered[2:].isdigit():
            continue
        if len(token) <= 2 and token.upper() != token:
            continue
        tokens.append(token)
    return tokens[:5]


def _quoted_or_acronym_terms(text: str) -> list[str]:
    matches = re.findall(r"[\"'](.+?)[\"']", text)
    terms = [match.strip() for match in matches if match.strip()]
    terms.extend(
        token
        for token in _ENGLISH_TOKEN_PATTERN.findall(text)
        if token.upper() == token and len(token) >= 3
    )
    return _dedupe(terms)


def _recent_user_clues(recent_context: list[dict[str, Any]]) -> list[str]:
    clues: list[str] = []
    for entry in recent_context[-3:]:
        if str(entry.get("role", "")).lower() != "user":
            continue
        content = clean_internal_context_text(entry.get("content", ""), max_length=90)
        if content:
            clues.append(content)
    return _dedupe(clues)


def _build_intent_summary(intent: QueryIntent) -> str:
    parts = [f"goal={intent.user_goal}"]
    if intent.paper_scope:
        parts.append("scope=" + ", ".join(intent.paper_scope[:2]))
    if intent.time_range:
        parts.append("time=" + str(intent.time_range.get("label", "")))
    if intent.focus_terms:
        parts.append("focus=" + ", ".join(intent.focus_terms[:2]))
    return "; ".join(part for part in parts if part)


def _dedupe(values: list[str]) -> list[str]:
    items: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = " ".join(str(value).split()).strip()
        if not clean:
            continue
        key = clean.casefold()
        if key in seen:
            continue
        seen.add(key)
        items.append(clean)
    return items
