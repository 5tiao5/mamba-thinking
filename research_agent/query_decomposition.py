from __future__ import annotations

import re
from typing import Iterable, List


BROAD_TOPIC_HINTS = (
    "future",
    "frontier",
    "frontiers",
    "progress",
    "trend",
    "trends",
    "survey",
    "overview",
    "landscape",
    "state of the art",
    "direction",
    "directions",
    "advanced",
    "前沿",
    "未来",
    "趋势",
    "综述",
    "进展",
    "方向",
)


DEFAULT_RESEARCH_FACETS = (
    "core methods",
    "benchmark evaluation",
    "limitations and failure modes",
    "real-world applications",
    "future directions",
)


SOFTWARE_ENGINEERING_FACETS = (
    "developer workflow",
    "repository reasoning",
    "benchmark evaluation",
    "limitations and failure modes",
    "future directions",
)


INTERACTION_FACETS = (
    "human-agent interaction",
    "developer trust and control",
    "benchmark evaluation",
    "limitations and failure modes",
    "future directions",
)


def build_search_queries(topic: str, *, fast: bool = False, balanced: bool = False) -> List[str]:
    clean_topic = " ".join(str(topic).split()).strip()
    if not clean_topic:
        return []

    if fast:
        return [clean_topic]

    facets = infer_research_facets(clean_topic)
    if balanced:
        return _dedupe([clean_topic, *[f"{clean_topic} {facet}" for facet in facets[:3]], f"{clean_topic} survey"])[:4]

    return _dedupe(
        [
            clean_topic,
            *[f"{clean_topic} {facet}" for facet in facets],
            f"{clean_topic} survey review",
            f"{clean_topic} state of the art",
        ]
    )[:6]


def infer_research_facets(topic: str) -> List[str]:
    lowered = topic.lower()
    if _contains_any(lowered, ("software engineering", "code agent", "coding agent", "repository")):
        facets = list(SOFTWARE_ENGINEERING_FACETS)
    elif _contains_any(lowered, ("interaction", "human-agent", "developer", "usability", "trust")):
        facets = list(INTERACTION_FACETS)
    else:
        facets = list(DEFAULT_RESEARCH_FACETS)

    explicit_focus = _extract_focus_phrase(topic)
    if explicit_focus and not _looks_like_meta_research_phrase(explicit_focus):
        facets.insert(0, explicit_focus)

    if not is_broad_topic(topic):
        facets = facets[:3]
    return _dedupe(facets)


def is_broad_topic(topic: str) -> bool:
    lowered = topic.lower()
    return _contains_any(lowered, BROAD_TOPIC_HINTS)


def _extract_focus_phrase(topic: str) -> str | None:
    match = re.search(r"focus on\s+(.+)$", topic, flags=re.IGNORECASE)
    if not match:
        return None
    raw = match.group(1).strip()
    raw = re.sub(r"\s+", " ", raw)
    return raw if len(raw) >= 4 else None


def _looks_like_meta_research_phrase(phrase: str) -> bool:
    lowered = phrase.lower()
    meta_hints = (
        "future",
        "frontier",
        "progress",
        "trend",
        "direction",
        "前沿",
        "未来",
        "趋势",
        "进展",
        "方向",
    )
    return _contains_any(lowered, meta_hints)


def _contains_any(text: str, needles: Iterable[str]) -> bool:
    return any(needle in text for needle in needles)


def _dedupe(items: Iterable[str]) -> List[str]:
    result: List[str] = []
    seen = set()
    for item in items:
        clean = " ".join(str(item).split()).strip()
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result
