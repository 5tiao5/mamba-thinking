from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field


class CreateMessageRequest(BaseModel):
    role: str = Field(default="user", description="消息角色，当前前端默认发送 user")
    content: str = Field(..., description="消息正文")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="消息扩展信息")


class MessageView(BaseModel):
    message_id: str
    conversation_id: str
    role: str
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: str


class ListMessagesResponse(BaseModel):
    conversation_id: str
    items: List[MessageView] = Field(default_factory=list)
