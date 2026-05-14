from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from product_agent.domain import Conversation
from product_agent.repositories import ConversationRepository


class ConversationService:
    """
    处理会话的创建、读取和后续多轮上下文挂载。

    当前阶段:
    - 提供 create / get 的最小能力

    后续重点:
    - 会话摘要
    - 历史会话列表
    - 多轮上下文压缩
    """

    def __init__(self, repository: ConversationRepository) -> None:
        self.repository = repository

    def create_conversation(self, *, topic: str, title: str | None = None) -> Conversation:
        """
        创建一个新的研究会话。

        调用者:
        - `ProductApiHandlers.create_conversation`

        参数:
        - `topic`: 研究主题，是整轮会话的默认主线
        - `title`: 可选标题；为空时回退为 `topic`

        返回:
        - `Conversation`

        待实现:
        1. 创建时同步生成一条 system welcome message
        2. 预留会话级配置，如默认工具集合和共享知识开关
        3. 增加 `conversation_summary` 字段，服务于多轮上下文压缩
        """
        conversation = Conversation(
            conversation_id=f"conv_{uuid4().hex[:12]}",
            topic=topic,
            title=title or topic,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        return self.repository.create(conversation)

    def get_conversation(self, conversation_id: str) -> Conversation | None:
        """
        根据 ID 获取会话。

        调用者:
        - `ProductApiHandlers.continue_conversation`
        - `MessageService`
        - 后续的 `ContextService`
        """
        return self.repository.get(conversation_id)
