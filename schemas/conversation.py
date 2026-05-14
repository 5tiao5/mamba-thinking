from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class CreateConversationRequest(BaseModel):
    topic: str = Field(..., description="本次会话围绕的研究主题")
    title: Optional[str] = Field(default=None, description="会话标题；为空时可回退为 topic")


class CreateConversationResponse(BaseModel):
    conversation_id: str
    topic: str
    title: str


class SendMessageRequest(BaseModel):
    role: str = Field(..., description="消息角色，通常为 user")
    content: str = Field(..., description="用户输入内容")
    run_research: bool = Field(default=True, description="是否基于该消息触发一轮研究任务")


class FollowUpTaskPreview(BaseModel):
    task_id: str
    topic: str
    status: str
    trigger_message_id: Optional[str] = None


class ContinueConversationRequest(BaseModel):
    conversation_id: str
    content: str
    focus: Optional[str] = Field(default=None, description="本轮追问希望聚焦的子问题")
    create_follow_up_task: bool = Field(default=True, description="是否为本轮追问创建 follow-up 任务")
    mode: str = Field(default="default", description="follow-up 任务模式：default / fast / balanced")


class ContinueConversationResponse(BaseModel):
    conversation_id: str
    next_focus: str
    message: str
    message_id: Optional[str] = None
    context_preview: list[str] = Field(default_factory=list)
    follow_up_task: Optional[FollowUpTaskPreview] = None
