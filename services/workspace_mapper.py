from __future__ import annotations

import json
import re
from typing import Any, Dict, List

from product_agent.domain import GapRecord, PaperRecord, ResearchIdeaRecord, ResearchWorkspace
from product_agent.services.text_cleaning import clean_internal_context_text
from product_agent.services.taxonomy_grounding_service import ground_taxonomy


def workspace_from_agent_state(*, task_id: str, topic: str, state: Dict[str, Any]) -> ResearchWorkspace:
    """
    将旧版 Agent state 转成产品工作台对象。

    这是前后端契约稳定化的关键步骤。

    TODO(iter3-workspace-mapper):
    1. 继续补全 taxonomy summary / recommended papers / key comparisons
    2. 为前端增加 section-level payload
    3. 增加引用来源与 evidence mapping
    """

    evidence_pool = state.get("evidence_pool") or state.get("paper_nodes", {})
    analysis_nodes = state.get("paper_nodes", {})
    papers = [_map_paper(paper) for paper in evidence_pool.values()]
    analysis_papers = [_map_paper(paper) for paper in analysis_nodes.values()]
    gaps = [_map_gap(task_id, gap) for gap in state.get("detected_gaps", [])]
    gap_ids = {g.gap_id for g in gaps}

    # map graph edges with gap-awareness
    graph_edges = [_map_graph_edge(edge, gap_ids) for edge in state.get("evolution_graph", [])]

    # taxonomy normalization uses papers and gaps to build tree/coverage
    taxonomy = _normalize_taxonomy(
        state.get("expert_taxonomy", {}),
        analysis_papers,
        gaps,
    )

    # ideas mapping can infer related papers / derived gaps
    ideas = [
        _map_idea(task_id, idea, analysis_papers, gaps)
        for idea in state.get("generated_ideas", [])
    ]

    trace = _build_trace(state)
    evidence_status = _build_evidence_status(papers=papers, taxonomy=taxonomy)

    summary_payload = dict(state.get("final_report_summary", {}) or {})
    summary_payload["analysis_paper_ids"] = list(state.get("paper_nodes", {}).keys())
    summary_payload["evidence_pool_count"] = len(evidence_pool)
    summary_payload["analysis_paper_count"] = len(state.get("paper_nodes", {}))
    evidence_snapshot = dict(state.get("evidence_snapshot", {}) or {})
    if evidence_snapshot:
        summary_payload["evidence_snapshot"] = evidence_snapshot
        summary_payload["evidence_snapshot_id"] = evidence_snapshot.get("snapshot_id", "")

    return ResearchWorkspace(
        task_id=task_id,
        topic=clean_internal_context_text(topic, max_length=180) or topic,
        summary=_build_workspace_summary(topic=topic, state=state),
        summary_payload=summary_payload,
        papers=papers,
        taxonomy=taxonomy,
        graph_edges=graph_edges,
        gaps=gaps,
        ideas=ideas,
        alignment_score=float(state.get("alignment_score", 0.0) or 0.0),
        evidence_status=evidence_status,
        trace=trace,
    )


def _build_workspace_summary(*, topic: str, state: Dict[str, Any]) -> str:
    topic = clean_internal_context_text(topic, max_length=180) or topic
    summary_payload = state.get("final_report_summary", {}) or {}
    structured_summary = _summary_from_payload(topic=topic, summary_payload=summary_payload)
    if structured_summary:
        return structured_summary

    report_text = str(state.get("final_report", "") or "")
    cleaned_report = _strip_report_noise(report_text)
    if not cleaned_report:
        return ""

    paragraphs = [segment.strip() for segment in re.split(r"\n\s*\n", cleaned_report) if segment.strip()]
    if not paragraphs:
        return cleaned_report[:400].strip()

    selected: List[str] = []
    for paragraph in paragraphs:
        if "taxonomy" in paragraph.lower() and "{" in paragraph:
            continue
        selected.append(paragraph)
        if len(" ".join(selected)) >= 360:
            break

    text = "\n\n".join(selected).strip() or cleaned_report.strip()
    return clean_internal_context_text(text, max_length=400)


