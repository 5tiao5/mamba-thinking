from __future__ import annotations

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
        return WorkspaceSnapshotResponse(
            task_id=workspace.task_id,
            topic=workspace.topic,
            summary=workspace.summary,
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
