from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class CreateConversationRequest(BaseModel):
    topic: str = Field(..., description="本次会话的研究主题")
    title: Optional[str] = Field(default=None, description="会话标题，留空时可自动生成")


class CreateConversationResponse(BaseModel):
    conversation_id: str
    topic: str
    title: str


class SendMessageRequest(BaseModel):
    role: str = Field(..., description="通常为 user")
    content: str = Field(..., description="用户输入内容")
    run_research: bool = Field(default=True, description="是否基于这条消息触发一次研究任务")


class ContinueConversationRequest(BaseModel):
    conversation_id: str
    content: str
    focus: Optional[str] = Field(default=None, description="本轮追问希望聚焦的子问题")

