from __future__ import annotations

import json
import os
from typing import Any

from product_agent.llm_client import call_openai_json, has_openai_key
from product_agent.services.text_cleaning import clean_internal_context_text


_MAX_ROUNDS = 6
_MAX_ITEMS_PER_SECTION = 4


def synthesize_conversation_overview(
    *,
    topic: str,
    workspaces: list,
    papers: list,
    gaps: list,
    ideas: list,
) -> dict[str, Any]:
    """Create a bounded semantic overview with a deterministic fallback."""
    fallback = _build_fallback(
        topic=topic,
        workspaces=workspaces,
        papers=papers,
        gaps=gaps,
        ideas=ideas,
    )
    if (
        len(workspaces) < 2
        or os.environ.get("SKIP_CONVERSATION_SYNTHESIS_LLM") == "1"
        or not has_openai_key()
    ):
        return fallback

    round_briefs, valid_task_ids, valid_evidence_ids = _build_round_briefs(workspaces)
    prompt = json.dumps(
        {
            "topic": topic,
            "rounds": round_briefs,
            "requirements": {
                "language": "Chinese",
                "goal": (
                    "Merge the research rounds semantically. Distinguish genuinely new "
                    "findings, strengthened findings, revised findings, open questions, "
                    "and current recommendations. Do not invent evidence."
                ),
                "output_schema": {
                    "headline": "string",
                    "summary": "string",
                    "new_findings": [_item_schema()],
                    "strengthened_findings": [_item_schema()],
                    "revised_findings": [_item_schema()],
                    "open_questions": [_item_schema()],
                    "current_recommendations": [_item_schema()],
                },
                "limits": {
                    "items_per_section": _MAX_ITEMS_PER_SECTION,
                    "headline_chars": 100,
                    "summary_chars": 320,
                },
            },
        },
        ensure_ascii=False,
    )
    raw = call_openai_json(
        prompt,
        system=(
            "You are a conservative research synthesis editor. Return JSON only. "
            "Every claim must cite only task IDs and evidence IDs present in the input."
        ),
        temperature=0.1,
        max_output_tokens=900,
    )
    validated = _validate_synthesis(
        raw,
        valid_task_ids=valid_task_ids,
        valid_evidence_ids=valid_evidence_ids,
    )
    if validated is None:
        return fallback
    validated["source"] = "llm"
    return validated


def _item_schema() -> dict[str, Any]:
    return {
        "text": "string",
        "source_task_ids": ["task id from input"],
        "evidence_ids": ["evidence id from input"],
    }


def _build_round_briefs(workspaces: list) -> tuple[list[dict], set[str], set[str]]:
    selected = list(workspaces[: _MAX_ROUNDS - 1])
    if len(workspaces) > _MAX_ROUNDS - 1:
        earliest = workspaces[-1]
        if earliest not in selected:
            selected.append(earliest)
    selected.reverse()

    briefs: list[dict] = []
    valid_task_ids: set[str] = set()
    valid_evidence_ids: set[str] = set()
    for workspace in selected:
        task_id = str(getattr(workspace, "task_id", "") or "").strip()
        if not task_id:
            continue
        valid_task_ids.add(task_id)

        paper_items = []
        for paper in list(getattr(workspace, "papers", []) or [])[:6]:
            paper_id = str(getattr(paper, "paper_id", "") or "").strip()
            if not paper_id:
                continue
            evidence_id = f"paper::{paper_id}"
            valid_evidence_ids.add(evidence_id)
            paper_items.append(
                {
                    "evidence_id": evidence_id,
                    "title": _clean(getattr(paper, "title", ""), 140),
                    "relevance_tier": str(getattr(paper, "relevance_tier", "") or ""),
                }
            )

        gap_items = []
        for gap in list(getattr(workspace, "gaps", []) or [])[:4]:
            gap_id = str(getattr(gap, "gap_id", "") or "").strip()
            evidence_id = f"{task_id}::gap::{gap_id or len(gap_items) + 1}"
            valid_evidence_ids.add(evidence_id)
            gap_items.append(
                {
                    "evidence_id": evidence_id,
                    "summary": _clean(getattr(gap, "summary", ""), 180),
                    "severity": str(getattr(gap, "severity", "") or ""),
                    "evidence_count": len(getattr(gap, "evidence", []) or []),
                }
            )

        idea_items = []
        for idea in list(getattr(workspace, "ideas", []) or [])[:4]:
            idea_id = str(getattr(idea, "idea_id", "") or "").strip()
            evidence_id = f"{task_id}::idea::{idea_id or len(idea_items) + 1}"
            valid_evidence_ids.add(evidence_id)
            idea_items.append(
                {
                    "evidence_id": evidence_id,
                    "title": _clean(getattr(idea, "title", ""), 150),
                    "motivation": _clean(getattr(idea, "motivation", ""), 160),
                    "confidence": float(getattr(idea, "confidence", 0.0) or 0.0),
                }
            )

        briefs.append(
            {
                "task_id": task_id,
                "topic": _clean(getattr(workspace, "topic", ""), 180),
                "summary": _clean(getattr(workspace, "summary", ""), 280),
                "papers": paper_items,
                "gaps": gap_items,
                "ideas": idea_items,
            }
        )
    return briefs, valid_task_ids, valid_evidence_ids


