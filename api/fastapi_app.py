from __future__ import annotations

from fastapi import FastAPI, Path, Query
from fastapi.middleware.cors import CORSMiddleware

from product_agent.env_loader import load_product_agent_dotenv

load_product_agent_dotenv()

from product_agent.app_container import AppContainer
from product_agent.schemas import (
    ContinueConversationRequest,
    CreateKnowledgeDocumentRequest,
    CreateConversationRequest,
    CreateMessageRequest,
    CreateResearchTaskRequest,
    CreateSkillRequest,
    ImportPaperCandidateRequest,
    SearchPaperCandidatesRequest,
    UpdateSkillRequest,
    UpdateToolRequest,
)

from .handlers import ProductApiHandlers


def create_app(container: AppContainer | None = None) -> FastAPI:
    """
    创建 FastAPI 应用实例。

    说明：
    - 避免在模块导入时把依赖装配彻底固化死
    - 方便后续测试注入、不同环境切换和应用生命周期管理
    """
    active_container = container or AppContainer()
    handlers = ProductApiHandlers(
        conversation_service=active_container.conversation_service,
        message_service=active_container.message_service,
        research_service=active_container.research_service,
        workspace_service=active_container.workspace_service,
        tool_service=active_container.tool_service,
        skill_service=active_container.skill_service,
        knowledge_service=active_container.knowledge_service,
    )

    app = FastAPI(
        title="Product Agent API",
        version="0.1.0",
        description="迭代三科研调研助手后端骨架，当前重点是冻结接口契约与模块边界。",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def healthcheck() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/conversations")
    def create_conversation(request: CreateConversationRequest):
        return handlers.create_conversation(request).model_dump()

    @app.get("/conversations")
    def list_conversations(limit: int | None = Query(default=None, ge=1, le=100, description="最多返回多少条会话")):
        return handlers.list_conversations(limit=limit).model_dump()

    @app.get("/conversations/{conversation_id}")
    def get_conversation(conversation_id: str = Path(..., description="会话 ID")):
        return handlers.get_conversation(conversation_id).model_dump()

    @app.delete("/conversations/{conversation_id}")
    def delete_conversation(conversation_id: str = Path(..., description="会话 ID")):
        return handlers.delete_conversation(conversation_id).model_dump()

    @app.get("/conversations/{conversation_id}/workspace")
    def get_conversation_workspace(conversation_id: str = Path(..., description="浼氳瘽 ID")):
        return handlers.get_conversation_workspace(conversation_id).model_dump()

    @app.get("/conversations/{conversation_id}/messages")
    def list_messages(conversation_id: str = Path(..., description="会话 ID")):
        return handlers.list_messages(conversation_id).model_dump()

    @app.post("/conversations/{conversation_id}/messages")
    def create_message(
        request: CreateMessageRequest,
        conversation_id: str = Path(..., description="会话 ID"),
    ):
        return handlers.create_message(conversation_id, request).model_dump()

    @app.post("/conversations/continue")
    def continue_conversation(request: ContinueConversationRequest):
        return handlers.continue_conversation(request).model_dump()

    @app.post("/research/tasks")
    def create_research_task(request: CreateResearchTaskRequest):
        return handlers.create_research_task(request).model_dump()

    @app.get("/research/tasks")
    def list_research_tasks(
        conversation_id: str | None = Query(default=None, description="按会话 ID 过滤任务"),
        limit: int | None = Query(default=None, ge=1, le=100, description="最多返回多少条任务"),
    ):
        return handlers.list_research_tasks(conversation_id=conversation_id, limit=limit).model_dump()

    @app.get("/research/tasks/{task_id}")
    def get_research_task(task_id: str = Path(..., description="研究任务 ID")):
        return handlers.get_research_task(task_id).model_dump()

    @app.post("/research/tasks/{task_id}/run")
    def run_research_task(task_id: str = Path(..., description="研究任务 ID")):
        return handlers.run_research_task(task_id).model_dump()

    @app.get("/research/tasks/{task_id}/workspace")
    def get_workspace(task_id: str = Path(..., description="研究任务 ID")):
        return handlers.get_workspace(task_id).model_dump()

    @app.get("/tools")
    def list_tools():
        return handlers.list_tools().model_dump()

    @app.patch("/tools/{tool_id}")
    def update_tool(
        request: UpdateToolRequest,
        tool_id: str = Path(..., description="工具 ID"),
    ):
        return handlers.update_tool(tool_id, request).model_dump()

    @app.get("/skills")
    def list_skills():
        return handlers.list_skills().model_dump()

    @app.post("/skills")
    def create_skill(request: CreateSkillRequest):
        return handlers.create_skill(request).model_dump()

    @app.patch("/skills/{skill_id}")
    def update_skill(
        request: UpdateSkillRequest,
        skill_id: str = Path(..., description="Skill ID"),
    ):
        return handlers.update_skill(skill_id, request).model_dump()

    @app.delete("/skills/{skill_id}")
    def delete_skill(skill_id: str = Path(..., description="Skill ID")):
        return handlers.delete_skill(skill_id).model_dump()

    @app.get("/knowledge/documents")
    def list_knowledge_documents():
        return handlers.list_knowledge_documents().model_dump()

    @app.post("/knowledge/documents")
    def create_knowledge_document(request: CreateKnowledgeDocumentRequest):
        return handlers.create_knowledge_document(request).model_dump()

    @app.post("/knowledge/paper-candidates")
    def search_paper_candidates(request: SearchPaperCandidatesRequest):
        return handlers.search_paper_candidates(request).model_dump()

    @app.post("/knowledge/paper-candidates/import")
    def import_paper_candidate(request: ImportPaperCandidateRequest):
        return handlers.import_paper_candidate(request).model_dump()

    @app.delete("/knowledge/documents/{document_id}")
    def delete_knowledge_document(document_id: str = Path(..., description="知识文档 ID")):
        return handlers.delete_knowledge_document(document_id).model_dump()

    @app.get("/knowledge/search")
    def search_knowledge(
        q: str = Query(default="", description="搜索关键词或标签（逗号分隔）"),
        by: str = Query(default="keyword", description="检索方式: keyword 或 tags"),
        limit: int = Query(default=10, ge=1, le=50, description="返回数量上限"),
    ):
        return handlers.search_knowledge(q=q, by=by, limit=limit).model_dump()

    return app


app = create_app()

