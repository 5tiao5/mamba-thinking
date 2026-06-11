from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
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
    evidence_snapshot: Dict[str, Any] = field(default_factory=dict)


@dataclass
class IdeaGenerationOutput:
    ideas: List[ResearchIdea]
    source: str


class IdeaGenerationService:
    def run(self, request: IdeaGenerationInput) -> IdeaGenerationOutput:
        papers = request.papers[:12]
        gaps = request.gaps[:10]

        prompt = f"""
请基于下面的论文证据与研究空白，生成 3 个具体、彼此区分明显的研究建议。

写作要求：
- 以中文表达为主，只保留必要的英文术语，例如 LLM、GPT-4、benchmark、dataset、paper title。
- 不要写成论文摘要，尽量像“给用户看的研究工作台建议”。
- 每个字段都要简洁自然：
  - title：一句中文标题，必要时保留少量英文术语
  - motivation：说明为什么值得做，1-2 句
  - approach：说明建议做法，1-3 句
  - feasibility：说明可行性，1-2 句
  - contribution：说明预期贡献，1-2 句
- 不要在字段里重复“研究建议：”“可行性：”“预期贡献：”这类标签。
- 每条建议必须紧贴 papers 和 gaps，不能凭空发散。

请只返回 JSON，格式如下：
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

Frozen evidence snapshot:
{json.dumps(request.evidence_snapshot, ensure_ascii=False)[:6000]}
"""
        if has_openai_key():
            live_status("Calling LLM to generate structured research ideas.")
        data = call_openai_json(
            prompt,
            system=(
                "You are a research idea advisor. Generate grounded ideas in concise Chinese and return valid JSON only."
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
                '请只返回 JSON，格式如下：\n{\n  "ideas": [\n    {\n      "id": "...",\n      "title": "...",\n      "motivation": "...",\n      "approach": "...",\n      "feasibility": "...",\n      "contribution": "...",\n      "related_papers": ["..."],\n      "derived_from_gaps": ["..."],\n      "confidence": 0.0,\n      "tags": ["..."],\n      "raw_text": "..."\n    }\n  ]\n}',
                "如果 JSON 难以稳定输出，请改成 3 条清晰分隔的研究建议，每条都包含 title、motivation、approach、feasibility、contribution。",
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
            title = self._polish_title(str(item.get("title", "")).strip())
            if not title:
                continue
            raw_text = str(item.get("raw_text", "")).strip()
            motivation = self._polish_field("motivation", str(item.get("motivation", "")).strip())
            approach = self._polish_field("approach", str(item.get("approach", "")).strip())
            feasibility = self._polish_field("feasibility", str(item.get("feasibility", "")).strip())
            contribution = self._polish_field("contribution", str(item.get("contribution", "")).strip())
            idea = ResearchIdea(
                idea_id=str(item.get("id", self._stable_id(f"{request.task_id}|{title}|{raw_text or motivation}"))),
                title=title,
                motivation=motivation,
                approach=approach,
                feasibility=feasibility,
                contribution=contribution,
                related_papers=self._normalize_list(item.get("related_papers", []), title, tags_only=False),
                derived_from_gaps=self._normalize_gap_ids(item.get("derived_from_gaps", [])),
                confidence=self._normalize_confidence(item.get("confidence", None), 0.8),
                tags=self._normalize_list(item.get("tags", []), title, tags_only=True),
                raw_text=raw_text or self._build_raw_text(item),
            )
            idea = self._enrich_idea(idea, request)
            ideas.append(idea)
        return ideas

    def _normalize_list(self, raw_value: Any, title: str, tags_only: bool = False) -> List[str]:
        if isinstance(raw_value, list):
            cleaned = [str(item).strip() for item in raw_value if str(item).strip()]
            if tags_only:
                return cleaned[:5]
            return cleaned[:3]
        if tags_only:
            return self._derive_tags(title)
        return []

    def _normalize_gap_ids(self, raw_value: Any) -> List[str]:
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
            idea.raw_text = " ".join(
                part for part in [idea.title, idea.motivation, idea.approach, idea.feasibility, idea.contribution] if part
            )
        if not idea.idea_id:
            idea.idea_id = self._stable_id(f"{request.task_id}|{idea.title}|{idea.raw_text}")
        return idea

    def _extract_three_ideas(self, text: str, request: IdeaGenerationInput) -> List[ResearchIdea]:
        if not text.strip():
            return []
        chunks = re.split(r"(?:^|\n)\s*(?:\d+[.\u3001)]|选题[一二三123][：:])\s*", text)
        ideas: List[ResearchIdea] = []
        for chunk in chunks:
            candidate = chunk.strip(" \n-—•")
            if len(candidate) < 40:
                continue
            title = self._extract_title(candidate)
            idea = ResearchIdea(
                idea_id=self._stable_id(f"{request.task_id}|{title}|{candidate}"),
                title=self._polish_title(title),
                motivation=self._polish_field("motivation", candidate),
                approach="",
                feasibility="",
                contribution="",
                related_papers=self._derive_related_papers(candidate, request.papers),
                derived_from_gaps=self._derive_gap_ids(candidate, request.gaps),
                confidence=0.65,
                tags=self._derive_tags(candidate),
                raw_text=candidate,
            )
            ideas.append(self._enrich_idea(idea, request))
            if len(ideas) >= 3:
                break
        if ideas:
            return ideas
        lines = [line.strip("-—•\n") for line in text.splitlines() if len(line.strip()) > 40]
        for line in lines[:3]:
            title = self._extract_title(line)
            idea = ResearchIdea(
                idea_id=self._stable_id(f"{request.task_id}|{title}|{line}"),
                title=self._polish_title(title),
                motivation=self._polish_field("motivation", line),
                approach="",
                feasibility="",
                contribution="",
                related_papers=self._derive_related_papers(line, request.papers),
                derived_from_gaps=self._derive_gap_ids(line, request.gaps),
                confidence=0.65,
                tags=self._derive_tags(line),
                raw_text=line,
            )
            ideas.append(self._enrich_idea(idea, request))
        return ideas

    def _fallback_ideas(self, request: IdeaGenerationInput) -> List[ResearchIdea]:
        topic = str(request.topic or "当前主题")
        gaps = request.gaps
        gap_hint = (
            self._humanize_gap_description(
                str(gaps[0].get("description", gaps[0].get("summary", gaps[0])))
            )
            if isinstance(gaps[0], dict)
            else self._humanize_gap_description(str(gaps[0]))
        ) if gaps else "当前证据仍存在覆盖不足与关系不稳的问题"
        paper_ids = self._paper_ids(request.papers[:3])
        return [
            ResearchIdea(
                idea_id=self._stable_id(f"{request.task_id}|idea1"),
                title=f"围绕 {topic} 的研究方向补全与证据增强",
                motivation=self._polish_field("motivation", f"当前主要问题是：{gap_hint}。如果不先补齐关键方向，后续 taxonomy 和演进判断都会偏弱。"),
                approach=self._polish_field("approach", "建议先围绕缺失分支补充代表性论文，再结合 taxonomy 对齐、引用关系和关键词重合度，自动识别还未被覆盖的研究方向。"),
                feasibility=self._polish_field("feasibility", "可以直接复用当前 graph、auditor 与 taxonomy grounding 链路，只需要补强检索和证据筛选。"),
                contribution=self._polish_field("contribution", "有望提升研究综述的证据完整度，并让后续 gap 判断更可信。"),
                related_papers=paper_ids,
                derived_from_gaps=self._gap_ids(gaps),
                confidence=0.55,
                tags=["taxonomy", "coverage", "evidence"],
                raw_text="",
            ),
            ResearchIdea(
                idea_id=self._stable_id(f"{request.task_id}|idea2"),
                title=f"面向 {topic} 的研究空白自动发现与优先级排序",
                motivation=self._polish_field("motivation", "当前 gap 发现仍然偏依赖人工解读，容易漏掉低置信节点、弱关系边和关键概念缺失。"),
                approach=self._polish_field("approach", "可以将低置信节点、跨分支弱关系和缺失概念统一映射成可追踪的 gap，再结合优先级规则给出补证顺序。"),
                feasibility=self._polish_field("feasibility", "现有 detected_gaps 已提供初始标签与描述，补一层规则排序即可形成第一版能力。"),
                contribution=self._polish_field("contribution", "可以形成一套可复用的选题发现流程，帮助用户快速知道先补什么证据。"),
                related_papers=paper_ids,
                derived_from_gaps=self._gap_ids(gaps),
                confidence=0.55,
                tags=["gap detection", "prioritization", "audit"],
                raw_text="",
            ),
            ResearchIdea(
                idea_id=self._stable_id(f"{request.task_id}|idea3"),
                title=f"结合 LLM 与规则校验的 {topic} 演进关系验证",
                motivation=self._polish_field("motivation", "仅凭引用或共词关系，并不能证明后续论文真的在方法、实验或结论上改进了前作。"),
                approach=self._polish_field("approach", "建议先用规则筛出候选改进边，再让 LLM 检查摘要与方法描述中是否存在明确的改进声明与证据。"),
                feasibility=self._polish_field("feasibility", "当前 OpenAI / DeepSeek 兼容层已经可用，可以直接作为关系复核模块。"),
                contribution=self._polish_field("contribution", "能减少错误演进边对研究判断的干扰，让演进图更适合作为研究线索图使用。"),
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
        first_line = raw_text.strip().splitlines()[0] if raw_text.strip() else "未命名研究建议"
        first_line = re.sub(r"^\s*\d+[\.、)]\s*", "", first_line).strip()
        return first_line[:120] or "未命名研究建议"

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
        result: List[str] = []
        for index, gap in enumerate(gaps[:3]):
            gap_id = self._gap_payload(gap, index).get("gap_id", "")
            if gap_id:
                result.append(gap_id)
        return result

    def _paper_ids(self, papers: List[Any]) -> List[str]:
        result: List[str] = []
        for paper in papers:
            paper_id = self._paper_payload(paper).get("paper_id", "")
            if paper_id:
                result.append(paper_id)
        return result[:3]

    def _polish_title(self, text: str) -> str:
        cleaned = self._cleanup_text(text)
        cleaned = re.sub(r"^(idea|research idea)\s*[:：-]\s*", "", cleaned, flags=re.IGNORECASE)
        title_map = {
            "AI-Assisted Reviewer Training Framework for Software Engineering Peer Review": "面向软件工程同行评审的 AI 辅助审稿训练框架",
            "Empirical Study of Cognitive Biases in AI-Generated Code: A Replication and Extension": "AI 生成代码中的认知偏差复现实证研究",
        }
        return title_map.get(cleaned, cleaned)

    def _polish_field(self, field: str, text: str) -> str:
        cleaned = self._cleanup_text(text)
        cleaned = self._strip_field_prefix(field, cleaned)
        cleaned = self._localize_common_phrases(cleaned)
        cleaned = self._compress_sentences(cleaned, field)
        cleaned = self._cleanup_text(cleaned)
        return cleaned

    def _cleanup_text(self, text: str) -> str:
        cleaned = (text or "").strip()
        if not cleaned:
            return ""
        cleaned = cleaned.replace("《", "").replace("》", "").replace("「", "").replace("」", "")
        cleaned = cleaned.replace("（", "(").replace("）", ")")
        cleaned = re.sub(r"\s+", " ", cleaned)
        cleaned = re.sub(r"\s*([,.;:!?])\s*", r"\1 ", cleaned)
        cleaned = cleaned.replace(" ,", ",").replace(" .", ".")
        cleaned = re.sub(r"([。！？；])\1+", r"\1", cleaned)
        cleaned = re.sub(r"([,，])\1+", r"\1", cleaned)
        return cleaned.strip(" \n\t,，;；")

    def _strip_field_prefix(self, field: str, text: str) -> str:
        prefixes = {
            "motivation": ["研究动机", "动机", "Motivation"],
            "approach": ["建议做法", "可行方法", "方法", "Approach"],
            "feasibility": ["可行性", "Feasibility"],
            "contribution": ["预期贡献", "Contribution"],
        }
        cleaned = text
        for prefix in prefixes.get(field, []):
            cleaned = re.sub(rf"^{re.escape(prefix)}\s*[:：]\s*", "", cleaned, flags=re.IGNORECASE)
        return cleaned.strip()

    def _localize_common_phrases(self, text: str) -> str:
        replacements = [
            (r"\bThe rapid growth of\b", "随着"),
            (r"\bhas outpaced the availability of\b", "的增长已经超过了"),
            (r"\bcreating a sustainability crisis in\b", "，使"),
            (r"\bExisting literature\b", "现有研究"),
            (r"\bhighlights the need for\b", "表明当前需要"),
            (r"\bbut lacks concrete solutions for\b", "但仍缺少针对"),
            (r"\bThis research gap presents an opportunity to\b", "因此可以围绕"),
            (r"\bDevelop a prototype system that uses\b", "建议先实现一个原型系统，利用"),
            (r"\bto generate initial review comments for submitted papers\b", "为投稿论文生成初步评审建议"),
            (r"\bfocusing on\b", "重点关注"),
            (r"\bThe system will include\b", "系统可包含"),
            (r"\bwhere they compare\b", "用于比较"),
            (r"\bThe framework will be evaluated through\b", "可以通过"),
            (r"\bRequires access to\b", "需要具备"),
            (r"\bThe annotation process is time-consuming but can be crowdsourced\b", "标注流程较耗时，但可以通过众包或课程协作降低成本"),
            (r"\bFirst empirical evidence of\b", "可提供首个面向"),
            (r"\bproviding a foundation for\b", "并为"),
            (r"\bpeer review\b", "同行评审"),
            (r"\breviewer training\b", "审稿人训练"),
            (r"\bAI-assisted review\b", "AI 辅助评审"),
            (r"\bcognitive biases\b", "认知偏差"),
            (r"\bsoftware engineering\b", "软件工程"),
            (r"\bsubmitted papers\b", "投稿论文"),
        ]
        localized = text
        for pattern, replacement in replacements:
            localized = re.sub(pattern, replacement, localized, flags=re.IGNORECASE)
        localized = localized.replace("e.g.,", "例如")
        localized = localized.replace("e.g.", "例如")
        localized = localized.replace("This ", "这项")
        localized = localized.replace(" but ", "，但")
        localized = localized.replace(" and ", "，并")
        localized = re.sub(
            r"Missing required concepts in '([^']+)':\s*(.+)",
            r"方向“\1”还缺少这些关键概念：\2",
            localized,
            flags=re.IGNORECASE,
        )
        localized = re.sub(
            r"Missing taxonomy branch:\s*(.+)",
            r"当前证据尚未覆盖研究方向“\1”",
            localized,
            flags=re.IGNORECASE,
        )
        localized = re.sub(
            r"Unsupported improvement claim:\s*(.+?)\s*->\s*(.+)",
            r"“\1”到“\2”的改进关系暂时缺少证据支持",
            localized,
            flags=re.IGNORECASE,
        )
        return localized

    def _compress_sentences(self, text: str, field: str) -> str:
        max_sentences = {
            "motivation": 2,
            "approach": 3,
            "feasibility": 2,
            "contribution": 2,
        }.get(field, 2)
        chunks = [chunk.strip() for chunk in re.split(r"(?<=[。！？.!?])\s+", text) if chunk.strip()]
        if not chunks:
            return text
        compact = " ".join(chunks[:max_sentences]).strip()
        if field == "approach":
            compact = re.sub(r"^(可以|可先)\s*", "", compact)
            if compact and not compact.startswith("建议"):
                compact = f"建议先{compact}"
        return compact

    def _humanize_gap_description(self, text: str) -> str:
        normalized = self._cleanup_text(text)
        normalized = self._localize_common_phrases(normalized)
        normalized = normalized.replace(" in 软件工程", "（软件工程场景）")
        normalized = normalized.replace(". 。", "。")
        normalized = normalized.replace(", AI 辅助评审.", "、AI 辅助评审")
        normalized = normalized.replace("taxonomy", "研究方向图")
        normalized = normalized.replace("gap", "研究空白")
        return self._cleanup_text(normalized)


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
