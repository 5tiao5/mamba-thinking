from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class CreateKnowledgeDocumentRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, description="Imported abstract, notes, or manually curated evidence text.")
    tags: List[str] = Field(default_factory=list)
    source_url: Optional[str] = Field(default=None, max_length=500)
    source_task_id: Optional[str] = Field(default=None, max_length=100)
    conversation_id: Optional[str] = Field(default=None, max_length=100)
    notes: Optional[str] = Field(default=None, max_length=4000)


class KnowledgeDocumentView(BaseModel):
    document_id: str
    title: str
    source_task_id: Optional[str] = None
    conversation_id: Optional[str] = None
    content: str
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ListKnowledgeDocumentsResponse(BaseModel):
    items: List[KnowledgeDocumentView] = Field(default_factory=list)


class SearchPaperCandidatesRequest(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    limit: int = Field(default=3, ge=1, le=5)


class PaperImportCandidateView(BaseModel):
    candidate_id: str
    title: str
    authors: List[str] = Field(default_factory=list)
    year: Optional[int] = None
    abstract: str = ""
    source_url: Optional[str] = None
    pdf_url: Optional[str] = None
    doi: Optional[str] = None
    arxiv_id: Optional[str] = None
    source: str
    venue: Optional[str] = None
    is_exact_match: bool = False


class ListPaperImportCandidatesResponse(BaseModel):
    items: List[PaperImportCandidateView] = Field(default_factory=list)


class ImportPaperCandidateRequest(BaseModel):
    candidate_id: str = Field(min_length=1, max_length=200)
    conversation_id: Optional[str] = Field(default=None, max_length=100)
    notes: Optional[str] = Field(default=None, max_length=4000)
    tags: List[str] = Field(default_factory=list)


PaperPoolStatus = Literal["candidate", "core", "excluded"]


class ResearchPaperView(BaseModel):
    paper_entry_id: str
    conversation_id: str
    document_id: str
    canonical_key: str
    title: str
    origin: str
    status: PaperPoolStatus
    source_url: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str


class ListResearchPapersResponse(BaseModel):
    items: List[ResearchPaperView] = Field(default_factory=list)
    total: int = 0


class UpdateResearchPaperRequest(BaseModel):
    status: PaperPoolStatus


class PdfImportItemView(BaseModel):
    filename: str
    success: bool
    document: Optional[KnowledgeDocumentView] = None
    research_paper: Optional[ResearchPaperView] = None
    parsed_pages: int = 0
    total_pages: int = 0
    duplicate_replaced: bool = False
    warnings: List[str] = Field(default_factory=list)
    error_code: str = ""
    error_message: str = ""


class BatchPdfImportResponse(BaseModel):
    items: List[PdfImportItemView] = Field(default_factory=list)
    imported_count: int = 0
    failed_count: int = 0
