from __future__ import annotations

from copy import deepcopy

from product_agent.domain import Conversation, KnowledgeDocument, MessageRecord, ResearchTask, ResearchWorkspace


class InMemoryConversationRepository:
    """开发期用的内存存储，后续可替换为 SQLite / PostgreSQL 实现。"""

    def __init__(self) -> None:
        self._items: dict[str, Conversation] = {}

    def create(self, conversation: Conversation) -> Conversation:
        stored = deepcopy(conversation)
        self._items[conversation.conversation_id] = stored
        return deepcopy(stored)

    def get(self, conversation_id: str) -> Conversation | None:
        item = self._items.get(conversation_id)
        return deepcopy(item) if item else None

    def update(self, conversation: Conversation) -> Conversation:
        stored = deepcopy(conversation)
        self._items[conversation.conversation_id] = stored
        return deepcopy(stored)


class InMemoryMessageRepository:
    """开发期消息链路的内存实现。"""

    def __init__(self) -> None:
        self._items: dict[str, MessageRecord] = {}
        self._conversation_index: dict[str, list[str]] = {}

    def create(self, message: MessageRecord) -> MessageRecord:
        stored = deepcopy(message)
        self._items[message.message_id] = stored
        self._conversation_index.setdefault(message.conversation_id, []).append(message.message_id)
        return deepcopy(stored)

    def list_by_conversation(self, conversation_id: str) -> list[MessageRecord]:
        message_ids = self._conversation_index.get(conversation_id, [])
        items = [self._items[message_id] for message_id in message_ids if message_id in self._items]
        return [deepcopy(item) for item in items]


class InMemoryResearchTaskRepository:
    def __init__(self) -> None:
        self._items: dict[str, ResearchTask] = {}

    def create(self, task: ResearchTask) -> ResearchTask:
        stored = deepcopy(task)
        self._items[task.task_id] = stored
        return deepcopy(stored)

    def get(self, task_id: str) -> ResearchTask | None:
        item = self._items.get(task_id)
        return deepcopy(item) if item else None

    def update(self, task: ResearchTask) -> ResearchTask:
        stored = deepcopy(task)
        self._items[task.task_id] = stored
        return deepcopy(stored)


class InMemoryWorkspaceRepository:
    def __init__(self) -> None:
        self._items: dict[str, ResearchWorkspace] = {}

    def save(self, workspace: ResearchWorkspace) -> ResearchWorkspace:
        stored = deepcopy(workspace)
        self._items[workspace.task_id] = stored
        return deepcopy(stored)

    def get_by_task(self, task_id: str) -> ResearchWorkspace | None:
        item = self._items.get(task_id)
        return deepcopy(item) if item else None


class InMemoryKnowledgeRepository:
    def __init__(self) -> None:
        self._items: dict[str, KnowledgeDocument] = {}

    def save(self, document: KnowledgeDocument) -> KnowledgeDocument:
        stored = deepcopy(document)
        self._items[document.document_id] = stored
        return deepcopy(stored)

    def list_all(self) -> list[KnowledgeDocument]:
        return [deepcopy(item) for item in self._items.values()]