def select_conversation_core_paper_ids(
    *,
    topic: str,
    workspaces: list,
    papers: list,
) -> list[str]:
    candidates = _build_paper_candidates(workspaces, papers)
    fallback_ids = [str(item["paper_id"]) for item in candidates[:12]]
    if (
        len(workspaces) < 2
        or not candidates
        or os.environ.get("SKIP_CONVERSATION_SYNTHESIS_LLM") == "1"
        or not has_openai_key()
    ):
        return fallback_ids

    valid_ids = {str(item["paper_id"]) for item in candidates}
    raw = call_openai_json(
        json.dumps(
            {
                "topic": topic,
                "paper_candidates": candidates,
                "selection_rules": [
                    "Select at most 12 papers.",
                    "Keep roughly two thirds from the latest round.",
                    "Use remaining slots for historically important, recurring, highly cited, "
                    "or complementary papers from earlier rounds.",
                    "Do not select off-topic papers or invent IDs.",
                ],
                "output_schema": {"paper_ids": ["paper id from candidates"]},
            },
            ensure_ascii=False,
        ),
        system=(
            "You conservatively rerank papers for a multi-round research overview. "
            "Return JSON only and use only supplied paper IDs."
        ),
        temperature=0.1,
        max_output_tokens=350,
    )
    if not isinstance(raw, dict):
        return fallback_ids
    selected = list(
        dict.fromkeys(
            str(paper_id)
            for paper_id in list(raw.get("paper_ids", []) or [])
            if str(paper_id) in valid_ids
        )
    )[:12]
    return selected or fallback_ids


def _build_paper_candidates(workspaces: list, papers: list) -> list[dict]:
    paper_by_id = {
        str(getattr(paper, "paper_id", "") or ""): paper
        for paper in papers
        if str(getattr(paper, "paper_id", "") or "")
    }
    round_sets: list[set[str]] = []
    candidate_ids: list[str] = []
    for workspace in workspaces:
        ids = [
            str(paper_id)
            for paper_id in list(
                (getattr(workspace, "summary_payload", {}) or {}).get(
                    "analysis_paper_ids", []
                )
                or []
            )
            if str(paper_id) in paper_by_id
        ]
        if not ids:
            ids = [
                str(getattr(paper, "paper_id", "") or "")
                for paper in list(getattr(workspace, "papers", []) or [])
                if str(getattr(paper, "paper_id", "") or "") in paper_by_id
            ]
        round_sets.append(set(ids))
        candidate_ids.extend(ids)

    candidates = []
    for paper_id in dict.fromkeys(candidate_ids):
        paper = paper_by_id[paper_id]
        candidates.append(
            {
                "paper_id": paper_id,
                "title": _clean(getattr(paper, "title", ""), 140),
                "year": str(getattr(paper, "publish_date", "") or "")[:4],
                "citation_count": int(getattr(paper, "citation_count", 0) or 0),
                "relevance_tier": str(
                    getattr(paper, "relevance_tier", "") or ""
                ),
                "round_count": sum(paper_id in ids for ids in round_sets),
                "in_latest_round": bool(round_sets and paper_id in round_sets[0]),
            }
        )
    return candidates[:24]


