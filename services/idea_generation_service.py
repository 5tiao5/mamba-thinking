from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List

from llm_client import call_openai_json, call_openai_text, has_openai_key
from observability import live_status
from product_agent.domain import ResearchIdea


@dataclass
class IdeaGenerationInput:
    task_id: str
    topic: str
    papers: List[Any]
    gaps: List[Any]


@dataclass
class IdeaGenerationOutput:
    ideas: List[ResearchIdea]
    source: str


class IdeaGenerationService:
    def run(self, request: IdeaGenerationInput) -> IdeaGenerationOutput:
        papers = request.papers[:12]
        gaps = request.gaps[:10]

        prompt = f"""
Please generate 3 concrete and clearly different Chinese research ideas based on the papers and gaps below.

Requirements:
- Each idea should stay close to the evidence in the papers and gaps.
- Each idea should include: id, title, motivation, approach, feasibility, contribution,
  related_papers, derived_from_gaps, confidence, tags, and raw_text.
- Keep paper titles, model names, benchmarks, datasets, and framework names in English when appropriate.
- Return JSON only in this format:
{{
  "ideas": [
    {{
      "id": "...",
      "title": "...",
      "motivation": "...",
      "approach": "...",
      "feasibility": "...",
      "contribution": "...",
      "related_papers": ["..."],
      "derived_from_gaps": ["..."],
      "confidence": 0.0,
      "tags": ["..."],
      "raw_text": "..."
    }}
  ]
}}

Papers:
{json.dumps([_paper_brief(p) for p in papers], ensure_ascii=False)}

Detected gaps:
{json.dumps(gaps, ensure_ascii=False)}
"""
        if has_openai_key():
            live_status("Calling LLM to generate structured research ideas.")
        data = call_openai_json(
            prompt,
            system=(
                "You are a research idea advisor. Generate grounded, specific ideas and return valid JSON only."
            ),
            max_output_tokens=2600,
        )
        if data and isinstance(data.get("ideas"), list):
            ideas = self._parse_json_ideas(data["ideas"], request)
            if len(ideas) >= 3:
                return IdeaGenerationOutput(ideas[:3], "llm-json")

        if os.environ.get("BALANCED_MODE") == "1":
            return IdeaGenerationOutput(self._fallback_ideas(request), "fallback-balanced-json-failed")

        if has_openai_key():
            live_status("Idea JSON parsing failed; asking the LLM for text-format ideas.")
        text = call_openai_text(
            prompt.replace(
                'Return JSON only in this format:\n{\n  "ideas": [\n    {\n      "id": "...",\n      "title": "...",\n      "motivation": "...",\n      "approach": "...",\n      "feasibility": "...",\n      "contribution": "...",\n      "related_papers": ["..."],\n      "derived_from_gaps": ["..."],\n      "confidence": 0.0,\n      "tags": ["..."],\n      "raw_text": "..."\n    }\n  ]\n}',
                "If JSON is difficult, return 3 clearly separated ideas with title, motivation, approach, feasibility, contribution, and raw_text.",
            ),
            system="You are a research idea advisor. Output 3 grounded Chinese research ideas.",
            max_output_tokens=2600,
        )
        parsed = self._extract_three_ideas(text or "", request)
        if len(parsed) >= 3:
            return IdeaGenerationOutput(parsed[:3], "llm-text")

        return IdeaGenerationOutput(self._fallback_ideas(request), "fallback")

    def _parse_json_ideas(self, items: List[Any], request: IdeaGenerationInput) -> List[ResearchIdea]:
        ideas: List[ResearchIdea] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title", "")).strip()
            if not title:
                continue
            raw_text = str(item.get("raw_text", "")).strip()
            motivation = str(item.get("motivation", "")).strip()
            approach = str(item.get("approach", "")).strip()
            feasibility = str(item.get("feasibility", "")).strip()
            contribution = str(item.get("contribution", "")).strip()
            idea = ResearchIdea(
                idea_id=str(item.get("id", self._stable_id(f"{request.task_id}|{title}|{raw_text or motivation}"))),
                title=title,
                motivation=motivation,
                approach=approach,
                feasibility=feasibility,
                contribution=contribution,
                related_papers=self._normalize_list(item.get("related_papers", []), request.papers, title),
                derived_from_gaps=self._normalize_gap_ids(item.get("derived_from_gaps", []), request.gaps),
                confidence=self._normalize_confidence(item.get("confidence", None), 0.8),
                tags=self._normalize_list(item.get("tags", []), request.papers, title, tags_only=True),
                raw_text=raw_text or self._build_raw_text(item),
            )
            idea = self._enrich_idea(idea, request)
            ideas.append(idea)
        return ideas

    def _normalize_list(self, raw_value: Any, papers: List[Any], title: str, tags_only: bool = False) -> List[str]:
        if isinstance(raw_value, list):
            cleaned = [str(item).strip() for item in raw_value if str(item).strip()]
            if tags_only:
                return cleaned[:5]
            return cleaned[:3]
        if tags_only:
            return self._derive_tags(title)
        return []

    def _normalize_gap_ids(self, raw_value: Any, gaps: List[Any]) -> List[str]:
        if isinstance(raw_value, list) and raw_value:
            return [str(item).strip() for item in raw_value if str(item).strip()][:3]
        return []

    def _normalize_confidence(self, raw_value: Any, default: float) -> float:
        try:
            value = float(raw_value)
            return max(0.0, min(1.0, value))
        except Exception:
            return default

    def _build_raw_text(self, item: Dict[str, Any]) -> str:
        return " ".join(
            str(item.get(field, "")).strip()
            for field in ["title", "motivation", "approach", "feasibility", "contribution"]
            if str(item.get(field, "")).strip()
        )

    def _enrich_idea(self, idea: ResearchIdea, request: IdeaGenerationInput) -> ResearchIdea:
        if not idea.related_papers:
            idea.related_papers = self._derive_related_papers(idea.raw_text or idea.title, request.papers)
        if not idea.derived_from_gaps:
            idea.derived_from_gaps = self._derive_gap_ids(idea.raw_text or idea.title, request.gaps)
        if not idea.tags:
            idea.tags = self._derive_tags(idea.title)
        if not idea.raw_text:
            idea.raw_text = idea.title
        if not idea.idea_id:
            idea.idea_id = self._stable_id(f"{request.task_id}|{idea.title}|{idea.raw_text}")
        return idea

    def _extract_three_ideas(self, text: str, request: IdeaGenerationInput) -> List[ResearchIdea]:
        if not text.strip():
            return []
        chunks = re.split(r"(?:^|\n)\s*(?:\d+[.\u3001)]|选题[一二三123][:：])\s*", text)
        ideas: List[ResearchIdea] = []
        for chunk in chunks:
            candidate = chunk.strip(" \n-•")
            if len(candidate) < 40:
                continue
            title = self._extract_title(candidate)
            ideas.append(
                ResearchIdea(
                    idea_id=self._stable_id(f"{request.task_id}|{title}|{candidate}"),
                    title=title,
                    motivation="",
                    approach="",
                    feasibility="",
                    contribution="",
                    related_papers=self._derive_related_papers(candidate, request.papers),
                    derived_from_gaps=self._derive_gap_ids(candidate, request.gaps),
                    confidence=0.65,
                    tags=self._derive_tags(candidate),
                    raw_text=candidate,
                )
            )
            if len(ideas) >= 3:
                break
        if ideas:
            return ideas
        lines = [line.strip("-•\n") for line in text.splitlines() if len(line.strip()) > 40]
        for line in lines[:3]:
            title = self._extract_title(line)
            ideas.append(
                ResearchIdea(
                    idea_id=self._stable_id(f"{request.task_id}|{title}|{line}"),
                    title=title,
                    motivation="",
                    approach="",
                    feasibility="",
                    contribution="",
                    related_papers=self._derive_related_papers(line, request.papers),
                    derived_from_gaps=self._derive_gap_ids(line, request.gaps),
                    confidence=0.65,
                    tags=self._derive_tags(line),
                    raw_text=line,
                )
            )
        return ideas

    def _fallback_ideas(self, request: IdeaGenerationInput) -> List[ResearchIdea]:
        topic = str(request.topic or "the topic")
        gaps = request.gaps
        gap_hint = (
            str(gaps[0].get("description", gaps[0])) if isinstance(gaps[0], dict) else str(gaps[0])
        ) if gaps else "the current graph still has coverage gaps and weak evidence links"
        paper_ids = self._paper_ids(request.papers[:3])
        return [
            ResearchIdea(
                idea_id=self._stable_id(f"{request.task_id}|idea1"),
                title=f"选题一：面向 {topic} 的可解释演进图补全方法。",
                motivation=f"研究动机：{gap_hint}。",
                approach="可行方法：联合引用关系、taxonomy 对齐和关键词重合度，自动发现缺失文献链。",
                feasibility="可行性：可以直接复用当前 Agent 的 graph 与 auditor 模块。",
                contribution="预期贡献：提高研究综述和演进图的证据完整性。",
                related_papers=paper_ids,
                derived_from_gaps=self._gap_ids(gaps),
                confidence=0.55,
                tags=["graph audit", "gap detection", "research idea"],
                raw_text="",
            ),
            ResearchIdea(
                idea_id=self._stable_id(f"{request.task_id}|idea2"),
                title=f"选题二：基于审计反馈的 {topic} 研究 gap 自动发现。",
                motivation="研究动机：传统综述高度依赖人工阅读，难以及时发现逻辑断层。",
                approach="可行方法：把低置信节点、弱跨分类边和缺失概念转化为可追踪 gap。",
                feasibility="可行性：当前 detected_gaps 已经提供初始标签。",
                contribution="预期贡献：形成一套可复现的选题推荐流程。",
                related_papers=paper_ids,
                derived_from_gaps=self._gap_ids(gaps),
                confidence=0.55,
                tags=["audit", "automation", "gap-based"],
                raw_text="",
            ),
            ResearchIdea(
                idea_id=self._stable_id(f"{request.task_id}|idea3"),
                title=f"选题三：融合 LLM 与规则校验的 {topic} 改进关系验证。",
                motivation="研究动机：仅凭引用关系并不能证明后续论文真的改进了前作。",
                approach="可行方法：规则先筛候选边，再用 LLM 检查摘要里的改进声明与实验支撑。",
                feasibility="可行性：现有 OpenAI/DeepSeek 兼容层可直接作为增强模块。",
                contribution="预期贡献：降低错误演进边对科研判断的干扰。",
                related_papers=paper_ids,
                derived_from_gaps=self._gap_ids(gaps),
                confidence=0.55,
                tags=["LLM", "verification", "evolution"],
                raw_text="",
            ),
        ]

    def _stable_id(self, seed: str) -> str:
        return f"idea_{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:10]}"

    def _extract_title(self, raw_text: str) -> str:
        first_line = raw_text.strip().splitlines()[0] if raw_text.strip() else "Untitled Idea"
        first_line = re.sub(r"^\s*\d+[\.、\)]\s*", "", first_line).strip()
        return first_line[:120] or "Untitled Idea"

    def _derive_tags(self, text: str) -> List[str]:
        tokens = re.findall(r"[A-Za-z0-9\u4e00-\u9fff]{4,}", text)
        tags = [token.lower() for token in tokens if len(token) > 3][:5]
        return list(dict.fromkeys(tags))

    def _derive_related_papers(self, text: str, papers: List[Any]) -> List[str]:
        if not papers:
            return []
        text_lower = text.lower()
        selected: List[str] = []
        for paper in papers:
            payload = self._paper_payload(paper)
            paper_text = " ".join(
                [payload.get("title", ""), payload.get("abstract", ""), payload.get("taxonomy_category", "")]
            ).lower()
            if any(token in paper_text for token in re.findall(r"\w{5,}", text_lower)):
                selected.append(payload.get("paper_id", ""))
        if not selected:
            selected = [self._paper_payload(paper).get("paper_id", "") for paper in papers[:3]]
        return [pid for pid in selected if pid][:3]

    def _derive_gap_ids(self, text: str, gaps: List[Any]) -> List[str]:
        if not gaps:
            return []
        text_lower = text.lower()
        candidates: List[str] = []
        for index, gap in enumerate(gaps):
            payload = self._gap_payload(gap, index)
            gap_text = payload.get("summary", "").lower()
            if any(token in gap_text for token in re.findall(r"\w{5,}", text_lower)):
                candidates.append(payload.get("gap_id", ""))
        if not candidates:
            candidates = [self._gap_payload(gap, index).get("gap_id", "") for index, gap in enumerate(gaps[:2])]
        return [gid for gid in candidates if gid][:3]

    def _paper_payload(self, paper: Any) -> Dict[str, Any]:
        if isinstance(paper, dict):
            return paper
        return {
            "paper_id": getattr(paper, "paper_id", ""),
            "title": getattr(paper, "title", ""),
            "abstract": getattr(paper, "abstract", ""),
            "taxonomy_category": getattr(paper, "taxonomy_category", ""),
        }

    def _gap_payload(self, gap: Any, index: int) -> Dict[str, Any]:
        if isinstance(gap, dict):
            return {
                "gap_id": str(gap.get("id") or gap.get("gap_id") or f"gap_{index}"),
                "summary": str(gap.get("description", gap.get("summary", str(gap)))).strip(),
            }
        return {"gap_id": f"gap_{index}", "summary": str(gap).strip()}

    def _gap_ids(self, gaps: List[Any]) -> List[str]:
        return [self._gap_payload(gap, index).get("gap_id", "") for index, gap in enumerate(gaps[:3]) if self._gap_payload(gap, index).get("gap_id", "")]

    def _paper_ids(self, papers: List[Any]) -> List[str]:
        return [self._paper_payload(paper).get("paper_id", "") for paper in papers if self._paper_payload(paper).get("paper_id", "")][:3]


def _paper_brief(paper: Any) -> Dict[str, str]:
    if isinstance(paper, dict):
        payload = paper
    else:
        payload = {
            "paper_id": getattr(paper, "paper_id", ""),
            "title": getattr(paper, "title", ""),
            "abstract": getattr(paper, "abstract", ""),
            "taxonomy_category": getattr(paper, "taxonomy_category", ""),
        }
    return {
        "id": payload.get("paper_id", ""),
        "title": payload.get("title", ""),
        "category": payload.get("taxonomy_category", ""),
        "abstract": payload.get("abstract", "")[:500],
    }
