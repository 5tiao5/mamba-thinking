from __future__ import annotations

from dataclasses import replace

from product_agent.domain import Conversation, KnowledgeDocument, ResearchTask, ResearchWorkspace


class InMemoryConversationRepository:
    """开发期用的内存仓储，后续可替换为 SQLite / PostgreSQL 实现。"""

    def __init__(self) -> None:
        self._items: dict[str, Conversation] = {}

    def create(self, conversation: Conversation) -> Conversation:
        self._items[conversation.conversation_id] = replace(conversation)
        return replace(conversation)

    def get(self, conversation_id: str) -> Conversation | None:
        item = self._items.get(conversation_id)
        return replace(item) if item else None

    def update(self, conversation: Conversation) -> Conversation:
        self._items[conversation.conversation_id] = replace(conversation)
        return replace(conversation)


class InMemoryResearchTaskRepository:
    def __init__(self) -> None:
        self._items: dict[str, ResearchTask] = {}

    def create(self, task: ResearchTask) -> ResearchTask:
        self._items[task.task_id] = replace(task)
        return replace(task)

    def get(self, task_id: str) -> ResearchTask | None:
        item = self._items.get(task_id)
        return replace(item) if item else None

    def update(self, task: ResearchTask) -> ResearchTask:
        self._items[task.task_id] = replace(task)
        return replace(task)


class InMemoryWorkspaceRepository:
    def __init__(self) -> None:
        self._items: dict[str, ResearchWorkspace] = {}

    def save(self, workspace: ResearchWorkspace) -> ResearchWorkspace:
        self._items[workspace.task_id] = workspace
        return workspace

    def get_by_task(self, task_id: str) -> ResearchWorkspace | None:
        return self._items.get(task_id)


class InMemoryKnowledgeRepository:
    def __init__(self) -> None:
        self._items: dict[str, KnowledgeDocument] = {}

    def save(self, document: KnowledgeDocument) -> KnowledgeDocument:
        self._items[document.document_id] = document
        return document

    def list_all(self) -> list[KnowledgeDocument]:
        return list(self._items.values())

