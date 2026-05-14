from __future__ import annotations

import json
import os
import re
from typing import Dict, List

from llm_client import call_openai_json, call_openai_text, has_openai_key
from observability import live_status, record_decision, record_tool_event

from ..models import EvolutionEdge, PaperNode, ResearchState


def synthesizer_node(state: ResearchState) -> ResearchState:
    """
    Convert the internal analysis state into user-facing deliverables:
    report text, research ideas, and a Mermaid graph.

    This implementation is now part of the new `product_agent` pipeline instead
    of delegating to the legacy root-level synthesizer node.
    """

    papers = state.get("paper_nodes", {})
    edges = state.get("evolution_graph", [])
    mermaid = build_mermaid_graph(papers, edges)
    logs = list(state.get("logs", []))
    ideas, idea_source = generate_ideas(state)
    report, report_source = generate_report(state, ideas, mermaid)

    updated = dict(state)
    updated["generated_ideas"] = ideas
    updated["final_report"] = report
    updated["mermaid_graph"] = mermaid

    record_tool_event(
        updated,
        tool_name="LLM idea generator",
        input_summary=f"papers={len(papers)}, gaps={len(state.get('detected_gaps', []))}",
        status="success" if idea_source.startswith("llm") else "fallback",
        output_count=len(ideas),
        note=idea_source,
    )
    record_tool_event(
        updated,
        tool_name="LLM report writer",
        input_summary=f"ideas={len(ideas)}",
        status="success" if report_source == "llm" else "fallback",
        output_count=1,
        note=report_source,
    )
    record_decision(
        updated,
        stage="synthesizer",
        decision=f"Generated {len(ideas)} ideas and the final report.",
        reason="Turn audited evidence into user-facing outputs for the workspace and report.",
        next_step="outputs",
    )

    logs.append(f"Synthesizer generated {len(ideas)} ideas via {idea_source}.")
    logs.append(f"Synthesizer generated report via {report_source}.")
    updated["logs"] = logs
    return updated


def generate_ideas(state: ResearchState) -> tuple[List[str], str]:
    papers = list(state.get("paper_nodes", {}).values())[:12]
    gaps = state.get("detected_gaps", [])[:10]
    prompt = f"""
Please generate 3 concrete and clearly different Chinese research ideas based on the papers and gaps below.

Requirements:
- Each idea should stay close to the evidence in the papers and gaps.
- Each idea should include: title, motivation, possible method, feasibility, and expected contribution.
- Keep paper titles, model names, benchmarks, datasets, and framework names in English when appropriate.
- Return JSON only in this format:
{{"ideas": ["idea 1", "idea 2", "idea 3"]}}

Papers:
{json.dumps([_paper_brief(p) for p in papers], ensure_ascii=False)}

Detected gaps:
{json.dumps(gaps, ensure_ascii=False)}
"""
    if has_openai_key():
        live_status("Calling LLM to generate research ideas.")
    data = call_openai_json(
        prompt,
        system=(
            "You are a research idea advisor. Generate grounded, specific ideas and return valid JSON only."
        ),
        max_output_tokens=2600,
    )
    if data and isinstance(data.get("ideas"), list):
        ideas = [str(item).strip() for item in data["ideas"] if str(item).strip()]
        if len(ideas) >= 3:
            return ideas[:3], "llm-json"

    if os.environ.get("BALANCED_MODE") == "1":
        return _fallback_ideas(state), "fallback-balanced-json-failed"

    if has_openai_key():
        live_status("Idea JSON parsing failed; asking the LLM for text-format ideas.")
    text = call_openai_text(
        prompt.replace(
            'Return JSON only in this format:\n{"ideas": ["idea 1", "idea 2", "idea 3"]}',
            "If JSON is difficult, return a numbered list with 3 full ideas.",
        ),
        system="You are a research idea advisor. Output 3 grounded Chinese research ideas.",
        max_output_tokens=2600,
    )
    parsed = _extract_three_ideas(text or "")
    if len(parsed) >= 3:
        return parsed[:3], "llm-text"

    return _fallback_ideas(state), "fallback"


def generate_report(state: ResearchState, ideas: List[str], mermaid: str) -> tuple[str, str]:
    if os.environ.get("SKIP_REPORT_LLM") == "1":
        return _fallback_report(state, ideas, mermaid), "fallback-balanced"

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

