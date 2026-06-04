from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


KnowledgeScopeLiteral = Literal["none", "conversation_only", "shared"]


class CreateConversationRequest(BaseModel):
    topic: str = Field(..., description="Research topic for this conversation")
    title: Optional[str] = Field(default=None, description="Optional display title; falls back to topic")


class CreateConversationResponse(BaseModel):
    conversation_id: str
    topic: str
    title: str


class ConversationSummaryView(BaseModel):
    conversation_id: str
    topic: str
    title: str
    status: str
    latest_task_id: Optional[str] = None
    created_at: str
    updated_at: str


class ConversationDetailResponse(ConversationSummaryView):
    message_count: int = 0


class SendMessageRequest(BaseModel):
    role: str = Field(..., description="Message role, usually user")
    content: str = Field(..., description="User message content")
    run_research: bool = Field(default=True, description="Whether this message should trigger a research task")


class FollowUpTaskPreview(BaseModel):
    task_id: str
    topic: str
    status: str
    trigger_message_id: Optional[str] = None


class ContinueConversationRequest(BaseModel):
    conversation_id: str
    content: str
    focus: Optional[str] = Field(default=None, description="Optional sub-problem to focus on in this follow-up")
    create_follow_up_task: bool = Field(default=True, description="Whether to create a follow-up research task")
    mode: str = Field(default="default", description="Follow-up task mode: default / fast / balanced")
    knowledge_scope: Optional[KnowledgeScopeLiteral] = Field(
        default=None,
        description="Knowledge scope for this follow-up: none / conversation_only / shared.",
    )
    selected_skill_ids: list[str] = Field(default_factory=list, description="Skill IDs to activate for this follow-up task")

    def resolve_knowledge_scope(self) -> str:
        return self.knowledge_scope or "shared"


class KnowledgeHitView(BaseModel):
    document_id: str
    title: str
    snippet: str
    score: float = 0.0
    scope: str = "shared"
    source_task_id: Optional[str] = None
    source_type: str = ""
    evidence_level: str = "candidate"
    matched_chunk_count: int = 0
    supporting_snippets: list[str] = Field(default_factory=list)


class ContinueConversationResponse(BaseModel):
    conversation_id: str
    next_focus: str
    message: str
    message_id: Optional[str] = None
    context_preview: list[str] = Field(default_factory=list)
    knowledge_scope_applied: KnowledgeScopeLiteral = "shared"
    knowledge_context: list[str] = Field(default_factory=list, description="Retrieved knowledge snippets")
    knowledge_hits: list[KnowledgeHitView] = Field(default_factory=list, description="Structured knowledge hits")
    workspace_context: list[str] = Field(default_factory=list, description="Conversation workspace guidance")
    follow_up_task: Optional[FollowUpTaskPreview] = None


class ListConversationsResponse(BaseModel):
    items: list[ConversationSummaryView] = Field(default_factory=list)
