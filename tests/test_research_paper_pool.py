from __future__ import annotations

from pathlib import Path

from product_agent.api.handlers import ProductApiHandlers
from product_agent.app_container import AppContainer
from product_agent.domain import KnowledgeDocument
from product_agent.repositories import (
    InMemoryResearchPaperRepository,
    SQLiteDatabase,
    SQLiteResearchPaperRepository,
)
from product_agent.services.knowledge_service import PaperImportCandidate
from product_agent.services.research_paper_service import ResearchPaperService
from product_agent.schemas import ImportPaperCandidateRequest, UpdateResearchPaperRequest


def _paper_document(*, document_id: str, title: str, doi: str = "") -> KnowledgeDocument:
    metadata = {
        "source_type": "paper_import",
        "source_url": "https://example.org/paper",
        "authors": ["Researcher A"],
    }
    if doi:
        metadata["doi"] = doi
    return KnowledgeDocument(
        document_id=document_id,
        title=title,
        content="paper evidence",
        metadata=metadata,
    )


def test_paper_pool_deduplicates_by_doi_and_preserves_user_status() -> None:
    service = ResearchPaperService(InMemoryResearchPaperRepository())
    first = service.add_document(
        conversation_id="conversation-1",
        document=_paper_document(
            document_id="doc-1",
            title="Original title",
            doi="10.1000/example",
        ),
    )
    service.update_status(
        conversation_id="conversation-1",
        paper_entry_id=first.paper_entry_id,
        status="core",
    )

    second = service.add_document(
        conversation_id="conversation-1",
        document=_paper_document(
            document_id="doc-2",
            title="Updated title",
            doi="https://doi.org/10.1000/example",
        ),
    )

    assert second.paper_entry_id == first.paper_entry_id
    assert second.document_id == "doc-2"
    assert second.title == "Updated title"
    assert second.status == "core"
    assert len(service.list_papers("conversation-1")) == 1


def test_sqlite_paper_pool_persists_status(tmp_path: Path) -> None:
    database = SQLiteDatabase(tmp_path / "paper-pool.db")
    database.initialize()
    service = ResearchPaperService(SQLiteResearchPaperRepository(database))
    document = _paper_document(
        document_id="doc-sqlite",
        title="Persistent paper",
        doi="10.1000/persistent",
    )

    with database.connect() as connection:
        connection.execute(
            """
            INSERT INTO conversations (
                conversation_id, title, topic, status, message_ids_json,
                latest_task_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "conversation-sqlite",
                "Persistent research",
                "Persistent research",
                "active",
                "[]",
                None,
                "2026-06-12T00:00:00+00:00",
                "2026-06-12T00:00:00+00:00",
            ),
        )
        connection.execute(
            """
            INSERT INTO knowledge_documents (
                document_id, title, source_task_id, content, tags_json, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                document.document_id,
                document.title,
                None,
                document.content,
                "[]",
                '{"doi":"10.1000/persistent"}',
            ),
        )
        connection.commit()

    paper = service.add_document(
        conversation_id="conversation-sqlite",
        document=document,
        origin="user_upload",
    )
    service.update_status(
        conversation_id="conversation-sqlite",
        paper_entry_id=paper.paper_entry_id,
        status="excluded",
    )

    reloaded = ResearchPaperService(SQLiteResearchPaperRepository(database))
    papers = reloaded.list_papers("conversation-sqlite", status="excluded")
    assert len(papers) == 1
    assert papers[0].canonical_key == "doi:10.1000/persistent"
    assert papers[0].origin == "user_upload"


def test_candidate_import_enters_conversation_paper_pool_and_can_be_promoted() -> None:
    container = AppContainer(storage_backend="memory")
    conversation = container.conversation_service.create_conversation(
        topic="Agent tool-use evaluation",
    )
    candidate = PaperImportCandidate(
        candidate_id="candidate-1",
        title="A Benchmark for Agent Tool Use",
        authors=["Researcher A"],
        year=2026,
        abstract="A benchmark for tool selection and failure recovery.",
        source_url="https://example.org/benchmark",
        pdf_url="https://example.org/benchmark.pdf",
        doi="10.1000/agent-benchmark",
        source="openalex",
        venue="Example Conference",
        is_exact_match=True,
    )
    container.knowledge_service.paper_candidate_cache[candidate.candidate_id] = candidate
    handlers = ProductApiHandlers(
        conversation_service=container.conversation_service,
        message_service=container.message_service,
        research_service=container.research_service,
        workspace_service=container.workspace_service,
        tool_service=container.tool_service,
        skill_service=container.skill_service,
        knowledge_service=container.knowledge_service,
        research_paper_service=container.research_paper_service,
    )

    imported = handlers.import_paper_candidate(
        ImportPaperCandidateRequest(
            candidate_id=candidate.candidate_id,
            conversation_id=conversation.conversation_id,
        )
    ).model_dump()
    assert imported["success"] is True
    paper_entry_id = imported["data"]["research_paper"]["paper_entry_id"]

    listed = handlers.list_research_papers(conversation.conversation_id).model_dump()
    assert listed["data"]["total"] == 1
    assert listed["data"]["items"][0]["status"] == "candidate"

    promoted = handlers.update_research_paper(
        conversation.conversation_id,
        paper_entry_id,
        UpdateResearchPaperRequest(status="core"),
    ).model_dump()
    assert promoted["success"] is True
    assert promoted["data"]["status"] == "core"
