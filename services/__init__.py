from __future__ import annotations

from importlib import import_module

from .errors import ConversationNotFoundError, InvalidTaskModeError, ProductAgentError, TaskNotFoundError
from .workspace_mapper import workspace_from_agent_state

__all__ = [
    "ConversationService",
    "ProductAgentError",
    "ConversationNotFoundError",
    "TaskNotFoundError",
    "InvalidTaskModeError",
    "MessageService",
    "ResearchService",
    "WorkspaceService",
    "ToolService",
    "SkillService",
    "KnowledgeService",
    "workspace_from_agent_state",
]


_LAZY_IMPORTS = {
    "ConversationService": ("product_agent.services.conversation_service", "ConversationService"),
    "MessageService": ("product_agent.services.message_service", "MessageService"),
    "ResearchService": ("product_agent.services.research_service", "ResearchService"),
    "WorkspaceService": ("product_agent.services.workspace_service", "WorkspaceService"),
    "ToolService": ("product_agent.services.tool_service", "ToolService"),
    "SkillService": ("product_agent.services.skill_service", "SkillService"),
    "KnowledgeService": ("product_agent.services.knowledge_service", "KnowledgeService"),
}


def __getattr__(name: str):
    if name not in _LAZY_IMPORTS:
        raise AttributeError(name)
    module_name, attr_name = _LAZY_IMPORTS[name]
    module = import_module(module_name)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value
