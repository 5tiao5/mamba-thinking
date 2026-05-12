from __future__ import annotations

from fastapi import FastAPI, Path
from fastapi.middleware.cors import CORSMiddleware

from product_agent.app_container import AppContainer
from product_agent.schemas import (
    ContinueConversationRequest,
    CreateConversationRequest,
    CreateResearchTaskRequest,
    UpdateToolRequest,
)

from .handlers import ProductApiHandlers


container = AppContainer()
handlers = ProductApiHandlers(
    conversation_service=container.conversation_service,
    research_service=container.research_service,
    workspace_service=container.workspace_service,
    tool_service=container.tool_service,
    skill_service=container.skill_service,
)

app = FastAPI(
    title="Product Agent API",
    version="0.1.0",
    description="迭代三科研调研助手后端骨架。当前重点是冻结接口契约与模块边界。",
)

# 开发期默认启动方式:
# uvicorn product_agent.api.fastapi_app:app --reload
#
# 默认访问地址:
# - API: http://127.0.0.1:8000
# - Docs: http://127.0.0.1:8000/docs
# - ReDoc: http://127.0.0.1:8000/redoc

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
    """健康检查接口。"""

    return {"status": "ok"}


@app.post("/conversations")
def create_conversation(request: CreateConversationRequest):
    """创建一个新的研究会话。"""

    return handlers.create_conversation(request).model_dump()


@app.post("/conversations/continue")
def continue_conversation(request: ContinueConversationRequest):
    """在已有会话基础上继续追问。"""

    return handlers.continue_conversation(request).model_dump()


@app.post("/research/tasks")
def create_research_task(request: CreateResearchTaskRequest):
    """创建一条研究任务记录。"""

    return handlers.create_research_task(request).model_dump()


@app.post("/research/tasks/{task_id}/run")
def run_research_task(task_id: str = Path(..., description="研究任务 ID")):
    """运行已创建的研究任务。"""

    return handlers.run_research_task(task_id).model_dump()


@app.get("/research/tasks/{task_id}/workspace")
def get_workspace(task_id: str = Path(..., description="研究任务 ID")):
    """获取任务工作台快照。"""

    return handlers.get_workspace(task_id).model_dump()


@app.get("/tools")
def list_tools():
    """列出所有已注册工具。"""

    return handlers.list_tools().model_dump()


@app.patch("/tools/{tool_id}")
def update_tool(
    request: UpdateToolRequest,
    tool_id: str = Path(..., description="工具 ID"),
):
    """更新指定工具的开关与配置。"""

    return handlers.update_tool(tool_id, request).model_dump()


@app.get("/skills")
def list_skills():
    """列出所有已注册 skill。"""

    return handlers.list_skills().model_dump()
