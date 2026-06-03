from __future__ import annotations

import re


_RESULT_ANCHORS = (
    "\u7814\u7a76\u5ba1\u8ba1\u6982\u89c8",
    "\u672c\u8f6e\u5206\u6790",
    "\u5efa\u8bae\uff1a",
    "\u4f18\u5148\u5173\u6ce8\uff1a",
    "Research Overview",
    "Summary",
)
_INTERNAL_MARKER_PATTERN = re.compile(
    r"\[(?:Prior research knowledge|prior knowledge|Knowledge)[^\]]*\]\s*",
    flags=re.IGNORECASE,
)
_TASK_TAG_PATTERN = re.compile(r"\[task:[^\]]+\]\s*", flags=re.IGNORECASE)
_AUTO_TAG_PATTERN = re.compile(r"\[Auto\]\s*", flags=re.IGNORECASE)
_INTERNAL_PHRASE_PATTERN = re.compile(
    r"(?:Prior research knowledge\s*-?\s*use this to reduce fallback and improve search relevance|prior knowledge)\s*:?",
    flags=re.IGNORECASE,
)
_TRUNCATED_TASK_TAG_PATTERN = re.compile(r"\[t(?:ask)?\.{2,}.*?(?=\s|$)", flags=re.IGNORECASE)
_FOLLOW_UP_LABEL_PATTERN = re.compile(r"\s+-\s+(?:follow\s*up|focus\s*on)\s*:\s*", flags=re.IGNORECASE)
_INFORMED_BY_SUFFIX_PATTERN = re.compile(r"\s+-\s+informed\s+by\s+.*$", flags=re.IGNORECASE)


def clean_internal_context_text(value: object, *, max_length: int | None = None) -> str:
    """Remove internal knowledge-context markers from user-visible text."""
    if value is None:
        return ""

    text = str(value)
    if not text.strip():
        return ""

    has_internal_prefix = any(
        marker in text
        for marker in (
            "[Knowledge",
            "[Prior research knowledge",
            "[task:",
            "[Auto]",
            "Prior research knowledge",
            "prior knowledge",
        )
    )
    anchor_indexes = [text.find(anchor) for anchor in _RESULT_ANCHORS if text.find(anchor) > 0]
    if has_internal_prefix and anchor_indexes:
        text = text[min(anchor_indexes):]

    text = _INTERNAL_MARKER_PATTERN.sub(" ", text)
    text = _TASK_TAG_PATTERN.sub(" ", text)
    text = _AUTO_TAG_PATTERN.sub(" ", text)
    text = _INTERNAL_PHRASE_PATTERN.sub(" ", text)
    text = _TRUNCATED_TASK_TAG_PATTERN.sub(" ", text)
    text = _FOLLOW_UP_LABEL_PATTERN.sub(" - ", text)
    text = _INFORMED_BY_SUFFIX_PATTERN.sub("", text)
    text = re.sub(r"\[\s*\]", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" \t\r\n:;-")

    if max_length is not None and max_length > 0 and len(text) > max_length:
        text = f"{text[: max_length - 3].rstrip()}..."

    return text


def clean_internal_context_items(values: list[str], *, max_length: int | None = None) -> list[str]:
    cleaned: list[str] = []
    seen = set()
    for value in values:
        text = clean_internal_context_text(value, max_length=max_length)
        if not text:
            continue
        normalized = text.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        cleaned.append(text)
    return cleaned
