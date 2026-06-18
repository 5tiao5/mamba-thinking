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
    (
        "extend_context",
        (
            "extend",
            "expand",
            "add",
            "\u7ee7\u7eed",
            "\u7ee7\u7eed\u5c55\u5f00",
            "\u5c55\u5f00",
            "\u6df1\u5165",
            "\u6df1\u5316",
            "\u6269\u5c55",
            "\u8865\u5145",
            "\u52a0\u4e0a",
        ),
    ),
)

_PAPER_SCOPE_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("benchmark evaluation", ("benchmark", "evaluation", "eval", "\u8bc4\u6d4b", "\u8bc4\u4f30", "\u57fa\u51c6")),
    ("survey review", ("survey", "review", "overview", "\u7efc\u8ff0")),
    ("methods", ("method", "methods", "approach", "technique", "\u65b9\u6cd5", "\u65b9\u6848")),
    ("datasets", ("dataset", "datasets", "corpus", "\u6570\u636e\u96c6", "\u8bed\u6599")),
    ("applications", ("application", "applications", "deployment", "\u5e94\u7528", "\u843d\u5730")),
    ("limitations", ("limitation", "limitations", "failure", "challenge", "\u5c40\u9650", "\u6311\u6218")),
)

_DOMAIN_FOCUS_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("public datasets", ("public dataset", "public datasets", "\u516c\u5f00\u6570\u636e\u96c6")),
    ("evaluation metrics", ("evaluation metric", "evaluation metrics", "\u8bc4\u4ef7\u6307\u6807", "\u8bc4\u6d4b\u6307\u6807")),
    ("ablation studies", ("ablation study", "ablation studies", "ablation experiment", "\u6d88\u878d\u5b9e\u9a8c")),
    ("robot vision", ("robot vision", "robotic vision", "robot perception", "\u673a\u5668\u4eba\u89c6\u89c9", "\u673a\u5668\u4eba\u611f\u77e5")),
    ("lightweight", ("lightweight", "efficient", "efficiency", "edge deployment", "mobile deployment", "\u8f7b\u91cf\u7ea7", "\u8f7b\u91cf\u5316", "\u9ad8\u6548", "\u8fb9\u7f18\u90e8\u7f72")),
    ("fusion architecture", ("fusion architecture", "multimodal fusion architecture", "fusion network", "\u878d\u5408\u67b6\u6784", "\u878d\u5408\u7ed3\u6784", "\u67b6\u6784\u8bbe\u8ba1")),
    ("cross-modal alignment", ("cross-modal alignment", "vision-language alignment", "modality alignment", "\u8de8\u6a21\u6001\u5bf9\u9f50", "\u6a21\u6001\u5bf9\u9f50")),
    (
        "missing modality robustness",
        (
            "missing modality",
            "incomplete multimodal",
            "missing modality robustness",
            "\u7f3a\u5931\u6a21\u6001",
            "\u6a21\u6001\u7f3a\u5931",
            "\u7f3a\u5931\u6a21\u6001\u9c81\u68d2",
        ),
    ),
    ("multimodal retrieval", ("multimodal retrieval", "cross-modal retrieval", "image text retrieval", "\u591a\u6a21\u6001\u68c0\u7d22", "\u8de8\u6a21\u6001\u68c0\u7d22")),
    ("causal reasoning", ("causal reasoning", "causal inference", "causal discovery", "counterfactual reasoning", "\u56e0\u679c\u63a8\u7406", "\u56e0\u679c\u53d1\u73b0", "\u53cd\u4e8b\u5b9e")),
    ("edge-cloud collaboration", ("edge-cloud", "edge cloud collaboration", "cloud edge collaboration", "\u7aef\u4e91\u534f\u540c", "\u7aef\u8fb9\u4e91\u534f\u540c")),
    ("early fusion", ("early fusion", "\u65e9\u671f\u878d\u5408")),
    ("late fusion", ("late fusion", "\u540e\u671f\u878d\u5408")),
    ("intermediate fusion", ("intermediate fusion", "middle fusion", "\u4e2d\u95f4\u878d\u5408")),
    (
        "failure recovery",
        (
            "failure recovery",
            "error recovery",
            "recover from failure",
            "失败恢复",
            "故障恢复",
            "错误恢复",
            "恢复能力",
        ),
    ),
    (
        "cost efficiency",
        (
            "cost efficiency",
            "cost-aware",
            "cost aware",
            "token cost",
            "api cost",
            "成本",
            "预算",
        ),
    ),
    ("latency", ("latency", "response time", "延迟", "时延", "响应时间")),
    (
        "task success rate",
        (
            "task success rate",
            "success rate",
            "任务成功率",
            "成功率",
        ),
    ),
    ("tool selection", ("tool selection", "工具选择")),
    ("tool use", ("tool use", "tool usage", "tool-using", "\u5de5\u5177\u4f7f\u7528", "\u5de5\u5177\u8c03\u7528")),
    ("tool calling", ("tool calling", "api calling", "function calling", "\u51fd\u6570\u8c03\u7528", "api \u8c03\u7528")),
    ("benchmark evaluation", ("benchmark", "evaluation", "\u8bc4\u6d4b", "\u57fa\u51c6")),
    ("survey review", ("survey", "review", "\u7efc\u8ff0")),
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
_EXPLICIT_FOCUS_PATTERNS = (
    re.compile(
        r"(?:\u91cd\u70b9(?:\u5173\u6ce8|\u5206\u6790|\u7814\u7a76|\u8ba8\u8bba|\u8865\u5145)"
        r"|\u805a\u7126(?:\u4e8e)?|\u7740\u91cd(?:\u4e8e)?|\u5173\u6ce8|\u56f4\u7ed5)"
        r"\s*[:\uff1a]?\s*([^\u3002\uff01\uff1f\uff1b;]+)",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"(?:focus(?:ing)?\s+on|with\s+emphasis\s+on|pay\s+attention\s+to)"
        r"\s*[:：]?\s*([^.!?;]+)",
        flags=re.IGNORECASE,
    ),
)
_CONTINUATION_FOCUS_PATTERNS = (
    re.compile(
        r"(?:\u7ee7\u7eed(?:\u5c55\u5f00|\u6df1\u5165|\u6df1\u5316)?"
        r"|\u5c55\u5f00|\u6df1\u5165|\u6df1\u5316|\u6269\u5c55|\u8865\u5145|\u56f4\u7ed5)"
        r"\s*(?:\u4e00\u4e0b|\u8fd9\u4e2a\u65b9\u5411|\u8be5\u65b9\u5411|\u65b9\u5411)?"
        r"\s*[:\uff1a]\s*([^\u3002\uff01\uff1f\uff1b;]+)",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"(?:continue(?: with)?|expand(?: on)?|drill into|further explore)"
        r"\s*[:\-]?\s*([^.!?;]+)",
        flags=re.IGNORECASE,
    ),
)
_EXPLICIT_COMPARISON_PATTERNS = (
    re.compile(
        r"(?:\u5e76|\u540c\u65f6)?(?:\u6bd4\u8f83|\u5bf9\u6bd4)"
        r"\s*[:\uff1a]?\s*([^\u3002\uff01\uff1f\uff1b;]+)",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"(?:compare|comparison\s+of)\s+([^.!?;]+)",
        flags=re.IGNORECASE,
    ),
)
_FOCUS_SEGMENT_SPLIT_PATTERN = re.compile(
    r"\s*(?:[\u3001,\uff0c/]|\u4ee5\u53ca|\u4e0e|\u53ca|\u548c|\band\b)\s*",
    flags=re.IGNORECASE,
)
_FOCUS_TRAILING_DIRECTIVE_PATTERN = re.compile(
    r"(?:\uff0c|,)?\s*(?:"
    r"\u5e76(?:\u8865\u5145|\u67e5\u627e|\u641c\u7d22|\u627e)"
    r"|\u5e76(?:\u6bd4\u8f83|\u5bf9\u6bd4)"
    r"|\u540c\u65f6(?:\u8865\u5145|\u67e5\u627e|\u641c\u7d22|\u627e)"
    r"|\u540c\u65f6(?:\u6bd4\u8f83|\u5bf9\u6bd4)"
    r"|and\s+(?:add|find|search|include)"
    r"|and\s+compare"
    r").*$",
    flags=re.IGNORECASE,
)
_COMPARISON_CRITERIA_SUFFIX_PATTERN = re.compile(
    r"\s*(?:\u7684)?(?:\u6027\u80fd|\u6548\u679c|\u8868\u73b0|\u9002\u7528\u573a\u666f|\u4f18\u7f3a\u70b9).*$",
    flags=re.IGNORECASE,
)
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
_GENERIC_FOCUS_TERMS = {
    "\u8fd9\u4e2a\u65b9\u5411",
    "\u8be5\u65b9\u5411",
    "\u8fd9\u4e00\u65b9\u5411",
    "\u76f8\u5173\u65b9\u5411",
    "\u8fd9\u4e2a\u4e3b\u9898",
    "\u8be5\u4e3b\u9898",
    "this direction",
    "this topic",
    "the topic",
    "\u5b83",
    "\u5b83\u4eec",
    "\u5176",
    "\u4e8c\u8005",
    "\u4e24\u8005",
}
_CANONICALIZED_FOCUS_LABELS = {
    "public datasets",
    "evaluation metrics",
    "ablation studies",
    "early fusion",
    "late fusion",
    "intermediate fusion",
}


