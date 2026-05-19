from __future__ import annotations

import os
from pathlib import Path

from product_agent.domain import SkillDescriptor, ToolDescriptor
from product_agent.registries import SkillRegistry, ToolRegistry
from product_agent.repositories import (
    InMemoryConversationRepository,
    InMemoryKnowledgeRepository,
    InMemoryMessageRepository,
    InMemoryResearchTaskRepository,
    InMemoryWorkspaceRepository,
    SQLiteConversationRepository,
    SQLiteDatabase,
    SQLiteKnowledgeRepository,
    SQLiteMessageRepository,
    SQLiteResearchTaskRepository,
    SQLiteWorkspaceRepository,
)
from product_agent.services.conversation_service import ConversationService
from product_agent.services.knowledge_service import KnowledgeService
from product_agent.services.message_service import MessageService
from product_agent.services.research_service import ResearchService
from product_agent.services.skill_service import SkillService
from product_agent.services.tool_service import ToolService
from product_agent.services.workspace_service import WorkspaceService


class AppContainer:
    """
    应用装配入口。

    目标:
    - 统一管理服务、仓储和注册表的创建
    - 后续替换数据库或 Web 框架时，尽量不影响业务层
    """

    def __init__(
        self,
        *,
        storage_backend: str | None = None,
        sqlite_path: str | None = None,
    ) -> None:
        backend = (storage_backend or os.getenv("PRODUCT_AGENT_STORAGE", "sqlite")).strip().lower()

        if backend == "sqlite":
            db_path = sqlite_path or os.getenv("PRODUCT_AGENT_SQLITE_PATH")
            if not db_path:
                db_path = str(Path(__file__).resolve().parent / "data" / "product_agent.db")
            self.database = SQLiteDatabase(db_path)
            self.database.initialize()
            self.conversation_repository = SQLiteConversationRepository(self.database)
            self.message_repository = SQLiteMessageRepository(self.database)
            self.task_repository = SQLiteResearchTaskRepository(self.database)
            self.workspace_repository = SQLiteWorkspaceRepository(self.database)
            self.knowledge_repository = SQLiteKnowledgeRepository(self.database)
        else:
            self.database = None
            self.conversation_repository = InMemoryConversationRepository()
            self.message_repository = InMemoryMessageRepository()
            self.task_repository = InMemoryResearchTaskRepository()
            self.workspace_repository = InMemoryWorkspaceRepository()
            self.knowledge_repository = InMemoryKnowledgeRepository()

        self.tool_registry = ToolRegistry()
        self.skill_registry = SkillRegistry()
        self._register_defaults()

        self.conversation_service = ConversationService(self.conversation_repository)
        self.message_service = MessageService(
            repository=self.message_repository,
            conversation_repository=self.conversation_repository,
        )
        self.research_service = ResearchService(
            conversation_repository=self.conversation_repository,
            task_repository=self.task_repository,
            workspace_repository=self.workspace_repository,
        )
        self.workspace_service = WorkspaceService(self.workspace_repository)
        self.tool_service = ToolService(self.tool_registry)
        self.skill_service = SkillService(self.skill_registry)
        self.knowledge_service = KnowledgeService(self.knowledge_repository)

    def _register_defaults(self) -> None:
        self.tool_registry.register(
            ToolDescriptor(
                tool_id="arxiv_search",
                display_name="ArXiv Search",
                description="Searches academic papers from ArXiv.",
            )
        )
        self.tool_registry.register(
            ToolDescriptor(
                tool_id="semantic_scholar",
                display_name="Semantic Scholar",
                description="Fetches paper metadata and optional reference enrichment.",
            )
        )
        self.skill_registry.register(
            SkillDescriptor(
                skill_id="paper_compare",
                display_name="Paper Compare",
                description="Compares representative papers across method, benchmark and limitation dimensions.",
                required_tools=["arxiv_search", "semantic_scholar"],
            )
        )
