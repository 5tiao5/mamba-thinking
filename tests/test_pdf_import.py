from __future__ import annotations

import fitz
from fastapi.testclient import TestClient

from product_agent.api.fastapi_app import create_app
from product_agent.app_container import AppContainer
from product_agent.services.pdf_import_service import PdfImportService, PdfUploadInput


def _pdf_bytes(title: str, body: str = "This paper studies reliable tool use.") -> bytes:
    document = fitz.open()
    document.set_metadata({"title": title})
    page = document.new_page()
    page.insert_text((72, 72), f"{title}\nAbstract\n{body}")
    payload = document.tobytes()
    document.close()
    return payload


def test_pdf_import_batch_isolates_bad_files_and_enters_paper_pool() -> None:
    container = AppContainer(storage_backend="memory")
    conversation = container.conversation_service.create_conversation(
        topic="Agent tool-use evaluation",
    )

    results = container.pdf_import_service.import_batch(
        conversation_id=conversation.conversation_id,
        uploads=[
            PdfUploadInput(
                filename="benchmark.pdf",
                content_type="application/pdf",
                payload=_pdf_bytes("Reliable Tool Use Benchmark"),
            ),
            PdfUploadInput(
                filename="broken.pdf",
                content_type="application/pdf",
                payload=b"%PDF-broken",
            ),
        ],
    )

    assert [result.success for result in results] == [True, False]
    assert results[0].document is not None
    assert results[0].research_paper is not None
    assert results[0].research_paper.origin == "user_upload"
    assert results[0].document.metadata["conversation_id"] == conversation.conversation_id
    assert results[0].document.metadata["page_count"] == 1
    assert "[Page 1]" in results[0].document.content
    assert results[1].error_code == "pdf_parse_failed"
    assert len(container.research_paper_service.list_papers(conversation.conversation_id)) == 1


def test_reupload_replaces_old_knowledge_document_without_duplicating_pool_entry() -> None:
    container = AppContainer(storage_backend="memory")
    conversation = container.conversation_service.create_conversation(topic="Research agents")
    service: PdfImportService = container.pdf_import_service
    first = service.import_batch(
        conversation_id=conversation.conversation_id,
        uploads=[
            PdfUploadInput(
                filename="paper-v1.pdf",
                content_type="application/pdf",
                payload=_pdf_bytes("Persistent Research Agent"),
            )
        ],
    )[0]
    old_document_id = first.document.document_id

    second = service.import_batch(
        conversation_id=conversation.conversation_id,
        uploads=[
            PdfUploadInput(
                filename="paper-v2.pdf",
                content_type="application/pdf",
                payload=_pdf_bytes(
                    "Persistent Research Agent",
                    "This revised paper includes stronger evidence.",
                ),
            )
        ],
    )[0]

    assert second.success is True
    assert second.duplicate_replaced is True
    assert second.research_paper.paper_entry_id == first.research_paper.paper_entry_id
    assert second.document.document_id != old_document_id
    assert container.knowledge_service.get_document(old_document_id) is None
    assert len(container.research_paper_service.list_papers(conversation.conversation_id)) == 1


def test_pdf_import_api_returns_per_file_results() -> None:
    container = AppContainer(storage_backend="memory")
    conversation = container.conversation_service.create_conversation(topic="Research agents")
    client = TestClient(create_app(container))

    response = client.post(
        f"/conversations/{conversation.conversation_id}/papers/import-pdfs",
        files=[
            (
                "files",
                ("paper.pdf", _pdf_bytes("Research Agent Evidence"), "application/pdf"),
            ),
            (
                "files",
                ("notes.txt", b"not a pdf", "text/plain"),
            ),
        ],
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["imported_count"] == 1
    assert payload["data"]["failed_count"] == 1
    assert payload["data"]["items"][1]["error_code"] == "unsupported_file_type"
    assert container.task_repository.list_all() == []
