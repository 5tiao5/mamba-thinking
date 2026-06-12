from __future__ import annotations

import os
from pathlib import Path

from product_agent.domain import SkillDescriptor, ToolDescriptor
from product_agent.registries import SkillRegistry, ToolRegistry
from product_agent.repositories import (
    InMemoryConversationRepository,
    InMemoryWorkingMemoryRepository,
    InMemoryKnowledgeRepository,
    InMemoryMessageRepository,
    InMemoryResearchPaperRepository,
    InMemoryResearchTaskRepository,
    InMemoryWorkspaceRepository,
    SQLiteConversationRepository,
    SQLiteDatabase,
    SQLiteSkillRepository,
    SQLiteWorkingMemoryRepository,
    SQLiteKnowledgeRepository,
    SQLiteMessageRepository,
    SQLiteResearchPaperRepository,
    SQLiteResearchTaskRepository,
    SQLiteVectorStore,
    SQLiteWorkspaceRepository,
)
from product_agent.services.knowledge_service import HashEmbedder
from product_agent.services.conversation_service import ConversationService
from product_agent.services.knowledge_service import KnowledgeService
from product_agent.services.message_service import MessageService
from product_agent.services.pdf_import_service import PdfImportService
from product_agent.services.research_paper_service import ResearchPaperService
from product_agent.services.research_service import ResearchService
from product_agent.services.skill_service import SkillService
from product_agent.services.tool_service import ToolService
from product_agent.services.working_memory_service import WorkingMemoryService
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
            self.working_memory_repository = SQLiteWorkingMemoryRepository(self.database)
            self.knowledge_repository = SQLiteKnowledgeRepository(self.database)
            self.research_paper_repository = SQLiteResearchPaperRepository(self.database)
        else:
            self.database = None
            self.conversation_repository = InMemoryConversationRepository()
            self.message_repository = InMemoryMessageRepository()
            self.task_repository = InMemoryResearchTaskRepository()
            self.workspace_repository = InMemoryWorkspaceRepository()
            self.working_memory_repository = InMemoryWorkingMemoryRepository()
            self.knowledge_repository = InMemoryKnowledgeRepository()
            self.research_paper_repository = InMemoryResearchPaperRepository()

        self.tool_registry = ToolRegistry()
        self.skill_registry = SkillRegistry()
        self._register_defaults()

        # Services - 注意顺序：先创建不依赖其他服务的，后创建有依赖的
        self.conversation_service = ConversationService(
            self.conversation_repository,
            message_repository=self.message_repository,
            task_repository=self.task_repository,
            workspace_repository=self.workspace_repository,
            working_memory_repository=self.working_memory_repository,
            research_paper_repository=self.research_paper_repository,
        )
        self.message_service = MessageService(
            repository=self.message_repository,
            conversation_repository=self.conversation_repository,
        )
        self.working_memory_service = WorkingMemoryService(self.working_memory_repository)
        self.research_paper_service = ResearchPaperService(self.research_paper_repository)

        # ✅ 先创建 knowledge_service（被 research_service 依赖）
        # SQLite mode: 注入持久化向量存储和确定性哈希嵌入器
        if backend == "sqlite":
            self.knowledge_service = KnowledgeService(
                self.knowledge_repository,
                vector_store=SQLiteVectorStore(self.database),
                embedder=HashEmbedder(),
                task_repository=self.task_repository,
                async_indexing=True,
            )
        else:
            self.knowledge_service = KnowledgeService(
                self.knowledge_repository,
                embedder=HashEmbedder(),
                task_repository=self.task_repository,
                async_indexing=True,
            )

        self.pdf_import_service = PdfImportService(
            knowledge_service=self.knowledge_service,
            research_paper_service=self.research_paper_service,
        )

        # ✅ 先创建 tool_service 和 skill_service（被 research_service 依赖）
        self.tool_service = ToolService(self.tool_registry)
        self.skill_service = SkillService(
            self.skill_registry,
            repository=SQLiteSkillRepository(self.database) if backend == "sqlite" else None,
            tool_registry=self.tool_registry,
        )

        # ✅ 再创建 research_service
        self.workspace_service = WorkspaceService(
            self.workspace_repository,
            conversation_repository=self.conversation_repository,
            task_repository=self.task_repository,
            working_memory_service=self.working_memory_service,
        )
        self.research_service = ResearchService(
            conversation_repository=self.conversation_repository,
            task_repository=self.task_repository,
            workspace_repository=self.workspace_repository,
            workspace_service=self.workspace_service,
            message_service=self.message_service,
            knowledge_service=self.knowledge_service,
            working_memory_service=self.working_memory_service,
            skill_service=self.skill_service,
        )
        # 注意：self.knowledge_service 已经在上面创建，这里不要重复创建

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
        self.tool_registry.register(
            ToolDescriptor(
                tool_id="paper_resolver",
                display_name="Paper Resolver",
                description=(
                    "Resolves a title, DOI, arXiv ID, or paper URL into a "
                    "canonical paper identity and open-access location."
                ),
                config={
                    "accepted_inputs": ["title", "doi", "arxiv_id", "url"],
                    "metadata_sources": ["arxiv", "openalex"],
                },
            )
        )
        self.tool_registry.register(
            ToolDescriptor(
                tool_id="fulltext_fetcher",
                display_name="Open Full-text Fetcher",
                description=(
                    "Downloads an open-access paper PDF and extracts page-aware, "
                    "section-aware text for downstream evidence verification."
                ),
                config={
                    "parser": "pymupdf",
                    "default_max_pages": 40,
                    "default_max_pdf_mb": 20,
                },
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