def _validate_synthesis(
    raw: Any,
    *,
    valid_task_ids: set[str],
    valid_evidence_ids: set[str],
) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    headline = _clean(raw.get("headline", ""), 100)
    summary = _clean(raw.get("summary", ""), 320)
    if not headline or not summary:
        return None

    result: dict[str, Any] = {"headline": headline, "summary": summary}
    accepted_count = 0
    for field_name in (
        "new_findings",
        "strengthened_findings",
        "revised_findings",
        "open_questions",
        "current_recommendations",
    ):
        accepted = []
        for item in list(raw.get(field_name, []) or [])[:_MAX_ITEMS_PER_SECTION]:
            if not isinstance(item, dict):
                continue
            text = _clean(item.get("text", ""), 220)
            task_ids = [
                str(value)
                for value in list(item.get("source_task_ids", []) or [])
                if str(value) in valid_task_ids
            ]
            evidence_ids = [
                str(value)
                for value in list(item.get("evidence_ids", []) or [])
                if str(value) in valid_evidence_ids
            ]
            if not text or not task_ids or not evidence_ids:
                continue
            accepted.append(
                {
                    "text": text,
                    "source_task_ids": list(dict.fromkeys(task_ids)),
                    "evidence_ids": list(dict.fromkeys(evidence_ids)),
                }
            )
        result[field_name] = accepted
        accepted_count += len(accepted)
    return result if accepted_count else None


def _build_fallback(
    *,
    topic: str,
    workspaces: list,
    papers: list,
    gaps: list,
    ideas: list,
) -> dict[str, Any]:
    latest = workspaces[0] if workspaces else None
    latest_task_id = str(getattr(latest, "task_id", "") or "")

    def item(text: str, evidence_id: str) -> dict[str, Any]:
        return {
            "text": text,
            "source_task_ids": [latest_task_id] if latest_task_id else [],
            "evidence_ids": [evidence_id] if evidence_id else [],
        }

    latest_ideas = []
    for idea in list(getattr(latest, "ideas", []) or [])[:3]:
        idea_id = str(getattr(idea, "idea_id", "") or "")
        latest_ideas.append(
            item(
                _clean(getattr(idea, "title", ""), 180),
                f"{latest_task_id}::idea::{idea_id}" if latest_task_id else "",
            )
        )
    latest_gaps = []
    for gap in list(getattr(latest, "gaps", []) or [])[:3]:
        gap_id = str(getattr(gap, "gap_id", "") or "")
        latest_gaps.append(
            item(
                _clean(getattr(gap, "summary", ""), 180),
                f"{latest_task_id}::gap::{gap_id}" if latest_task_id else "",
            )
        )

    return {
        "headline": f"{topic} 的阶段性研究结论",
        "summary": (
            f"当前累计整合 {len(workspaces)} 轮研究、{len(papers)} 篇论文线索、"
            f"{len(gaps)} 条研究空白和 {len(ideas)} 条研究建议。"
        ),
        "new_findings": latest_ideas,
        "strengthened_findings": [],
        "revised_findings": [],
        "open_questions": latest_gaps,
        "current_recommendations": latest_ideas,
        "source": "deterministic",
    }


def _clean(value: Any, max_length: int) -> str:
    return clean_internal_context_text(str(value or ""), max_length=max_length)
