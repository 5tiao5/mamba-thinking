from __future__ import annotations

import re

from product_agent.repositories import WorkspaceRepository
from product_agent.schemas import (
    WorkspaceGapView,
    WorkspaceGraphEdgeView,
    WorkspaceIdeaView,
    WorkspacePaperView,
    WorkspaceSnapshotResponse,
    WorkspaceTraceView,
)


class WorkspaceService:
    """
    负责工作台数据的读取、聚合与导出前整理。

    当前目标：
    - 对外优先返回稳定的 `WorkspaceSnapshotResponse`
    - 避免 handler 或前端继续理解 domain object 细节
    """

    def __init__(self, repository: WorkspaceRepository) -> None:
        self.repository = repository

    def get_workspace(self, task_id: str):
        """根据 `task_id` 读取工作台 domain 对象。"""
        return self.repository.get_by_task(task_id)

    def get_workspace_snapshot(self, task_id: str) -> WorkspaceSnapshotResponse | None:
        """根据 `task_id` 读取并投影为前端稳定消费的工作台响应。"""
        workspace = self.repository.get_by_task(task_id)
        if workspace is None:
            return None

        trace = workspace.trace or {}
        summary = _normalize_workspace_summary(
            topic=workspace.topic,
            summary=workspace.summary,
            summary_payload=workspace.summary_payload or {},
        )
        return WorkspaceSnapshotResponse(
            task_id=workspace.task_id,
            topic=workspace.topic,
            summary=summary,
            papers=[
                WorkspacePaperView(
                    paper_id=paper.paper_id,
                    title=paper.title,
                    publish_date=paper.publish_date,
                    source=paper.source,
                    taxonomy_category=paper.taxonomy_category,
                    citation_count=paper.citation_count,
                    url=paper.url,
                )
                for paper in workspace.papers
            ],
            taxonomy=workspace.taxonomy,
            graph_edges=[
                WorkspaceGraphEdgeView(
                    source=str(edge.get("source", "")),
                    target=str(edge.get("target", "")),
                    relationship=str(edge.get("relationship", "")),
                    reasoning=str(edge.get("reasoning", "")),
                )
                for edge in workspace.graph_edges
            ],
            gaps=[
                WorkspaceGapView(
                    summary=gap.summary,
                    severity=gap.severity,
                    evidence=list(gap.evidence),
                )
                for gap in workspace.gaps
            ],
            ideas=[
                WorkspaceIdeaView(
                    title=idea.title,
                    motivation=idea.motivation,
                    approach=idea.approach,
                    feasibility=idea.feasibility,
                    contribution=idea.contribution,
                    raw_text="",
                )
                for idea in workspace.ideas
            ],
            alignment_score=workspace.alignment_score,
            trace=WorkspaceTraceView(
                thought_trace=list(trace.get("thought_trace", [])),
                action_history=list(trace.get("action_history", [])),
                context_inputs=list(trace.get("context_inputs", [])),
            ),
        )


def _normalize_workspace_summary(*, topic: str, summary: str, summary_payload: dict) -> str:
    summary_payload = summary_payload or {}
    if _looks_like_legacy_report_excerpt(summary):
        payload_summary = _summary_from_payload(topic=topic, summary_payload=summary_payload)
        if payload_summary:
            return payload_summary
    return _strip_report_noise(summary)


def _looks_like_legacy_report_excerpt(summary: str) -> bool:
    text = (summary or "").lower()
    return "```json" in text or "domain_name" in text or "专家 taxonomy" in text


def _summary_from_payload(*, topic: str, summary_payload: dict) -> str:
    if not isinstance(summary_payload, dict) or not summary_payload:
        return ""

    headline = str(summary_payload.get("headline", "") or "").strip()
    score = summary_payload.get("score")
    counts = summary_payload.get("counts", {}) or {}
    recommendation = str(summary_payload.get("recommendation", "") or "").strip()
    top_gaps = summary_payload.get("top_gaps", []) or []

    lines: list[str] = [headline or f"科研演进审计报告：{topic}"]

    metrics: list[str] = []
    papers = counts.get("papers")
    gaps = counts.get("gaps")
    ideas = counts.get("ideas")
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

    gap_summaries: list[str] = []
    for gap in top_gaps[:2]:
        if isinstance(gap, dict):
            gap_summary = str(gap.get("summary", "") or "").strip()
        else:
            gap_summary = str(gap).strip()
        if gap_summary:
            gap_summaries.append(gap_summary)
    if gap_summaries:
        lines.append("优先关注：" + "；".join(gap_summaries) + "。")

    if recommendation:
        lines.append("建议：" + recommendation)

    return "\n".join(line for line in lines if line).strip()


def _strip_report_noise(summary: str) -> str:
    text = str(summary or "")
    text = re.sub(r"```json[\s\S]*?```", "", text, flags=re.IGNORECASE)
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(
        r"(?:^|\n)\s*\d+\.\s*专家\s*Taxonomy[\s\S]*?(?=(?:\n\s*\d+\.\s)|\Z)",
        "\n",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