@dataclass
class QueryIntent:
    raw_user_request: str
    task_topic: str
    conversation_topic: str
    core_topic: str
    user_goal: str
    knowledge_scope: str
    focus_facets: list[dict[str, Any]] = field(default_factory=list)
    request_focus_terms: list[str] = field(default_factory=list)
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
            "focus_facets": [dict(facet) for facet in self.focus_facets],
            "request_focus_terms": list(self.request_focus_terms),
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

    focus_facets = _extract_explicit_focus_facets(clean_request)
    facet_labels = [str(facet.get("label", "")) for facet in focus_facets]
    request_focus_terms = _dedupe(
        [
            *_domain_focus_terms(clean_request),
            *facet_labels,
            *_quoted_or_acronym_terms(clean_request),
        ]
    )
    # Search intent must stay anchored to the user's request and research topic.
    # Workspace and shared-knowledge clues are useful later as optional hints,
    # but promoting their English tokens into hard rerank signals can derail a
    # Chinese topic with unrelated terms from another conversation.
    topic_text = " ".join(
        part
        for part in (
            clean_request,
            clean_task_topic,
            clean_conversation_topic,
        )
        if part
    )
    focus_terms = _dedupe(
        [
            *request_focus_terms,
            *_domain_focus_terms(topic_text),
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
        focus_facets=focus_facets[:6],
        request_focus_terms=request_focus_terms[:4],
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


def _extract_explicit_focus_facets(text: str) -> list[dict[str, Any]]:
    facets: list[dict[str, Any]] = []
    seen: set[str] = set()
    for pattern in _CONTINUATION_FOCUS_PATTERNS:
        for match in pattern.finditer(text):
            clause = _FOCUS_TRAILING_DIRECTIVE_PATTERN.sub("", match.group(1)).strip()
            _append_focus_clause(facets, seen, clause)
    for pattern in _EXPLICIT_FOCUS_PATTERNS:
        for match in pattern.finditer(text):
            clause = _FOCUS_TRAILING_DIRECTIVE_PATTERN.sub("", match.group(1)).strip()
            _append_focus_clause(facets, seen, clause)
    for pattern in _EXPLICIT_COMPARISON_PATTERNS:
        for match in pattern.finditer(text):
            clause = _COMPARISON_CRITERIA_SUFFIX_PATTERN.sub("", match.group(1)).strip()
            _append_focus_clause(facets, seen, clause)
    return facets


def _append_focus_clause(
    facets: list[dict[str, Any]],
    seen: set[str],
    clause: str,
) -> None:
    for raw_segment in _FOCUS_SEGMENT_SPLIT_PATTERN.split(clause):
        segment = _clean_focus_segment(raw_segment)
        if not segment:
            continue
        mapped_terms = _matching_labels(segment, _DOMAIN_FOCUS_PATTERNS)
        if mapped_terms and _should_canonicalize_focus_label(segment, mapped_terms):
            labels = (
                [term for term in mapped_terms if term in _CANONICALIZED_FOCUS_LABELS]
                if re.search(r"[\u4e00-\u9fff]", segment)
                else mapped_terms
            )
        else:
            labels = [segment]
        for label in labels:
            key = label.casefold()
            if key in seen:
                continue
            seen.add(key)
            facets.append(
                {
                    "label": label,
                    "kind": "research_dimension",
                    "source": "explicit_user",
                    "required": True,
                }
            )


def _should_canonicalize_focus_label(segment: str, mapped_terms: list[str]) -> bool:
    """Keep user-facing focus labels stable, except for generic evaluation axes."""

    if not mapped_terms:
        return False
    if not re.search(r"[\u4e00-\u9fff]", segment):
        return True
    return any(term in _CANONICALIZED_FOCUS_LABELS for term in mapped_terms)


def _clean_focus_segment(value: str) -> str:
    segment = " ".join(str(value).split()).strip(" \t\r\n:：,，。；;")
    segment = re.sub(
        r"^(?:\u5bf9|\u5173\u4e8e|\u5728)\s*",
        "",
        segment,
        flags=re.IGNORECASE,
    )
    segment = re.sub(
        r"(?:\u7b49(?:\u65b9\u5411|\u65b9\u9762)?|\u65b9\u9762)$",
        "",
        segment,
        flags=re.IGNORECASE,
    ).strip()
    if not segment or segment.casefold() in _GENERIC_FOCUS_TERMS:
        return ""
    if len(segment) > 80:
        return ""
    if _extract_time_range(segment, reference_year=None):
        return ""
    return segment


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
