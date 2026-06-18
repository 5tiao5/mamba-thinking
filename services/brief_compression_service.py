from __future__ import annotations

import hashlib
import json
import os
from collections import OrderedDict

from product_agent import llm_client
from product_agent.schemas import WorkspaceResearchBriefView
from product_agent.services.text_cleaning import clean_internal_context_text


_CACHE_MAX_SIZE = 128
_CACHE: OrderedDict[str, WorkspaceResearchBriefView] = OrderedDict()


def compress_research_brief_with_llm(
    *,
    topic: str,
    brief: WorkspaceResearchBriefView,
) -> WorkspaceResearchBriefView:
    """Use a cheap LLM pass as an editor, never as a new evidence generator."""

    if (
        os.environ.get("SKIP_RESEARCH_BRIEF_LLM") == "1"
        or not llm_client.has_openai_key()
        or not brief.executive_summary
    ):
        return brief

    payload = _brief_payload(topic=topic, brief=brief)
    cache_key = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    if cache_key in _CACHE:
        _CACHE.move_to_end(cache_key)
        return _CACHE[cache_key]

    raw = llm_client.call_openai_json(
        json.dumps(
            {
                "topic": topic,
                "brief": payload,
                "task": (
                    "Rewrite the research brief as a concise Chinese research-decision brief. "
                    "Do not add new claims, papers, numbers, or evidence. Preserve uncertainty."
                ),
                "output_schema": {
                    "headline": "string, <= 80 Chinese chars",
                    "executive_summary": "string, <= 260 Chinese chars",
                    "landscape_overview": "string, <= 180 Chinese chars",
                    "evidence_rationale": "string, <= 180 Chinese chars",
                    "decision_advice": "string, <= 180 Chinese chars",
                    "follow_up_prompts": "array of 3-5 concise Chinese follow-up prompts, each <= 36 chars, no caveat/log text",
                },
            },
            ensure_ascii=False,
        ),
        system=(
            "You are a conservative research brief editor. Return JSON only. "
            "Use only supplied facts. Do not invent papers, counts, citations, claims, or verification levels."
        ),
        temperature=0.15,
        max_output_tokens=600,
    )
    compressed = _validate_compression(raw)
    if compressed is None:
        return brief

    result = brief.model_copy(
        update={
            "headline": compressed.get("headline") or brief.headline,
            "executive_summary": compressed.get("executive_summary") or brief.executive_summary,
            "landscape_overview": compressed.get("landscape_overview") or brief.landscape_overview,
            "evidence_rationale": compressed.get("evidence_rationale") or brief.evidence_rationale,
            "decision_advice": compressed.get("decision_advice") or brief.decision_advice,
            "follow_up_prompts": compressed.get("follow_up_prompts") or brief.follow_up_prompts,
            "source": "llm_compressed",
        }
    )
    _CACHE[cache_key] = result
    _CACHE.move_to_end(cache_key)
    if len(_CACHE) > _CACHE_MAX_SIZE:
        _CACHE.popitem(last=False)
    return result


def _brief_payload(*, topic: str, brief: WorkspaceResearchBriefView) -> dict:
    return {
        "topic": clean_internal_context_text(topic, max_length=120),
        "headline": clean_internal_context_text(brief.headline, max_length=120),
        "executive_summary": clean_internal_context_text(brief.executive_summary, max_length=420),
        "landscape_overview": clean_internal_context_text(brief.landscape_overview, max_length=260),
        "evidence_rationale": clean_internal_context_text(brief.evidence_rationale, max_length=260),
        "decision_advice": clean_internal_context_text(brief.decision_advice, max_length=260),
        "must_read_titles": [
            clean_internal_context_text(paper.title, max_length=120)
            for paper in brief.must_read_papers[:4]
            if paper.title
        ],
        "evidence_warnings": [
            clean_internal_context_text(warning, max_length=160)
            for warning in brief.evidence_warnings[:3]
            if warning
        ],
        "open_gaps": [
            clean_internal_context_text(item.text, max_length=180)
            for item in brief.open_gaps[:3]
            if item.text
        ],
        "recommended_next_steps": [
            clean_internal_context_text(item.text, max_length=180)
            for item in brief.recommended_next_steps[:3]
            if item.text
        ],
        "follow_up_prompts": [
            clean_internal_context_text(prompt, max_length=90)
            for prompt in brief.follow_up_prompts[:5]
            if prompt
        ],
    }


def _validate_compression(raw) -> dict[str, object] | None:
    if not isinstance(raw, dict):
        return None
    result: dict[str, object] = {}
    limits = {
        "headline": 120,
        "executive_summary": 360,
        "landscape_overview": 260,
        "evidence_rationale": 260,
        "decision_advice": 260,
    }
    for key, limit in limits.items():
        value = clean_internal_context_text(raw.get(key, ""), max_length=limit)
        if value:
            result[key] = value
    raw_prompts = raw.get("follow_up_prompts", [])
    if isinstance(raw_prompts, list):
        prompts: list[str] = []
        banned_fragments = ("以下内容仅作为", "待验证假设", "选择依据", "证据等级", "依据 ")
        for item in raw_prompts:
            prompt = clean_internal_context_text(str(item or ""), max_length=80).strip(" ，,；;：:-")
            if not prompt or any(fragment in prompt for fragment in banned_fragments):
                continue
            prompts.append(prompt)
            if len(prompts) == 5:
                break
        if prompts:
            result["follow_up_prompts"] = prompts
    return result if result.get("executive_summary") else None
