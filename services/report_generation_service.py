from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List

from llm_client import call_openai_text, has_openai_key
from observability import live_status
from product_agent.domain import ResearchIdea


@dataclass
class ReportGenerationInput:
    topic: str
    alignment_score: float
    expert_taxonomy: Dict[str, Any]
    audit_reports: List[Any]
    detected_gaps: List[Any]
    ideas: List[ResearchIdea]
    mermaid: str


@dataclass
class ReportGenerationOutput:
    report_text: str
    source: str
    report_id: str


class ReportGenerationService:
    def run(self, request: ReportGenerationInput) -> ReportGenerationOutput:
        report_id = self._stable_report_id(request)
        if os.environ.get("SKIP_REPORT_LLM") == "1" or not has_openai_key():
            return ReportGenerationOutput(self._fallback_report(request), "fallback-balanced", report_id)

        prompt = f"""
Write a Chinese research evolution audit report with the following sections:
1. Topic overview
2. Expert taxonomy
3. Evolution narrative
4. Audit findings and gaps
5. Three research ideas

Writing requirements:
- The main body should be in Chinese.
- Taxonomy branch names and important technical terms may stay in English.
- Paper titles, model names, benchmarks, datasets, and frameworks should stay in English.
- Use natural Chinese-English mixed academic writing instead of forcing every term into Chinese.

Topic: {request.topic}
Alignment score: {request.alignment_score}
Taxonomy: {json.dumps(request.expert_taxonomy, ensure_ascii=False)[:3000]}
Audit reports: {json.dumps(request.audit_reports[:12], ensure_ascii=False)}
Detected gaps: {json.dumps(request.detected_gaps[:12], ensure_ascii=False)}
Ideas: {json.dumps([{"idea_id": idea.idea_id, "title": idea.title} for idea in request.ideas], ensure_ascii=False)}
"""
        if has_openai_key():
            live_status("Calling LLM to write the final report.")
        text = call_openai_text(
            prompt,
            system="You are a Chinese research review writer.",
            max_output_tokens=3200,
        )
        if text:
            cleaned = self._sanitize_report_text(text)
            return ReportGenerationOutput(
                cleaned + "\n\n## Mermaid 图谱\n\n```mermaid\n" + request.mermaid + "\n```\n",
                "llm",
                report_id,
            )

        return ReportGenerationOutput(self._fallback_report(request), "fallback", report_id)

    def _stable_report_id(self, request: ReportGenerationInput) -> str:
        seed = json.dumps(
            {
                "topic": request.topic,
                "alignment_score": request.alignment_score,
                "ideas": [idea.idea_id for idea in request.ideas],
                "mermaid": request.mermaid,
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        return f"report_{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:10]}"

    def _sanitize_report_text(self, text: str) -> str:
        cleaned = (text or "").strip()
        if not cleaned:
            return cleaned

        lines = [line.rstrip() for line in cleaned.splitlines()]
        openers = ("好的", "遵照您的要求", "根据您的要求", "当然", "下面是")

        while lines and any(lines[0].strip().startswith(prefix) for prefix in openers):
            lines.pop(0)
            while lines and not lines[0].strip():
                lines.pop(0)

        cleaned = "\n".join(lines).strip()
        heading_match = re.search(r"(^#{1,6}\s+.+$)", cleaned, re.MULTILINE)
        if heading_match and heading_match.start() > 0:
            cleaned = cleaned[heading_match.start() :].lstrip()

        return cleaned

    def _fallback_report(self, request: ReportGenerationInput) -> str:
        papers = request.expert_taxonomy
        edges = []
        taxonomy = request.expert_taxonomy
        reports = request.audit_reports
        gaps = request.detected_gaps

        lines = [
            f"# 科研演进审计报告：{request.topic}",
            "",
            "## 1. 主题概览",
            f"本次 Agent 共收集论文 {len(request.ideas)} 条建议，对齐分数为 {request.alignment_score}。",
            "",
            "## 2. 专家 Taxonomy",
            "```json",
            json.dumps(taxonomy, ensure_ascii=False, indent=2),
            "```",
            "",
            "## 3. 审计发现",
        ]
        lines.extend([f"- {item}" for item in reports[:15]] or ["- 暂无明显审计风险。"])
        lines.extend(["", "## 4. 检测到的 Gap"])
        lines.extend([f"- {item}" for item in gaps[:15]] or ["- 暂无明显 gap。"])
        lines.extend(["", "## 5. 研究选题建议"])
        lines.extend([f"{index}. {getattr(idea, 'title', str(idea))}" for index, idea in enumerate(request.ideas, 1)])
        lines.extend(["", "## Mermaid 图谱", "```mermaid", request.mermaid, "```"])
        return "\n".join(lines)