def _summary_from_payload(*, topic: str, summary_payload: Dict[str, Any]) -> str:
    if not isinstance(summary_payload, dict) or not summary_payload:
        return ""

    headline = str(summary_payload.get("headline", "") or "").strip()
    score = summary_payload.get("score")
    counts = summary_payload.get("counts", {}) or {}
    recommendation = str(summary_payload.get("recommendation", "") or "").strip()
    top_gaps = summary_payload.get("top_gaps", []) or []
    is_expansion_followup = _is_expansion_followup_summary(topic=topic, summary_payload=summary_payload)

    lines: List[str] = []
    if headline:
        lines.append(headline)
    else:
        lines.append(f"科研演进审计报告：{topic}")

    papers = counts.get("papers")
    gaps = counts.get("gaps")
    ideas = counts.get("ideas")
    metrics: List[str] = []
    if papers is not None:
        metrics.append(f"论文 {papers} 篇")
    if gaps is not None:
        metrics.append(f"研究空白 {gaps} 条")
    if ideas is not None:
        metrics.append(f"研究建议 {ideas} 条")
    if isinstance(score, (int, float)):
        metrics.append(f"对齐分数 {float(score):.3f}")
    if metrics:
        lines.append("本轮分析共得到 " + "，".join(metrics) + "。")

    if is_expansion_followup:
        focus = _expansion_focus_from_topic(topic)
        if focus:
            lines.append(f"当前展开方向：{focus}。")
    elif top_gaps:
        gap_summaries = []
        for gap in top_gaps[:2]:
            if isinstance(gap, dict):
                summary = str(gap.get("summary", "") or "").strip()
            else:
                summary = str(gap).strip()
            if summary:
                gap_summaries.append(summary)
        if gap_summaries:
            lines.append("优先关注：" + "；".join(gap_summaries) + "。")

    if recommendation:
        lines.append("建议：" + recommendation)

    return clean_internal_context_text("\n".join(line for line in lines if line).strip(), max_length=600)


def _is_expansion_followup_summary(*, topic: str, summary_payload: Dict[str, Any]) -> bool:
    if "继续展开" in str(topic):
        return True
    grounding = summary_payload.get("context_grounding", {}) if isinstance(summary_payload, dict) else {}
    retrieval_plan = str(grounding.get("retrieval_plan", "") or "") if isinstance(grounding, dict) else ""
    return "goal=extend_context" in retrieval_plan


def _expansion_focus_from_topic(topic: str) -> str:
    text = clean_internal_context_text(str(topic or ""), max_length=180)
    for marker in ("继续展开：", "继续展开:", "展开：", "展开:"):
        if marker in text:
            return text.split(marker, 1)[1].strip(" -")
    return ""


