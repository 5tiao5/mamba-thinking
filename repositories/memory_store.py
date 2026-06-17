from __future__ import annotations

from copy import deepcopy

from product_agent.domain import (
    Conversation,
    ConversationResearchPaper,
    ConversationWorkingMemory,
    KnowledgeDocument,
    MessageRecord,
    ResearchTask,
    ResearchTaskEvent,
    ResearchWorkspace,
)


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

    def list_all(self) -> list[Conversation]:
        items = sorted(self._items.values(), key=lambda item: item.updated_at, reverse=True)
        return [deepcopy(item) for item in items]

    def delete(self, conversation_id: str) -> bool:
        if conversation_id not in self._items:
            return False
        del self._items[conversation_id]
        return True


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

    def delete_by_conversation(self, conversation_id: str) -> int:
        message_ids = self._conversation_index.pop(conversation_id, [])
        deleted = 0
        for message_id in message_ids:
            if message_id in self._items:
                del self._items[message_id]
                deleted += 1
        return deleted


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

    def list_all(self) -> list[ResearchTask]:
        items = sorted(self._items.values(), key=lambda item: item.updated_at, reverse=True)
        return [deepcopy(item) for item in items]

    def delete_by_conversation(self, conversation_id: str) -> list[str]:
        task_ids = [task_id for task_id, task in self._items.items() if task.conversation_id == conversation_id]
        for task_id in task_ids:
            del self._items[task_id]
        return task_ids


class InMemoryResearchTaskEventRepository:
    def __init__(self) -> None:
        self._items: dict[str, ResearchTaskEvent] = {}
        self._task_index: dict[str, list[str]] = {}

    def append(self, event: ResearchTaskEvent) -> ResearchTaskEvent:
        stored = deepcopy(event)
        self._items[event.event_id] = stored
        self._task_index.setdefault(event.task_id, []).append(event.event_id)
        return deepcopy(stored)

    def list_by_task(self, task_id: str) -> list[ResearchTaskEvent]:
        event_ids = self._task_index.get(task_id, [])
        items = [self._items[event_id] for event_id in event_ids if event_id in self._items]
        items.sort(key=lambda item: (item.sequence, item.created_at, item.event_id))
        return [deepcopy(item) for item in items]

    def delete_by_task_ids(self, task_ids: list[str]) -> int:
        deleted = 0
        for task_id in task_ids:
            event_ids = self._task_index.pop(task_id, [])
            for event_id in event_ids:
                if event_id in self._items:
                    del self._items[event_id]
                    deleted += 1
        return deleted


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

    def delete_by_task_ids(self, task_ids: list[str]) -> int:
        deleted = 0
        for task_id in task_ids:
            if task_id in self._items:
                del self._items[task_id]
                deleted += 1
        return deleted


class InMemoryKnowledgeRepository:
    def __init__(self) -> None:
        self._items: dict[str, KnowledgeDocument] = {}

    def save(self, document: KnowledgeDocument) -> KnowledgeDocument:
        stored = deepcopy(document)
        self._items[document.document_id] = stored
        return deepcopy(stored)

    def get(self, document_id: str) -> KnowledgeDocument | None:
        item = self._items.get(document_id)
        return deepcopy(item) if item else None

    def list_all(self) -> list[KnowledgeDocument]:
        return [deepcopy(item) for item in self._items.values()]

    def list_by_tags(self, tags: list[str], limit: int) -> list[KnowledgeDocument]:
        matched = []
        for doc in self._items.values():
            # 检查文档的 tags 是否与查询 tags 有交集
            if any(tag in doc.tags for tag in tags):
                matched.append(doc)
        # 按创建时间倒序排序（最近优先），创建时间存储在 metadata["created_at"] 中
        matched.sort(key=lambda d: d.metadata.get("created_at", ""), reverse=True)
        return [deepcopy(doc) for doc in matched[:limit]]

    def delete(self, document_id: str) -> bool:
        if document_id in self._items:
            del self._items[document_id]
            return True
        return False


class InMemoryWorkingMemoryRepository:
    def __init__(self) -> None:
        self._items: dict[str, ConversationWorkingMemory] = {}

    def save(self, memory: ConversationWorkingMemory) -> ConversationWorkingMemory:
        stored = deepcopy(memory)
        self._items[memory.conversation_id] = stored
        return deepcopy(stored)

    def get(self, conversation_id: str) -> ConversationWorkingMemory | None:
        item = self._items.get(conversation_id)
        return deepcopy(item) if item else None

    def delete(self, conversation_id: str) -> bool:
        if conversation_id not in self._items:
            return False
        del self._items[conversation_id]
        return True


class InMemoryResearchPaperRepository:
    def __init__(self) -> None:
        self._items: dict[str, ConversationResearchPaper] = {}

    def save(self, paper: ConversationResearchPaper) -> ConversationResearchPaper:
        stored = deepcopy(paper)
        self._items[paper.paper_entry_id] = stored
        return deepcopy(stored)

    def get(self, paper_entry_id: str) -> ConversationResearchPaper | None:
        item = self._items.get(paper_entry_id)
        return deepcopy(item) if item else None

    def get_by_conversation_and_key(
        self,
        conversation_id: str,
        canonical_key: str,
    ) -> ConversationResearchPaper | None:
        for item in self._items.values():
            if item.conversation_id == conversation_id and item.canonical_key == canonical_key:
                return deepcopy(item)
        return None

    def list_by_conversation(self, conversation_id: str) -> list[ConversationResearchPaper]:
        items = [
            item for item in self._items.values()
            if item.conversation_id == conversation_id
        ]
        items.sort(key=lambda item: item.updated_at, reverse=True)
        return [deepcopy(item) for item in items]

    def delete_by_conversation(self, conversation_id: str) -> int:
        paper_ids = [
            paper_id for paper_id, item in self._items.items()
            if item.conversation_id == conversation_id
        ]
        for paper_id in paper_ids:
            del self._items[paper_id]
        return len(paper_ids)
