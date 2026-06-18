from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from collections import OrderedDict
from typing import Any

from product_agent import llm_client
from product_agent.schemas import WorkspacePaperBriefView
from product_agent.services.text_cleaning import clean_internal_context_text


_CACHE_MAX_SIZE = 256
_CACHE: OrderedDict[str, WorkspacePaperBriefView] = OrderedDict()
_CACHE_LOCK = threading.Lock()

_FIELD_LIMITS = {
    "problem": 220,
    "method": 220,
    "contribution": 220,
    "limitation": 220,
    "relation_to_topic": 220,
    "why_selected": 360,
    "read_focus": 260,
    "evidence_basis": 320,
    "verification_boundary": 320,
}
_INTERNAL_TOKEN_PATTERN = re.compile(
    r"\b(?:[a-f0-9]{24,64}|team_process|topic_match|user_selected|focus|abstract|query|score):?\b",
    flags=re.IGNORECASE,
)


def paper_brief_llm_enabled() -> bool:
    """Return whether the Paper Brief LLM editor should run.

    Product runtime defaults to auto-on when an API key exists. Tests stay
    offline unless they explicitly opt in with ENABLE_PAPER_BRIEF_LLM=1.
    """

    if (
        os.environ.get("SKIP_PAPER_BRIEF_LLM") == "1"
        or os.environ.get("DISABLE_PAPER_BRIEF_LLM") == "1"
    ):
        return False
    if os.environ.get("PYTEST_CURRENT_TEST") and os.environ.get("ENABLE_PAPER_BRIEF_LLM") != "1":
        return False
    mode = os.environ.get("PAPER_BRIEF_LLM_MODE", "auto").strip().casefold()
    if mode in {"0", "off", "false", "disabled", "skip"}:
        return False
    return (
        os.environ.get("ENABLE_PAPER_BRIEF_LLM") == "1"
        or mode in {"", "1", "auto", "on", "true", "enabled"}
    ) and llm_client.has_openai_key()


def enhance_paper_brief_with_llm(
    *,
    topic: str,
    paper_title: str,
    abstract: str,
    review_text: str,
    brief: WorkspacePaperBriefView,
    selection_factors: list[str] | None = None,
) -> WorkspacePaperBriefView:
    """Use an LLM as a conservative editor for an existing Paper Brief.

    This layer must not introduce new evidence. It only rewrites the existing
    metadata, abstract/full-text excerpts, and claim checks into more useful
    reading guidance.
    """

    if (
        not paper_brief_llm_enabled()
        or not paper_title.strip()
        or brief.source == "metadata"
    ):
        return brief

    payload = _paper_brief_payload(
        topic=topic,
        paper_title=paper_title,
        abstract=abstract,
        review_text=review_text,
        brief=brief,
        selection_factors=selection_factors or [],
    )
    cache_key = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    with _CACHE_LOCK:
        cached = _CACHE.get(cache_key)
        if cached is not None:
            _CACHE.move_to_end(cache_key)
            return cached

    raw = llm_client.call_openai_json(
        json.dumps(
            {
                "topic": payload["topic"],
                "paper": payload,
                "task": (
                    "Rewrite the Paper Brief into precise Chinese reading guidance. "
                    "Use only the supplied paper metadata, abstract/full-text excerpt, "
                    "selection factors, and claim checks. Do not add new claims, papers, "
                    "numbers, benchmark results, or citations. Preserve uncertainty."
                ),
                "output_schema": {
                    "problem": "string, <= 160 Chinese chars",
                    "method": "string, <= 160 Chinese chars",
                    "contribution": "string, <= 160 Chinese chars",
                    "limitation": "string, <= 160 Chinese chars",
                    "relation_to_topic": "string, <= 160 Chinese chars",
                    "why_selected": "string, <= 240 Chinese chars",
                    "read_focus": "string, <= 200 Chinese chars",
                    "evidence_basis": "string, <= 220 Chinese chars",
                    "verification_boundary": "string, <= 220 Chinese chars",
                },
            },
            ensure_ascii=False,
        ),
        system=(
            "You are a cautious paper-reading analyst. Return JSON only. "
            "Never invent missing evidence. Never expose internal IDs, labels, or scoring tokens."
        ),
        temperature=0.12,
        max_output_tokens=900,
    )
    updates = _validate_llm_updates(raw)
    if not updates:
        return brief

    result = brief.model_copy(update=updates)
    with _CACHE_LOCK:
        _CACHE[cache_key] = result
        _CACHE.move_to_end(cache_key)
        if len(_CACHE) > _CACHE_MAX_SIZE:
            _CACHE.popitem(last=False)
    return result


def _paper_brief_payload(
    *,
    topic: str,
    paper_title: str,
    abstract: str,
    review_text: str,
    brief: WorkspacePaperBriefView,
    selection_factors: list[str],
) -> dict[str, Any]:
    return {
        "topic": clean_internal_context_text(topic, max_length=120),
        "title": clean_internal_context_text(paper_title, max_length=180),
        "abstract": clean_internal_context_text(abstract, max_length=900),
        "full_text_excerpt": clean_internal_context_text(review_text, max_length=2600),
        "source_level": brief.source,
        "tags": list(brief.tags[:8]),
        "selection_factors": [
            clean_internal_context_text(item, max_length=120)
            for item in selection_factors[:8]
            if clean_internal_context_text(item, max_length=120)
        ],
        "current_brief": {
            key: clean_internal_context_text(getattr(brief, key, ""), max_length=limit)
            for key, limit in _FIELD_LIMITS.items()
        },
        "claim_checks": [
            {
                "type": clean_internal_context_text(check.claim_type, max_length=40),
                "claim": clean_internal_context_text(check.claim, max_length=200),
                "status": clean_internal_context_text(check.status, max_length=40),
                "source_level": clean_internal_context_text(check.source_level, max_length=40),
                "section": clean_internal_context_text(check.section, max_length=60),
                "page": int(getattr(check, "page", 0) or 0),
                "confidence": float(getattr(check, "confidence", 0.0) or 0.0),
                "evidence": clean_internal_context_text(check.evidence, max_length=260),
                "caveat": clean_internal_context_text(check.caveat, max_length=180),
            }
            for check in brief.claim_checks[:8]
        ],
    }


def _validate_llm_updates(raw: Any) -> dict[str, str] | None:
    if not isinstance(raw, dict):
        return None

    updates: dict[str, str] = {}
    for key, limit in _FIELD_LIMITS.items():
        value = clean_internal_context_text(raw.get(key, ""), max_length=limit)
        if not value or _looks_like_internal_text(value):
            continue
        updates[key] = value
    return updates or None


def _looks_like_internal_text(value: str) -> bool:
    normalized = value.strip().casefold()
    if not normalized:
        return True
    if "未识别论文" in value:
        return True
    if _INTERNAL_TOKEN_PATTERN.search(normalized):
        return True
    return bool(re.fullmatch(r"[a-z][a-z0-9_+-]*(?:[\s,;/]+[a-z][a-z0-9_+-]*){0,8}", normalized))