def _strip_report_noise(report_text: str) -> str:
    if not report_text.strip():
        return ""

    text = report_text
    text = re.sub(r"```json[\s\S]*?```", "", text, flags=re.IGNORECASE)
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(
        r"(?:^|\n)\s*\d+\.\s*专家\s*Taxonomy[\s\S]*?(?=(?:\n\s*\d+\.\s)|\Z)",
        "\n",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\n{3,}", "\n\n", text)
    return clean_internal_context_text(text.strip())


def _map_paper(paper: Any) -> PaperRecord:
    if hasattr(paper, "model_dump"):
        payload = paper.model_dump()
    elif isinstance(paper, dict):
        payload = paper
    else:
        payload = paper.__dict__
    return PaperRecord(
        paper_id=str(payload.get("paper_id", "")),
        title=str(payload.get("title", "")),
        abstract=str(payload.get("abstract", "")),
        authors=list(payload.get("authors", [])),
        keywords=[str(item).strip() for item in payload.get("keywords", []) if str(item).strip()],
        publish_date=str(payload.get("publish_date", "")),
        source=str(payload.get("source", "")),
        taxonomy_category=str(payload.get("taxonomy_category", "")),
        citation_count=int(payload.get("citation_count", 0) or 0),
        url=str(payload.get("url", "")),
        is_new_this_round=bool(payload.get("is_new_this_round", False)),
        relevance_score=float(payload.get("relevance_score", 0.0) or 0.0),
        relevance_tier=str(payload.get("relevance_tier", "candidate") or "candidate"),
        relevance_reasons=[
            str(item).strip()
            for item in payload.get("relevance_reasons", [])
            if str(item).strip()
        ],
    )


def _map_gap(task_id: str, raw_gap: str) -> GapRecord:
    if isinstance(raw_gap, dict):
        gap_id = str(raw_gap.get("id") or raw_gap.get("gap_id") or f"gap_{abs(hash((task_id, json_safe(raw_gap)))) % 10_000_000}")
        summary = str(raw_gap.get("summary", raw_gap.get("description", raw_gap))).strip()
        evidence = [str(item).strip() for item in raw_gap.get("evidence", []) if str(item).strip()]
        severity = str(raw_gap.get("severity", "")).strip().lower() or (
            "high" if any(token in summary.lower() for token in ["missing", "unsupported", "dangling"]) else "medium"
        )
    else:
        gap_id = f"gap_{abs(hash((task_id, str(raw_gap)))) % 10_000_000}"
        summary = str(raw_gap).strip()
        evidence = []
        severity = "high" if any(token in summary.lower() for token in ["missing", "unsupported", "dangling"]) else "medium"

    return GapRecord(
        gap_id=gap_id,
        task_id=task_id,
        summary=summary,
        severity=severity,
        evidence=evidence,
    )


def _map_graph_edge(raw_edge: Any, gap_ids: set) -> Dict[str, Any]:
    if hasattr(raw_edge, "model_dump"):
        payload = raw_edge.model_dump()
    elif isinstance(raw_edge, dict):
        payload = raw_edge
    elif hasattr(raw_edge, "__dict__"):
        payload = {k: v for k, v in vars(raw_edge).items() if not k.startswith("_")}
    else:
        payload = {"raw": str(raw_edge)}

    source = str(payload.get("source", ""))
    target = str(payload.get("target", ""))
    relationship = str(payload.get("relationship", ""))
    reasoning = str(payload.get("reasoning", ""))
    provenance = str(payload.get("provenance", ""))
    evidence_level = str(payload.get("evidence_level", "candidate"))
    evidence = str(payload.get("evidence", ""))
    evidence_snippets = [
        str(item)
        for item in payload.get("evidence_snippets", [])
        if str(item).strip()
    ]
    edge_id = str(payload.get("id") or payload.get("edge_id") or f"edge_{source}_{target}")
    metadata = {
        key: value
        for key, value in payload.items()
        if key not in {"id", "edge_id", "source", "target", "relationship", "reasoning", "score", "type"}
    }

    # quality labels
    confidence = float(payload.get("confidence", payload.get("score") or 0.0) or 0.0)
    is_weak = confidence < 0.5
    # determine whether this edge relates to known gaps
    is_gap_related = False
    # explicit related gap fields from payload
    related_field = payload.get("related_gaps") or payload.get("related_gap_ids") or payload.get("gap_ids") or payload.get("gap_id")
    related_set = set()
    if related_field:
        if isinstance(related_field, (list, tuple, set)):
            related_set = set(str(x) for x in related_field)
        else:
            related_set = {str(related_field)}
    if related_set & set(gap_ids):
        is_gap_related = True
    # scan metadata values for gap ids
    if not is_gap_related:
        for v in metadata.values():
            if isinstance(v, str):
                for gid in gap_ids:
                    if gid and gid in v:
                        is_gap_related = True
                        break
            elif isinstance(v, (list, tuple, set)):
                if any(str(x) in gap_ids for x in v):
                    is_gap_related = True
                    break
            if is_gap_related:
                break
    # fallback: relation text mentions 'gap' or source/target look like gap ids
    if not is_gap_related:
        if relationship and "gap" in relationship.lower():
            is_gap_related = True
        elif str(source).startswith("gap_") or str(target).startswith("gap_"):
            is_gap_related = True

    edge_type = str(payload.get("type", relationship or "semantic")).strip() or "semantic"

    return {
        "edge_id": edge_id,
        "source": source,
        "target": target,
        "relationship": relationship,
        "reasoning": reasoning,
        "type": edge_type,
        "confidence": confidence,
        "provenance": provenance,
        "evidence_level": evidence_level,
        "evidence": evidence,
        "evidence_snippets": evidence_snippets,
        "is_weak": is_weak,
        "is_gap_related": is_gap_related,
        "metadata": metadata,
    }



def _map_idea(task_id: str, raw_idea: Any, papers: List[PaperRecord], gaps: List[GapRecord]) -> ResearchIdeaRecord:
    if isinstance(raw_idea, ResearchIdeaRecord):
        payload = {
            "idea_id": raw_idea.idea_id,
            "title": raw_idea.title,
            "motivation": raw_idea.motivation,
            "approach": raw_idea.approach,
            "feasibility": raw_idea.feasibility,
            "contribution": raw_idea.contribution,
            "related_papers": list(raw_idea.related_papers),
            "derived_from_gaps": list(raw_idea.derived_from_gaps),
            "confidence": raw_idea.confidence,
            "tags": list(raw_idea.tags),
            "raw_text": raw_idea.raw_text,
        }
    elif isinstance(raw_idea, dict):
        payload = raw_idea
    elif hasattr(raw_idea, "to_dict"):
        payload = raw_idea.to_dict()
    else:
        payload = {"title": _extract_title(str(raw_idea)), "raw_text": str(raw_idea)}

    title = str(payload.get("title", "")).strip() or _extract_title(str(payload.get("raw_text", "")))
    motivation = str(payload.get("motivation", "")).strip()
    approach = str(payload.get("approach", "")).strip()
    feasibility = str(payload.get("feasibility", "")).strip()
    contribution = str(payload.get("contribution", "")).strip()
    related_papers = [str(item).strip() for item in payload.get("related_papers", []) if str(item).strip()]
    derived_from_gaps = [str(item).strip() for item in payload.get("derived_from_gaps", []) if str(item).strip()]
    confidence = float(payload.get("confidence", 0.0) or 0.0)
    tags = [str(item).strip() for item in payload.get("tags", []) if str(item).strip()]
    raw_text = str(payload.get("raw_text", "")).strip() or title
    idea_id = str(payload.get("idea_id") or payload.get("id") or f"idea_{abs(hash((task_id, raw_text or title))) % 10_000_000}")
    # Auto-link related papers if missing
    if not related_papers and (raw_text or title):
        related_papers = _infer_related_papers(raw_text or title, papers)

    # Auto-match derived gaps if missing
    if not derived_from_gaps and raw_text:
        derived_from_gaps = _match_gap_text(raw_text, gaps)

    return ResearchIdeaRecord(
        idea_id=idea_id,
        task_id=task_id,
        title=title,
        motivation=motivation,
        approach=approach,
        feasibility=feasibility,
        contribution=contribution,
        related_papers=related_papers,
        derived_from_gaps=derived_from_gaps,
        confidence=confidence,
        tags=tags,
        raw_text=raw_text,
    )


def _extract_title(raw_idea: str) -> str:
    first_line = raw_idea.strip().splitlines()[0] if raw_idea.strip() else "Untitled Idea"
    first_line = re.sub(r"^\s*\d+[\.\、)]\s*", "", first_line).strip()
    return first_line[:120] or "Untitled Idea"


def _normalize_taxonomy(raw_taxonomy: Any, papers: List[PaperRecord], gaps: List[GapRecord] = None) -> Dict[str, Any]:
    return ground_taxonomy(raw_taxonomy, papers, gaps or [])


def _slug(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return normalized or "branch"


def _build_trace(state: Dict[str, Any]) -> Dict[str, Any]:
    thought = list(state.get("thought_trace", []))
    actions = list(state.get("action_history", []))
    tools = list(state.get("tool_events", []))
    timeline = []
    step = 1
    def add_events(items, type_name):
        nonlocal step
        for it in items:
            if isinstance(it, dict):
                summary = str(it.get("summary") or it.get("title") or it.get("name") or "").strip()
                ts = it.get("timestamp") or it.get("ts")
            else:
                summary = str(it).splitlines()[0][:200]
                ts = None
            timeline.append({"step": step, "type": type_name, "summary": summary, "timestamp": ts, "raw": it})
            step += 1

    add_events(actions, "action")
    add_events(thought, "thought")
    add_events(tools, "tool")

    return {
        "thought_trace": thought,
        "action_history": actions,
        "context_inputs": list(state.get("context_inputs", [])),
        "logs": list(state.get("logs", [])),
        "decisions": list(state.get("decisions", [])),
        "tool_events": tools,
        "timeline": timeline,
        "run_status": str(state.get("run_status", "running") or "running"),
        "termination_reason": str(state.get("termination_reason", "") or ""),
        "degraded_reason": str(state.get("degraded_reason", "") or ""),
        "repair_count": int(state.get("retry_count", 0) or 0),
        "max_repair_rounds": int(state.get("max_repair_rounds", 0) or 0),
        "repair_stop_reason": str(state.get("repair_stop_reason", "") or ""),
        "repair_history": list(state.get("repair_history", [])),
    }


def _build_evidence_status(
    *,
    papers: List[PaperRecord],
    taxonomy: Dict[str, Any],
) -> Dict[str, Any]:
    """Generate WorkspaceEvidenceStatus from papers and grounded taxonomy."""
    total_papers = len(papers)
    real_paper_count = sum(
        1 for p in papers if getattr(p, "source", "") not in ("seed", "fallback")
    )
    direct_paper_count = sum(
        1 for p in papers if getattr(p, "relevance_tier", "") == "direct"
    )
    adjacent_paper_count = sum(
        1 for p in papers if getattr(p, "relevance_tier", "") == "adjacent"
    )
    fallback_paper_count = total_papers - real_paper_count
    fallback_ratio = round(fallback_paper_count / total_papers, 3) if total_papers > 0 else 0.0

    branches = taxonomy.get("branches", []) if isinstance(taxonomy, dict) else []
    total_branches = len(branches)
    if total_branches == 0:
        return {
            "insufficient": True,
            "total_papers": total_papers,
            "real_paper_count": real_paper_count,
            "direct_paper_count": direct_paper_count,
            "adjacent_paper_count": adjacent_paper_count,
            "fallback_paper_count": fallback_paper_count,
            "fallback_ratio": fallback_ratio,
            "covered_branch_count": 0,
            "candidate_branches": [],
            "message": "No taxonomy branches were generated. Evidence is insufficient for structured analysis.",
        }

    candidate_branches = [
        b["name"] for b in branches
        if b.get("evidence_tier") == "candidate"
    ]
    covered_branch_count = total_branches - len(candidate_branches)

    candidate_ratio = len(candidate_branches) / total_branches if total_branches > 0 else 0
    insufficient = candidate_ratio > 0.5 or (total_papers <= 3 and fallback_ratio > 0.5)

    if insufficient:
        if candidate_branches:
            message = (
                f"当前{total_papers}篇论文中{fallback_paper_count}篇为保底论文，"
                f"{total_branches}个研究分支中{len(candidate_branches)}个尚无文献支撑。"
                f"当前更适合把 {' / '.join(candidate_branches[:3])} 当作候选研究分支，"
                f"而不是直接展示完整 taxonomy。后续建议继续补充真实论文。"
            )
        else:
            message = (
                f"当前仅{total_papers}篇论文，证据总量不足以支撑可靠的研究分类。"
                f"建议补充检索或缩小研究范围后重试。"
            )
    else:
        weak_count = sum(1 for b in branches if b.get("evidence_tier") == "weak")
        if weak_count > 0:
            message = (
                f"{total_branches}个分支中{covered_branch_count}个已有文献支撑，"
                f"{weak_count}个证据偏弱。整体可视为初步研究地图。"
            )
        else:
            message = (
                f"所有{total_branches}个研究分支均有文献支撑，"
                f"taxonomy 可作为可靠的研究导航使用。"
            )

    return {
        "insufficient": insufficient,
        "total_papers": total_papers,
        "real_paper_count": real_paper_count,
        "direct_paper_count": direct_paper_count,
        "adjacent_paper_count": adjacent_paper_count,
        "fallback_paper_count": fallback_paper_count,
        "fallback_ratio": fallback_ratio,
        "covered_branch_count": covered_branch_count,
        "candidate_branches": candidate_branches,
        "message": message,
    }


def json_safe(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except Exception:
        return str(value)


def _infer_related_papers(text: str, papers: List[PaperRecord], top_n: int = 3) -> List[str]:
    text_lower = (text or "").lower()
    tokens = [t for t in re.split(r"[^a-z0-9]+", text_lower) if len(t) > 3]
    if not tokens:
        return []
    scores = []
    for p in papers:
        text_fields = f"{p.title or ''} {p.abstract or ''}".lower()
        score = sum(1 for t in tokens if t in text_fields)
        if score > 0:
            scores.append((score, p.paper_id or p.title))
    scores.sort(key=lambda x: -x[0])
    return [item[1] for item in scores[:top_n]]


def _match_gap_text(text: str, gaps: List[GapRecord]) -> List[str]:
    text_lower = (text or "").lower()
    tokens = [t for t in re.split(r"[^a-z0-9]+", text_lower) if len(t) > 3]
    matches = []
    for g in gaps:
        summary = (g.summary or "").lower()
        score = sum(1 for t in tokens if t in summary)
        if score > 0:
            matches.append((score, g.gap_id))
    matches.sort(key=lambda x: -x[0])
    return [m[1] for m in matches]
