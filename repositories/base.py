from __future__ import annotations

from typing import Protocol

from product_agent.domain import (
    Conversation,
    KnowledgeDocument,
    MessageRecord,
    ResearchTask,
    ResearchWorkspace,
)


class ConversationRepository(Protocol):
    """会话存储接口。后续可分别实现 InMemory / SQLite / PostgreSQL 版本。"""

    def create(self, conversation: Conversation) -> Conversation:
        """
        写入新会话并返回持久化结果。

        合同:
        - 必须返回已成功持久化的 `Conversation`
        - 若写入失败，应抛出实现层异常，而不是返回 `None`
        """
        ...

    def get(self, conversation_id: str) -> Conversation | None:
        """按 ID 读取会话；不存在时返回 `None`。"""
        ...

    def update(self, conversation: Conversation) -> Conversation:
        """更新会话状态并返回更新后的对象。"""
        ...

    def list_all(self) -> list[Conversation]:
        """列出所有会话，默认按最近更新时间倒序返回。"""
        ...

    def delete(self, conversation_id: str) -> bool:
        """删除会话，返回是否成功删除。"""
        ...


class MessageRepository(Protocol):
    """消息存储接口。"""

    def create(self, message: MessageRecord) -> MessageRecord:
        """写入一条消息并返回持久化结果。"""
        ...

    def list_by_conversation(self, conversation_id: str) -> list[MessageRecord]:
        """按会话列出消息，默认按创建时间升序返回。"""
        ...

    def delete_by_conversation(self, conversation_id: str) -> int:
        """删除某个会话下的所有消息，返回删除数量。"""
        ...


class ResearchTaskRepository(Protocol):
    """研究任务存储接口。"""

    def create(self, task: ResearchTask) -> ResearchTask:
        """写入新任务并返回持久化结果。"""
        ...

    def get(self, task_id: str) -> ResearchTask | None:
        """按 ID 查询任务。"""
        ...

    def update(self, task: ResearchTask) -> ResearchTask:
        """更新任务状态。"""
        ...

    def list_all(self) -> list[ResearchTask]:
        """列出所有研究任务，默认按最近更新时间倒序返回。"""
        ...

    def delete_by_conversation(self, conversation_id: str) -> list[str]:
        """删除某个会话下的所有研究任务，返回被删除的任务 ID。"""
        ...


class WorkspaceRepository(Protocol):
    """工作台结果存储接口。"""

    def save(self, workspace: ResearchWorkspace) -> ResearchWorkspace:
        """保存一次任务的工作台快照。"""
        ...

    def get_by_task(self, task_id: str) -> ResearchWorkspace | None:
        """按 task_id 获取工作台快照。"""
        ...

    def delete_by_task_ids(self, task_ids: list[str]) -> int:
        """删除指定任务对应的工作台快照，返回删除数量。"""
        ...


class KnowledgeRepository(Protocol):
    """知识沉淀存储接口。"""

    def save(self, document: KnowledgeDocument) -> KnowledgeDocument:
        """保存知识文档。"""
        ...

    def list_all(self) -> list[KnowledgeDocument]:
        """列出所有知识文档。"""
        ...

    def get(self, document_id: str) -> KnowledgeDocument | None:
        """按 ID 获取知识文档。"""
        ...

    def list_by_tags(self, tags: list[str], limit: int) -> list[KnowledgeDocument]:
        """根据标签检索文档（至少包含其中一个 tag），按创建时间倒序返回最多 limit 条。"""
        ...

    def delete(self, document_id: str) -> bool:
        """删除知识文档，返回是否成功删除。"""
        ...