Topic: {state.get("topic")}
Alignment score: {state.get("alignment_score")}
Taxonomy: {json.dumps(state.get("expert_taxonomy", {}), ensure_ascii=False)[:3000]}
Audit reports: {json.dumps(state.get("audit_reports", [])[:12], ensure_ascii=False)}
Detected gaps: {json.dumps(state.get("detected_gaps", [])[:12], ensure_ascii=False)}
Ideas: {json.dumps(ideas, ensure_ascii=False)}
"""
    if has_openai_key():
        live_status("Calling LLM to write the final report.")
    text = call_openai_text(
        prompt,
        system="You are a Chinese research review writer.",
        max_output_tokens=3200,
    )
    if text:
        cleaned = _sanitize_report_text(text)
        return cleaned + "\n\n## Mermaid 图谱\n\n```mermaid\n" + mermaid + "\n```\n", "llm"

    return _fallback_report(state, ideas, mermaid), "fallback"


def build_mermaid_graph(papers: Dict[str, PaperNode], edges: List[EvolutionEdge]) -> str:
    lines = ["graph LR"]
    if not papers:
        return "graph LR\n  empty[No papers]"

    node_ids = {paper_id: _mermaid_id(paper_id) for paper_id in papers}

    def label(paper: PaperNode) -> str:
        title = paper.title[:45].replace('"', "'") or paper.paper_id
        return f'{node_ids[paper.paper_id]}["{title}"]'

    for paper in list(papers.values())[:30]:
        lines.append(f"  {label(paper)}")
    for edge in edges[:50]:
        if edge.source not in node_ids or edge.target not in node_ids:
            continue
        rel = edge.relationship.replace('"', "'")
        lines.append(f'  {node_ids[edge.source]} -- "{rel}" --> {node_ids[edge.target]}')
    return "\n".join(lines)


def _extract_three_ideas(text: str) -> List[str]:
    if not text.strip():
        return []
    chunks = re.split(r"(?:^|\n)\s*(?:\d+[.\u3001)]|选题[一二三123][:：])\s*", text)
    ideas = [chunk.strip(" \n-") for chunk in chunks if len(chunk.strip()) > 30]
    if len(ideas) >= 3:
        return ideas[:3]
    lines = [line.strip("-•\n") for line in text.splitlines() if len(line.strip()) > 30]
    return lines[:3]


def _sanitize_report_text(text: str) -> str:
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


def _fallback_ideas(state: ResearchState) -> List[str]:
    topic = state.get("topic", "the topic")
    gaps = state.get("detected_gaps", [])
    gap_hint = gaps[0] if gaps else "the current graph still has coverage gaps and weak evidence links"
    return [
        (
            f"选题一：面向 {topic} 的可解释演进图补全方法。"
            f"研究动机：{gap_hint}。"
            "可行方法：联合引用关系、taxonomy 对齐和关键词重合度，自动发现缺失文献链。"
            "可行性：可以直接复用当前 Agent 的 graph 与 auditor 模块。"
            "预期贡献：提高研究综述和演进图的证据完整性。"
        ),
        (
            f"选题二：基于审计反馈的 {topic} 研究 gap 自动发现。"
            "研究动机：传统综述高度依赖人工阅读，难以及时发现逻辑断层。"
            "可行方法：把低置信节点、弱跨分类边和缺失概念转化为可追踪 gap。"
            "可行性：当前 detected_gaps 已经提供初始标签。"
            "预期贡献：形成一套可复现的选题推荐流程。"
        ),
        (
            f"选题三：融合 LLM 与规则校验的 {topic} 改进关系验证。"
            "研究动机：仅凭引用关系并不能证明后续论文真的改进了前作。"
            "可行方法：规则先筛候选边，再用 LLM 检查摘要里的改进声明与实验支撑。"
            "可行性：现有 OpenAI/DeepSeek 兼容层可直接作为增强模块。"
            "预期贡献：降低错误演进边对科研判断的干扰。"
        ),
    ]


def _fallback_report(state: ResearchState, ideas: List[str], mermaid: str) -> str:
    papers = state.get("paper_nodes", {})
    edges = state.get("evolution_graph", [])
    taxonomy = state.get("expert_taxonomy", {})
    reports = state.get("audit_reports", [])
    gaps = state.get("detected_gaps", [])

    lines = [
        f"# 科研演进审计报告：{state.get('topic', '')}",
        "",
        "## 1. 主题概览",
        f"本次 Agent 共收集论文 {len(papers)} 篇，构建演进边 {len(edges)} 条，对齐分数为 {state.get('alignment_score', 0)}。",
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
    lines.extend([f"{index}. {idea}" for index, idea in enumerate(ideas, 1)])
    lines.extend(["", "## Mermaid 图谱", "```mermaid", mermaid, "```"])
    return "\n".join(lines)


def _paper_brief(paper: PaperNode) -> Dict[str, str]:
    return {
        "id": paper.paper_id,
        "title": paper.title,
        "category": paper.taxonomy_category,
        "abstract": paper.abstract[:500],
    }


def _mermaid_id(value: str) -> str:
    safe = "".join(ch if ch.isalnum() else "_" for ch in value)
    return "n_" + safe
