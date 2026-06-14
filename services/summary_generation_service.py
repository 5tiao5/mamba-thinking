from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List

from product_agent.llm_client import call_openai_json, has_openai_key
from product_agent.observability import live_status
from product_agent.domain import ResearchIdea


@dataclass
class SummaryGenerationInput:
    topic: str
    alignment_score: float
    paper_nodes: List[Any]
    detected_gaps: List[Any]
    ideas: List[ResearchIdea]
    report_text: str
    evidence_snapshot: Dict[str, Any] = field(default_factory=dict)
    allow_recommendation: bool = True


@dataclass
class SummaryGenerationOutput:
    summary: Dict[str, Any]
    source: str


class SummaryGenerationService:
    def run(self, request: SummaryGenerationInput) -> SummaryGenerationOutput:
        summary = self.build_structured_summary(request)
        if not request.allow_recommendation:
            return SummaryGenerationOutput(summary, "deterministic-evidence-limited")
        if os.environ.get("SKIP_SUMMARY_LLM") == "1" or not has_openai_key():
            return SummaryGenerationOutput(summary, "deterministic")

        prompt = f"""
Generate an optional headline and recommendation for the research summary below.
Return valid JSON only in this format:
{{
  "headline": "...",
  "recommendation": "..."
}}

Topic: {request.topic}
Alignment score: {request.alignment_score}
Evidence snapshot ID: {request.evidence_snapshot.get("snapshot_id", "")}
Top gaps: {json.dumps([str(gap.get('id') or gap.get('gap_id')) if isinstance(gap, dict) else str(index) for index, gap in enumerate(request.detected_gaps[:4])], ensure_ascii=False)}
Ideas: {json.dumps([{'idea_id': idea.idea_id, 'title': idea.title} for idea in request.ideas[:3]], ensure_ascii=False)}
"""
        if has_openai_key():
            live_status("Calling LLM to enrich the structured summary headline and recommendation.")
        data = call_openai_json(
            prompt,
            system="You are a Chinese research summary writer. Return valid JSON only.",
            max_output_tokens=300,
        )
        if data and isinstance(data, dict):
            headline = data.get("headline")
            recommendation = data.get("recommendation")
            if isinstance(headline, str) and headline.strip():
                summary["headline"] = headline.strip()
            if isinstance(recommendation, str) and recommendation.strip():
                summary["recommendation"] = recommendation.strip()
            summary["source"] = "llm-enriched"
            return SummaryGenerationOutput(summary, "llm-enriched")

        return SummaryGenerationOutput(summary, "deterministic")

    def build_structured_summary(self, request: SummaryGenerationInput) -> Dict[str, Any]:
        topic = str(request.topic or "Research topic")
        alignment_score = float(request.alignment_score or 0.0)
        top_gaps = self._top_gaps(request.detected_gaps, 3)
        top_ideas = [
            {"idea_id": idea.idea_id, "title": idea.title, "confidence": float(idea.confidence or 0.0)}
            for idea in request.ideas[:3]
        ]
        summary = {
            "summary_id": self._stable_summary_id(topic, alignment_score, top_gaps, top_ideas),
            "version": "v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "headline": f"{topic} 研究审计概览",
            "score": alignment_score,
            "top_gaps": top_gaps,
            "top_gap_ids": [gap["gap_id"] for gap in top_gaps],
            "top_ideas": top_ideas,
            "top_idea_ids": [idea["idea_id"] for idea in top_ideas],
            "counts": {
                "papers": len(request.paper_nodes),
                "gaps": len(request.detected_gaps),
                "ideas": len(request.ideas),
            },
            "recommendation": (
                "Focus on the top gaps and refine the ideas into actionable research plans."
                if request.allow_recommendation
                else "Direct evidence is insufficient. Narrow the query and retrieve topic-anchored papers before forming research recommendations."
            ),
            "source": "deterministic",
            "evidence_snapshot_id": str(request.evidence_snapshot.get("snapshot_id", "") or ""),
            "evidence_stats": dict(request.evidence_snapshot.get("stats", {}) or {}),
            "conclusion_contract": dict(
                request.evidence_snapshot.get("conclusion_contract", {}) or {}
            ),
        }
        return summary

    def _stable_summary_id(self, topic: str, score: float, top_gaps: List[Dict[str, str]], top_ideas: List[Dict[str, Any]]) -> str:
        seed = json.dumps(
            {"topic": topic, "score": score, "top_gaps": top_gaps, "top_ideas": top_ideas},
            sort_keys=True,
            ensure_ascii=False,
        )
        return f"summary_{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:10]}"

    def _top_gaps(self, gaps: List[Any], limit: int) -> List[Dict[str, str]]:
        normalized = []
        for index, gap in enumerate(gaps[:limit]):
            if isinstance(gap, dict):
                gap_id = str(gap.get("id") or gap.get("gap_id") or f"gap_{index}")
                summary = str(gap.get("description", gap.get("summary", str(gap)))).strip()
            else:
                gap_id = f"gap_{index}"
                summary = str(gap).strip()
            normalized.append({"gap_id": gap_id, "summary": summary})
        return normalized
