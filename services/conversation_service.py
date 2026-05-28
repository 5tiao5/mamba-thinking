from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from product_agent.domain import Conversation
from product_agent.repositories import ConversationRepository, MessageRepository, ResearchTaskRepository, WorkspaceRepository


class ConversationService:
    """
    处理会话的创建、读取和后续多轮上下文挂载。

    当前阶段:
    - 提供 create / get 的最小能力

    后续重点:
    - 会话摘要
    - 历史会话列表
    - 多轮上下文压缩
    """

    def __init__(
        self,
        repository: ConversationRepository,
        *,
        message_repository: MessageRepository | None = None,
        task_repository: ResearchTaskRepository | None = None,
        workspace_repository: WorkspaceRepository | None = None,
    ) -> None:
        self.repository = repository
        self.message_repository = message_repository
        self.task_repository = task_repository
        self.workspace_repository = workspace_repository

    def create_conversation(self, *, topic: str, title: str | None = None) -> Conversation:
        """
        创建一个新的研究会话。

        调用者:
        - `ProductApiHandlers.create_conversation`

        参数:
        - `topic`: 研究主题，是整轮会话的默认主线
        - `title`: 可选标题；为空时回退为 `topic`

        返回:
        - `Conversation`

        待实现:
        1. 创建时同步生成一条 system welcome message
        2. 预留会话级配置，如默认工具集合和共享知识开关
        3. 增加 `conversation_summary` 字段，服务于多轮上下文压缩
        """
        conversation = Conversation(
            conversation_id=f"conv_{uuid4().hex[:12]}",
            topic=topic,
            title=title or topic,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        return self.repository.create(conversation)

    def get_conversation(self, conversation_id: str) -> Conversation | None:
        """
        根据 ID 获取会话。

        调用者:
        - `ProductApiHandlers.continue_conversation`
        - `MessageService`
        - 后续的 `ContextService`
        """
        return self.repository.get(conversation_id)

    def list_conversations(self, *, limit: int | None = None) -> list[Conversation]:
        """
        列出历史会话，默认按最近更新时间倒序返回。
        调用者:
        - `ProductApiHandlers.list_conversations`
        - 后续 `HistoryService`
        """
        items = self.repository.list_all()
        if limit is not None:
            return items[:limit]
        return items

    def delete_conversation(self, conversation_id: str) -> dict[str, int | bool]:
        """
        删除会话及其直属数据。

        当前存储层没有数据库级 cascade，因此在服务层按依赖顺序清理：
        workspace -> task -> message -> conversation。
        """
        if self.repository.get(conversation_id) is None:
            return {"deleted": False, "deleted_messages": 0, "deleted_tasks": 0, "deleted_workspaces": 0}

        deleted_workspaces = 0
        deleted_task_ids: list[str] = []
        if self.task_repository is not None:
            deleted_task_ids = self.task_repository.delete_by_conversation(conversation_id)
        if self.workspace_repository is not None:
            deleted_workspaces = self.workspace_repository.delete_by_task_ids(deleted_task_ids)

        deleted_messages = 0
        if self.message_repository is not None:
            deleted_messages = self.message_repository.delete_by_conversation(conversation_id)

        deleted = self.repository.delete(conversation_id)
        return {
            "deleted": deleted,
            "deleted_messages": deleted_messages,
            "deleted_tasks": len(deleted_task_ids),
            "deleted_workspaces": deleted_workspaces,
        }
