from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from product_agent.domain import MessageRecord
from product_agent.repositories import ConversationRepository, MessageRepository


class MessageService:
    """
    处理多轮对话消息的创建、读取和后续上下文压缩入口。

    当前阶段：
    - 支持最小消息写入
    - 支持按会话读取消息列表

    后续重点：
    - 增加会话摘要压缩入口
    - 增加 system / assistant 消息写入辅助函数
    - 增加基于时间窗或数量截断的上下文提取
    """

    def __init__(
        self,
        *,
        repository: MessageRepository,
        conversation_repository: ConversationRepository,
    ) -> None:
        self.repository = repository
        self.conversation_repository = conversation_repository

    def create_message(
        self,
        *,
        conversation_id: str,
        role: str,
        content: str,
        metadata: dict | None = None,
    ) -> MessageRecord | None:
        """
        向指定会话写入一条消息。

        返回：
        - `MessageRecord`：写入成功
        - `None`：会话不存在

        副作用：
        - 更新 `Conversation.message_ids`
        - 更新 `Conversation.updated_at`
        """
        conversation = self.conversation_repository.get(conversation_id)
        if conversation is None:
            return None

        message = MessageRecord(
            message_id=f"msg_{uuid4().hex[:12]}",
            conversation_id=conversation_id,
            role=role,
            content=content,
            metadata=metadata or {},
            created_at=datetime.now(timezone.utc),
        )
        created = self.repository.create(message)

        conversation.message_ids.append(created.message_id)
        conversation.updated_at = datetime.now(timezone.utc)
        self.conversation_repository.update(conversation)
        return created

    def list_messages(self, conversation_id: str) -> list[MessageRecord] | None:
        """
        读取某个会话的消息列表。

        返回：
        - `list[MessageRecord]`：会话存在
        - `None`：会话不存在
        """
        conversation = self.conversation_repository.get(conversation_id)
        if conversation is None:
            return None
        return self.repository.list_by_conversation(conversation_id)

    def create_assistant_message(
        self,
        *,
        conversation_id: str,
        content: str,
        metadata: dict | None = None,
    ) -> MessageRecord | None:
        """
        写入一条 assistant 消息。

        说明：
        - 这是对 `create_message(..., role="assistant")` 的轻量封装
        - 用于把任务运行结果、失败提示、摘要结论沉淀回会话历史
        """
        return self.create_message(
            conversation_id=conversation_id,
            role="assistant",
            content=content,
            metadata=metadata,
        )

    def get_recent_context(self, conversation_id: str, *, limit: int = 6) -> list[MessageRecord] | None:
        """
        获取最近若干条消息，作为 follow-up 任务的轻量上下文输入。

        当前约定：
        - 只做简单截断，不做摘要压缩
        - 后续可升级为真正的 context compression
        """
        messages = self.list_messages(conversation_id)
        if messages is None:
            return None
        if limit <= 0:
            return []
        return messages[-limit:]
