from __future__ import annotations

import json
import re
from typing import Any

from product_agent.llm_client import call_openai_json, has_openai_key


def expand_focus_facets(
    *,
    query_intent: dict[str, Any],
    topic: str,
    mode: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Attach executable English search terms to the topic and focus facets."""

    intent = dict(query_intent or {})
    facets = _normalize_facets(intent.get("focus_facets", []))
    topic = " ".join(str(topic or intent.get("core_topic", "")).split()).strip()
    needs_topic_expansion = _needs_topic_expansion(topic, intent)
    if not facets and not needs_topic_expansion:
        return intent, _outcome("not_needed", attempted=False, expanded_count=0)

    expanded_count = 0
    pending_labels: list[str] = []
    for facet in facets:
        label = str(facet["label"])
        if _is_english_search_phrase(label):
            facet["search_terms"] = [label]
            facet["query_candidates"] = [_join_query(topic, label)]
            facet["expansion_source"] = "direct"
            expanded_count += 1
        else:
            pending_labels.append(label)

    if not pending_labels and not needs_topic_expansion:
        intent["focus_facets"] = facets
        return intent, _outcome(
            "direct",
            attempted=False,
            expanded_count=expanded_count,
        )

    if mode == "fast":
        intent["focus_facets"] = facets
        return intent, _outcome(
            "skipped_fast_mode",
            attempted=False,
            expanded_count=expanded_count,
        )
    if not has_openai_key():
        intent["focus_facets"] = facets
        if needs_topic_expansion and not pending_labels and expanded_count:
            return intent, _outcome(
                "direct",
                attempted=False,
                expanded_count=expanded_count,
            )
        return intent, _outcome(
            "no_llm_key",
            attempted=False,
            expanded_count=expanded_count,
        )

    data = call_openai_json(
        _expansion_prompt(topic=topic, labels=pending_labels),
        system=(
            "You translate research requirements into concise academic search "
            "language. Preserve meaning exactly and return valid JSON only."
        ),
        temperature=0.1,
        max_output_tokens=900,
    )
    topic_expansion = _parse_topic_expansion(data)
    if topic_expansion:
        intent.update(topic_expansion)
        expanded_count += 1
    expansions = _parse_facet_expansions(data, allowed_labels=set(pending_labels))
    for facet in facets:
        expansion = expansions.get(str(facet["label"]))
        if not expansion:
            continue
        facet.update(expansion)
        facet["expansion_source"] = "llm"
        expanded_count += 1

    intent["focus_facets"] = facets
    return intent, _outcome(
        "expanded" if expansions or topic_expansion else "invalid_llm_response",
        attempted=True,
        expanded_count=expanded_count,
    )


def _expansion_prompt(*, topic: str, labels: list[str]) -> str:
    payload = json.dumps(labels, ensure_ascii=False)
    return f"""
Convert the research topic and each required research facet into English academic search language.

Research topic: {topic}
Required facets: {payload}

Rules:
- Return a stable English topic_anchor likely to appear in paper titles or abstracts.
- Return 2-4 topic_alias_queries, 1-3 broad_queries, and 1-3 recall_queries.
- Return exactly one item for every supplied facet; do not add new facets.
- Keep each academic term between 2 and 6 words.
- Keep each query between 3 and 12 words and anchor it to the research topic.
- Use terminology likely to appear in paper titles or abstracts.
- Do not include years because year constraints are handled separately.

Return JSON only:
{{
  "topic_anchor": "concise English academic topic",
  "topic_alias_queries": ["topic query", "synonym query"],
  "broad_queries": ["broader recall query"],
  "recall_queries": ["short recall query"],
  "facets": [
    {{
      "label": "original facet text",
      "academic_terms": ["primary English term", "optional synonym"],
      "queries": ["one concise English academic query"]
    }}
  ]
}}
""".strip()


def _parse_topic_expansion(data: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {}
    topic_anchor = _single_valid_english_phrase(
        data.get("topic_anchor"),
        min_words=2,
        max_words=8,
    )
    topic_alias_queries = _valid_english_phrases(
        data.get("topic_alias_queries", []),
        min_words=2,
        max_words=12,
    )
    broad_queries = _valid_english_phrases(
        data.get("broad_queries", []),
        min_words=2,
        max_words=12,
    )
    recall_queries = _valid_english_phrases(
        data.get("recall_queries", []),
        min_words=2,
        max_words=8,
    )
    payload: dict[str, Any] = {}
    if topic_anchor:
        payload["topic_anchor"] = topic_anchor
    if topic_alias_queries:
        payload["topic_alias_queries"] = topic_alias_queries[:4]
    if broad_queries:
        payload["llm_broad_queries"] = broad_queries[:3]
    if recall_queries:
        payload["llm_recall_queries"] = recall_queries[:3]
    if payload:
        payload["query_expansion_source"] = "llm"
    return payload


def _parse_facet_expansions(
    data: dict[str, Any] | None,
    *,
    allowed_labels: set[str],
) -> dict[str, dict[str, Any]]:
    if not isinstance(data, dict) or not isinstance(data.get("facets"), list):
        return {}
    expansions: dict[str, dict[str, Any]] = {}
    for item in data["facets"]:
        if not isinstance(item, dict):
            continue
        label = " ".join(str(item.get("label", "")).split()).strip()
        if label not in allowed_labels:
            continue
        terms = _valid_english_phrases(item.get("academic_terms", []), min_words=2, max_words=6)
        queries = _valid_english_phrases(item.get("queries", []), min_words=3, max_words=12)
        if not terms or not queries:
            continue
        expansions[label] = {
            "search_terms": terms[:2],
            "query_candidates": queries[:1],
        }
    return expansions


def _needs_topic_expansion(topic: str, intent: dict[str, Any]) -> bool:
    if intent.get("topic_anchor") or intent.get("topic_alias_queries"):
        return False
    if not topic:
        return False
    if _has_deterministic_topic_expansion(topic):
        return False
    if re.search(r"[\u4e00-\u9fff]", topic):
        return True
    english_words = re.findall(r"[A-Za-z][A-Za-z0-9-]*", topic)
    return len(english_words) < 2


def _has_deterministic_topic_expansion(topic: str) -> bool:
    """Avoid paying LLM cost when retrieval planning already has stable aliases."""

    compact = re.sub(r"\s+", "", str(topic or "")).casefold()
    if not compact:
        return False
    if "\u5927\u6a21\u578b" in compact and "\u591a\u6a21\u6001" in compact:
        return True
    if "\u591a\u6a21\u6001" in compact and "\u878d\u5408" in compact:
        return True
    if "agent" in compact and (
        "\u5de5\u5177\u4f7f\u7528" in compact
        or "\u5de5\u5177\u8c03\u7528" in compact
        or "tooluse" in compact
        or "toolcalling" in compact
    ):
        return True
    return False


def _normalize_facets(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    facets: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            continue
        label = " ".join(str(item.get("label", "")).split()).strip()
        if not label or label.casefold() in seen:
            continue
        seen.add(label.casefold())
        facets.append(dict(item, label=label))
    return facets[:6]


def _valid_english_phrases(value: Any, *, min_words: int, max_words: int) -> list[str]:
    if not isinstance(value, list):
        return []
    phrases: list[str] = []
    seen: set[str] = set()
    for item in value:
        phrase = " ".join(str(item).split()).strip(" ,.;:")
        words = re.findall(r"[A-Za-z][A-Za-z0-9-]*", phrase)
        if not (min_words <= len(words) <= max_words):
            continue
        if re.search(r"[\u4e00-\u9fff]", phrase):
            continue
        normalized = " ".join(words)
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        phrases.append(normalized)
    return phrases


def _single_valid_english_phrase(value: Any, *, min_words: int, max_words: int) -> str:
    phrase = " ".join(str(value or "").split()).strip(" ,.;:")
    if not phrase:
        return ""
    phrases = _valid_english_phrases(
        [phrase],
        min_words=min_words,
        max_words=max_words,
    )
    return phrases[0] if phrases else ""


def _is_english_search_phrase(value: str) -> bool:
    return bool(re.search(r"[A-Za-z]", value)) and not bool(
        re.search(r"[\u4e00-\u9fff]", value)
    )


def _join_query(topic: str, facet: str) -> str:
    english_topic = " ".join(re.findall(r"[A-Za-z][A-Za-z0-9-]*", topic))
    return " ".join(part for part in (english_topic, facet) if part).strip() or facet


def _outcome(status: str, *, attempted: bool, expanded_count: int) -> dict[str, Any]:
    return {
        "status": status,
        "attempted": attempted,
        "expanded_count": expanded_count,
    }
