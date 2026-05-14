from __future__ import annotations


class ProductAgentError(Exception):
    """服务层业务异常基类。"""


class ConversationNotFoundError(ProductAgentError):
    """会话不存在。"""


class TaskNotFoundError(ProductAgentError):
    """任务不存在。"""


class InvalidTaskModeError(ProductAgentError):
    """任务模式非法。"""
