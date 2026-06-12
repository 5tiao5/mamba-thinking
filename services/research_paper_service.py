from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from product_agent.domain import ConversationResearchPaper, KnowledgeDocument
from product_agent.repositories import ResearchPaperRepository


class ResearchPaperServiceError(ValueError):
    pass


class ResearchPaperService:
    """Maintain the durable paper corpus attached to a research conversation."""

    ALLOWED_STATUSES = {"candidate", "core", "excluded"}
    ALLOWED_ORIGINS = {"user_import", "user_upload", "system_search"}

    def __init__(self, repository: ResearchPaperRepository) -> None:
        self.repository = repository

    def add_document(
        self,
        *,
        conversation_id: str,
        document: KnowledgeDocument,
        origin: str = "user_import",
        status: str = "candidate",
    ) -> ConversationResearchPaper:
        normalized_origin = self._validate_origin(origin)
        normalized_status = self._validate_status(status)
        canonical_key = self._canonical_key(document)
        existing = self.repository.get_by_conversation_and_key(conversation_id, canonical_key)
        now = datetime.now(timezone.utc)
        metadata = self._paper_metadata(document)

        if existing is not None:
            existing.document_id = document.document_id
            existing.title = document.title
            if existing.status not in {"core", "excluded"}:
                existing.status = normalized_status
            existing.source_url = str(document.metadata.get("source_url", "") or "")
            existing.metadata = metadata
            existing.updated_at = now
            return self.repository.save(existing)

        return self.repository.save(
            ConversationResearchPaper(
                paper_entry_id=f"research_paper_{uuid4().hex[:12]}",
                conversation_id=conversation_id,
                document_id=document.document_id,
                canonical_key=canonical_key,
                title=document.title,
                origin=normalized_origin,
                status=normalized_status,
                source_url=str(document.metadata.get("source_url", "") or ""),
                metadata=metadata,
                created_at=now,
                updated_at=now,
            )
        )

    def list_papers(
        self,
        conversation_id: str,
        *,
        status: str | None = None,
    ) -> list[ConversationResearchPaper]:
        papers = self.repository.list_by_conversation(conversation_id)
        if status is None:
            return papers
        normalized_status = self._validate_status(status)
        return [paper for paper in papers if paper.status == normalized_status]

    def find_matching_document(
        self,
        *,
        conversation_id: str,
        document: KnowledgeDocument,
    ) -> ConversationResearchPaper | None:
        return self.repository.get_by_conversation_and_key(
            conversation_id,
            self._canonical_key(document),
        )

    def update_status(
        self,
        *,
        conversation_id: str,
        paper_entry_id: str,
        status: str,
    ) -> ConversationResearchPaper:
        paper = self.repository.get(paper_entry_id)
        if paper is None or paper.conversation_id != conversation_id:
            raise KeyError(paper_entry_id)
        paper.status = self._validate_status(status)
        paper.updated_at = datetime.now(timezone.utc)
        return self.repository.save(paper)

    @classmethod
    def validate_status(cls, status: str) -> str:
        return cls._validate_status(status)

    @classmethod
    def _validate_status(cls, status: str) -> str:
        normalized = (status or "").strip().lower()
        if normalized not in cls.ALLOWED_STATUSES:
            raise ResearchPaperServiceError(
                f"Paper status `{status}` is invalid. Supported values: {sorted(cls.ALLOWED_STATUSES)}."
            )
        return normalized

    @classmethod
    def _validate_origin(cls, origin: str) -> str:
        normalized = (origin or "").strip().lower()
        if normalized not in cls.ALLOWED_ORIGINS:
            raise ResearchPaperServiceError(
                f"Paper origin `{origin}` is invalid. Supported values: {sorted(cls.ALLOWED_ORIGINS)}."
            )
        return normalized

    @staticmethod
    def _canonical_key(document: KnowledgeDocument) -> str:
        metadata = document.metadata or {}
        doi = str(metadata.get("doi", "") or "").strip().lower()
        if doi:
            return f"doi:{doi.removeprefix('https://doi.org/').removeprefix('http://doi.org/')}"
        arxiv_id = str(metadata.get("arxiv_id", "") or "").strip().lower()
        if arxiv_id:
            normalized_arxiv_id = re.sub(r"v\d+$", "", arxiv_id)
            return f"arxiv:{normalized_arxiv_id}"
        normalized_title = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", document.title.lower())
        normalized_title = " ".join(normalized_title.split())
        return f"title:{normalized_title}"

    @staticmethod
    def _paper_metadata(document: KnowledgeDocument) -> dict[str, Any]:
        source = document.metadata or {}
        keys = (
            "authors",
            "year",
            "doi",
            "arxiv_id",
            "pdf_url",
            "venue",
            "paper_source",
            "import_method",
        )
        return {key: source.get(key) for key in keys if source.get(key) not in (None, "", [])}
