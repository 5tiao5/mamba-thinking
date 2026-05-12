from __future__ import annotations

from dataclasses import asdict

from product_agent.schemas import (
    ContinueConversationRequest,
    CreateConversationRequest,
    CreateResearchTaskRequest,
    UpdateToolRequest,
)

from .response import fail, ok


class ProductApiHandlers:
    """
    不绑定具体 Web 框架的 API handler 集合。

    TODO(iter3-api-integration):
    1. 未来可由 FastAPI / Flask / Django 等框架路由直接调用这些方法
    2. 这里先冻结输入输出契约，避免前后端字段随意漂移
    3. 当前 handler 不应承担复杂业务逻辑，复杂逻辑一律下沉到 service 层

    合同约束:
    - handler 只负责接收输入、调用 service、返回统一响应
    - handler 不直接访问数据库
    - handler 不直接调用外部工具
    - 所有输出必须包装为 ApiResponse
    """

    def __init__(self, *, conversation_service, research_service, workspace_service, tool_service, skill_service):
        self.conversation_service = conversation_service
        self.research_service = research_service
        self.workspace_service = workspace_service
        self.tool_service = tool_service
        self.skill_service = skill_service

    def create_conversation(self, request: CreateConversationRequest):
        """
        创建新会话。

        调用链:
        - FastAPI route -> ProductApiHandlers.create_conversation -> ConversationService.create_conversation

        输入:
        - request.topic: 主题
        - request.title: 可选标题

        输出:
        - ApiResponse[data]:
          - conversation_id: str
          - topic: str
          - title: str

        错误约定:
        - 当前版本默认不抛业务错误
        - 后续如果 topic 非法，应返回 `conversation_invalid_topic`
        """
        conversation = self.conversation_service.create_conversation(topic=request.topic, title=request.title)
        return ok(
            {
                "conversation_id": conversation.conversation_id,
                "topic": conversation.topic,
                "title": conversation.title,
            }
        )

    def continue_conversation(self, request: ContinueConversationRequest):
        """
        在已有会话上继续追问。

        当前版本:
        - 只冻结接口契约
        - 不真正驱动新任务

        后续实现思路:
        - 根据 conversation_id 读取历史消息
        - 调用 ConversationService 生成 context summary
        - 把 content + context summary 交给 ResearchService
        - 若需要，自动创建 follow-up task

        输出:
        - conversation_id: str
        - next_focus: str
        - message: str

        错误约定:
        - 会话不存在 -> `conversation_not_found`

        组员实现提示:
        - 后续这里应该成为“多轮对话主入口”
        - 不建议直接在这里写上下文摘要逻辑，应下沉到 ConversationService 或专门的 ContextService
        """
        conversation = self.conversation_service.get_conversation(request.conversation_id)
        if conversation is None:
            return fail("conversation_not_found", "Conversation does not exist.")
        return ok(
            {
                "conversation_id": conversation.conversation_id,
                "next_focus": request.focus or "follow_up",
                "message": request.content,
            }
        )

    def create_research_task(self, request: CreateResearchTaskRequest):
        """
        创建研究任务，但不立即运行。

        输入:
        - conversation_id: str
        - topic: str
        - mode: str
        - use_shared_knowledge: bool
        - enabled_tools: list[str]

        输出:
        - task_id: str
        - conversation_id: str
        - status: str

        错误约定:
        - conversation 不存在 -> `conversation_not_found`
        - mode 非法 -> `task_invalid_mode`

        组员实现提示:
        - 后续应校验 conversation_id 是否存在
        - 后续应把 enabled_tools / use_shared_knowledge 真正写入任务配置
        """
        task = self.research_service.create_task(
            conversation_id=request.conversation_id,
            topic=request.topic,
            mode=request.mode,
        )
        return ok(
            {
                "task_id": task.task_id,
                "conversation_id": task.conversation_id,
                "status": task.status,
            }
        )

    def run_research_task(self, task_id: str):
        """
        运行已创建的研究任务。

        输入:
        - task_id: str

        输出:
        - task_id: str
        - topic: str
        - alignment_score: float
        - trace_keys: list[str]

        错误约定:
        - task 不存在 -> `task_not_found`

        组员实现提示:
        - 后续需要支持异步运行 / 后台任务
        - 后续返回值可以加 `workspace_ready: bool`
        """
        task = self.research_service.task_repository.get(task_id)
        if task is None:
            return fail("task_not_found", "Research task does not exist.")
        workspace = self.research_service.run_task(task)
        return ok(
            {
                "task_id": workspace.task_id,
                "topic": workspace.topic,
                "alignment_score": workspace.alignment_score,
                "trace_keys": list(workspace.trace.keys()),
            }
        )

    def get_workspace(self, task_id: str):
        """
        获取某次任务的工作台快照。

        输出:
        - task_id
        - topic
        - summary
        - taxonomy
        - graph_edges
        - alignment_score

        错误约定:
        - workspace 不存在 -> `workspace_not_found`

        组员实现提示:
        - 后续前端主要依赖这个接口渲染工作台
        - 返回结构要尽量稳定，不要直接暴露旧版 Agent 内部 state
        """
        workspace = self.workspace_service.get_workspace(task_id)
        if workspace is None:
            return fail("workspace_not_found", "Workspace does not exist.")
        return ok(
            {
                "task_id": workspace.task_id,
                "topic": workspace.topic,
                "summary": workspace.summary,
                "taxonomy": workspace.taxonomy,
                "graph_edges": workspace.graph_edges,
                "alignment_score": workspace.alignment_score,
            }
        )

    def list_tools(self):
        """
        列出当前已注册工具及其开关状态。

        组员实现提示:
        - 前端设置页优先对接这个接口
        - 返回结构要保持平铺和可读，避免嵌套过深
        """
        tools = self.tool_service.list_tools()
        return ok([asdict(tool) for tool in tools])

    def update_tool(self, tool_id: str, request: UpdateToolRequest):
        """
        更新某个工具的启用状态与配置。

        输入:
        - tool_id: str
        - request.enabled: bool
        - request.config: dict

        错误约定:
        - tool 不存在 -> `tool_not_found`

        组员实现提示:
        - 当前只更新 registry 内存状态
        - 后续需要接持久化
        """
        descriptor = self.tool_service.update_tool_enabled(tool_id, request.enabled)
        if descriptor is None:
            return fail("tool_not_found", "Tool does not exist.")
        descriptor.config = request.config
        return ok(asdict(descriptor))

    def list_skills(self):
        """
        列出当前已注册 skill。

        组员实现提示:
        - 前端可先把它作为只读页面
        - 后续再支持启用/禁用和动态加载
        """
        skills = self.skill_service.list_skills()
        return ok([asdict(skill) for skill in skills])
