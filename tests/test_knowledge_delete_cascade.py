from __future__ import annotations

from product_agent.domain import Conversation
from product_agent.repositories import (
    SQLiteConversationRepository,
    SQLiteDatabase,
    SQLiteKnowledgeRepository,
    SQLiteResearchPaperRepository,
    SQLiteVectorStore,
)
from product_agent.services.knowledge_service import KnowledgeService
from product_agent.services.research_paper_service import ResearchPaperService


def test_deleting_knowledge_document_removes_research_paper_links_and_chunks(tmp_path) -> None:
    database = SQLiteDatabase(tmp_path / "product_agent.sqlite")
    database.initialize()
    conversation_repository = SQLiteConversationRepository(database)
    knowledge_repository = SQLiteKnowledgeRepository(database)
    paper_repository = SQLiteResearchPaperRepository(database)
    vector_store = SQLiteVectorStore(database)
    knowledge_service = KnowledgeService(
        knowledge_repository,
        vector_store=vector_store,
    )
    paper_service = ResearchPaperService(paper_repository)
    conversation_id = "conversation-delete-cascade"

    conversation_repository.create(
        Conversation(
            conversation_id=conversation_id,
            title="Delete cascade",
            topic="multimodal fusion",
        )
    )
    document = knowledge_service.import_document(
        title="User imported multimodal fusion paper",
        content=(
            "Multimodal fusion paper about cross-modal alignment, "
            "missing modality robustness, and large multimodal models."
        ),
        conversation_id=conversation_id,
        metadata_extra={"paper_source": "user_upload"},
    )
    paper = paper_service.add_document(
        conversation_id=conversation_id,
        document=document,
        origin="user_upload",
        status="core",
    )

    assert paper_repository.get(paper.paper_entry_id) is not None
    assert vector_store.count() > 0

    assert knowledge_service.delete_document(document.document_id) is True

    assert knowledge_repository.get(document.document_id) is None
    assert paper_repository.list_by_conversation(conversation_id) == []
    assert vector_store.count() == 0
