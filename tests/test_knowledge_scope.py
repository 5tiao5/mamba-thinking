from __future__ import annotations

from product_agent.repositories import InMemoryKnowledgeRepository
from product_agent.services.knowledge_service import KnowledgeService


def _build_service() -> KnowledgeService:
    return KnowledgeService(
        InMemoryKnowledgeRepository(),
        enable_hybrid_search=True,
    )


def _import_fixture_documents(service: KnowledgeService) -> dict[str, str]:
    shared = service.import_document(
        title="Shared tool-use benchmark evidence",
        content="tool selection function calling failure recovery benchmark",
    )
    current = service.import_document(
        title="Current research private evidence",
        content="tool selection function calling failure recovery benchmark",
        conversation_id="conversation-current",
    )
    other = service.import_document(
        title="Other research private evidence",
        content="tool selection function calling failure recovery benchmark",
        conversation_id="conversation-other",
    )
    return {
        "shared": shared.document_id,
        "current": current.document_id,
        "other": other.document_id,
    }


def test_shared_scope_combines_global_and_current_conversation_only() -> None:
    service = _build_service()
    ids = _import_fixture_documents(service)

    hits = service.retrieve_hits_for_context(
        "tool selection function calling failure recovery benchmark",
        top_k=10,
        knowledge_scope="shared",
        conversation_id="conversation-current",
    )

    hit_ids = {hit.document_id for hit in hits}
    assert ids["shared"] in hit_ids
    assert ids["current"] in hit_ids
    assert ids["other"] not in hit_ids


def test_conversation_only_scope_excludes_global_and_other_conversations() -> None:
    service = _build_service()
    ids = _import_fixture_documents(service)

    hits = service.retrieve_hits_for_context(
        "tool selection function calling failure recovery benchmark",
        top_k=10,
        knowledge_scope="conversation_only",
        conversation_id="conversation-current",
    )

    assert {hit.document_id for hit in hits} == {ids["current"]}
    assert hits[0].scope == "conversation"


def test_shared_scope_without_conversation_returns_global_documents_only() -> None:
    service = _build_service()
    ids = _import_fixture_documents(service)

    hits = service.retrieve_hits_for_context(
        "tool selection function calling failure recovery benchmark",
        top_k=10,
        knowledge_scope="shared",
        conversation_id=None,
    )

    assert {hit.document_id for hit in hits} == {ids["shared"]}


def test_imported_documents_record_explicit_visibility() -> None:
    service = _build_service()

    private_document = service.import_document(
        title="Private paper",
        content="private research evidence",
        conversation_id="conversation-current",
    )
    shared_document = service.import_document(
        title="Shared paper",
        content="global research evidence",
    )

    assert private_document.metadata["visibility"] == "conversation"
    assert private_document.metadata["conversation_id"] == "conversation-current"
    assert shared_document.metadata["visibility"] == "shared"
    assert "conversation_id" not in shared_document.metadata
