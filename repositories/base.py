from __future__ import annotations

from typing import Protocol

from product_agent.domain import (
    Conversation,
    ConversationResearchPaper,
    ConversationWorkingMemory,
    KnowledgeDocument,
    MessageRecord,
    ResearchTask,
    ResearchWorkspace,
)


class ConversationRepository(Protocol):
    def create(self, conversation: Conversation) -> Conversation:
        ...

    def get(self, conversation_id: str) -> Conversation | None:
        ...

    def update(self, conversation: Conversation) -> Conversation:
        ...

    def list_all(self) -> list[Conversation]:
        ...

    def delete(self, conversation_id: str) -> bool:
        ...


class MessageRepository(Protocol):
    def create(self, message: MessageRecord) -> MessageRecord:
        ...

    def list_by_conversation(self, conversation_id: str) -> list[MessageRecord]:
        ...

    def delete_by_conversation(self, conversation_id: str) -> int:
        ...


class ResearchTaskRepository(Protocol):
    def create(self, task: ResearchTask) -> ResearchTask:
        ...

    def get(self, task_id: str) -> ResearchTask | None:
        ...

    def update(self, task: ResearchTask) -> ResearchTask:
        ...

    def list_all(self) -> list[ResearchTask]:
        ...

    def delete_by_conversation(self, conversation_id: str) -> list[str]:
        ...


class WorkspaceRepository(Protocol):
    def save(self, workspace: ResearchWorkspace) -> ResearchWorkspace:
        ...

    def get_by_task(self, task_id: str) -> ResearchWorkspace | None:
        ...

    def delete_by_task_ids(self, task_ids: list[str]) -> int:
        ...


class KnowledgeRepository(Protocol):
    def save(self, document: KnowledgeDocument) -> KnowledgeDocument:
        ...

    def list_all(self) -> list[KnowledgeDocument]:
        ...

    def get(self, document_id: str) -> KnowledgeDocument | None:
        ...

    def list_by_tags(self, tags: list[str], limit: int) -> list[KnowledgeDocument]:
        ...

    def delete(self, document_id: str) -> bool:
        ...


class WorkingMemoryRepository(Protocol):
    def save(self, memory: ConversationWorkingMemory) -> ConversationWorkingMemory:
        ...

    def get(self, conversation_id: str) -> ConversationWorkingMemory | None:
        ...

    def delete(self, conversation_id: str) -> bool:
        ...


class ResearchPaperRepository(Protocol):
    def save(self, paper: ConversationResearchPaper) -> ConversationResearchPaper:
        ...

    def get(self, paper_entry_id: str) -> ConversationResearchPaper | None:
        ...

    def get_by_conversation_and_key(
        self,
        conversation_id: str,
        canonical_key: str,
    ) -> ConversationResearchPaper | None:
        ...

    def list_by_conversation(self, conversation_id: str) -> list[ConversationResearchPaper]:
        ...

    def delete_by_conversation(self, conversation_id: str) -> int:
        ...
