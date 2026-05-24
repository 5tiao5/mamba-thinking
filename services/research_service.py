from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from product_agent.domain import ResearchTask, ResearchWorkspace
from product_agent.repositories import ConversationRepository, ResearchTaskRepository, WorkspaceRepository
from product_agent.services.errors import ConversationNotFoundError, InvalidTaskModeError, TaskNotFoundError
from product_agent.services.workspace_mapper import workspace_from_agent_state


class ResearchService:
    """
    编排一轮研究任务。

    当前约束：
    - 任务创建、任务执行、任务状态流转统一由本服务负责
    - handler 不应直接访问 task repository
    """

    SUPPORTED_MODES = {"default", "fast", "balanced"}

    def __init__(
        self,
        *,
        conversation_repository: ConversationRepository,
        task_repository: ResearchTaskRepository,
        workspace_repository: WorkspaceRepository,
    ) -> None:
        self.conversation_repository = conversation_repository
        self.task_repository = task_repository
        self.workspace_repository = workspace_repository

    def create_task(
        self,
        *,
        conversation_id: str,
        topic: str,
        mode: str = "default",
        trigger_message_id: str | None = None,
    ) -> ResearchTask:
        """
        创建一条新的研究分析任务记录。

        约束：
        - `conversation_id` 必须对应有效会话
        - `mode` 必须属于受支持集合
        """
        conversation = self.conversation_repository.get(conversation_id)
        if conversation is None:
            raise ConversationNotFoundError(f"Conversation `{conversation_id}` does not exist.")
        if mode not in self.SUPPORTED_MODES:
            raise InvalidTaskModeError(
                f"Mode `{mode}` is invalid. Supported modes: {sorted(self.SUPPORTED_MODES)}."
            )

        task = ResearchTask(
            task_id=f"task_{uuid4().hex[:12]}",
            conversation_id=conversation_id,
            topic=topic,
            mode=mode,
            trigger_message_id=trigger_message_id,
            status="created",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        created_task = self.task_repository.create(task)
        conversation.latest_task_id = created_task.task_id
        conversation.updated_at = datetime.now(timezone.utc)
        self.conversation_repository.update(conversation)
        return created_task

    def create_follow_up_task(
        self,
        *,
        conversation_id: str,
        base_topic: str,
        latest_message_content: str,
        focus: str | None = None,
        mode: str = "default",
        trigger_message_id: str | None = None,
    ) -> ResearchTask:
        """
        基于一轮新追问创建 follow-up 研究任务。

        设计目标：
        - 让“继续对话”不只是写消息，而是真正落到任务链路上
        - 前端可以选择立即运行该任务，或先把任务展示给用户
        """
        follow_up_topic = self._derive_follow_up_topic(
            base_topic=base_topic,
            latest_message_content=latest_message_content,
            focus=focus,
        )
        return self.create_task(
            conversation_id=conversation_id,
            topic=follow_up_topic,
            mode=mode,
            trigger_message_id=trigger_message_id,
        )

    def get_task(self, task_id: str) -> ResearchTask:
        """按 ID 获取任务；找不到时抛出显式业务异常。"""
        task = self.task_repository.get(task_id)
        if task is None:
            raise TaskNotFoundError(f"Research task `{task_id}` does not exist.")
        return task

    def list_tasks(
        self,
        *,
        conversation_id: str | None = None,
        limit: int | None = None,
    ) -> list[ResearchTask]:
        """
        列出历史研究任务。
        约束:
        - 若指定 `conversation_id`，则只返回对应会话下的任务
        - 默认按最近更新时间倒序返回
        """
        items = self.task_repository.list_all()
        if conversation_id is not None:
            items = [item for item in items if item.conversation_id == conversation_id]
        if limit is not None:
            return items[:limit]
        return items

    def run_task(self, task: ResearchTask) -> ResearchWorkspace:
        """
        运行一条研究任务，并把 Agent 结果投影为产品工作台数据。

        当前副作用：
        - 调用 `product_agent.research_agent.pipeline.run_pipeline`
        - 调用 `workspace_repository.save` 保存工作台快照
        - 成功时更新 `task.status=completed`
        - 失败时更新 `task.status=failed`
        """
        task.status = "running"
        task.updated_at = datetime.now(timezone.utc)
        self.task_repository.update(task)

        try:
            from product_agent.research_agent.pipeline import run_pipeline

            # 知识上下文不再拼入 topic（会污染搜索 query），
            # 而是通过 state["knowledge_context"] 传给后续节点使用
            state = run_pipeline(task.topic, show_progress=False)
            workspace: ResearchWorkspace = workspace_from_agent_state(
                task_id=task.task_id,
                topic=task.topic,
                state=state,
            )
            saved_workspace = self.workspace_repository.save(workspace)
            task.status = "completed"
            task.updated_at = datetime.now(timezone.utc)
            self.task_repository.update(task)
            return saved_workspace
        except Exception:
            task.status = "failed"
            task.updated_at = datetime.now(timezone.utc)
            self.task_repository.update(task)
            raise

    @staticmethod
    def _derive_follow_up_topic(
        *,
        base_topic: str,
        latest_message_content: str,
        focus: str | None = None,
    ) -> str:
        focus_text = (focus or "").strip()
        if focus_text:
            return f"{base_topic} - focus on {focus_text}"

        snippet = " ".join(latest_message_content.strip().split())
        if not snippet:
            return base_topic
        return f"{base_topic} - follow up: {snippet[:80]}"
