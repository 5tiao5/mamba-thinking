from __future__ import annotations

from product_agent.repositories import WorkspaceRepository


class WorkspaceService:
    """负责工作台数据的读取、聚合与导出前整理。"""

    def __init__(self, repository: WorkspaceRepository) -> None:
        self.repository = repository

    def get_workspace(self, task_id: str):
        return self.repository.get_by_task(task_id)

