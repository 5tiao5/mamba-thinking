from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class CreateKnowledgeDocumentRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, description="Imported abstract, notes, or manually curated evidence text.")
    tags: List[str] = Field(default_factory=list)
    source_url: Optional[str] = Field(default=None, max_length=500)
    source_task_id: Optional[str] = Field(default=None, max_length=100)
    notes: Optional[str] = Field(default=None, max_length=4000)


class KnowledgeDocumentView(BaseModel):
    document_id: str
    title: str
    source_task_id: Optional[str] = None
    content: str
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ListKnowledgeDocumentsResponse(BaseModel):
    items: List[KnowledgeDocumentView] = Field(default_factory=list)
