from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from product_agent.domain import ResearchTask, ResearchWorkspace
from product_agent.repositories import ResearchTaskRepository, WorkspaceRepository
from product_agent.research_agent.pipeline import run_pipeline
from product_agent.services.workspace_mapper import workspace_from_agent_state


class ResearchService:
    """
    编排一次研究任务。

    TODO(iter3-research-service):
    已完成:
    - 能创建任务记录
    - 能调用重构版 Agent pipeline
    - 能生成最小版 ResearchWorkspace

    待实现:
    1. 接入会话上下文摘要
       实现思路:
       - 从 Conversation / Message 仓储中读取最近 N 轮消息
       - 用摘要器压缩历史消息，生成 conversation_context
       - 将 conversation_context 作为扩展输入传给 Agent pipeline

    2. 接入共享知识与 RAG
       实现思路:
       - 先通过 KnowledgeService 获取与 topic 相关的知识文档摘要
       - 将检索结果组织成 retrieved_knowledge
       - 把 retrieved_knowledge 注入 planner / synthesizer 的上下文
       - 当前阶段先保留接口，不在本类直接做向量检索实现

    3. 接入工具开关配置
       实现思路:
       - 读取任务级 enabled_tools
       - 在运行 pipeline 前构造 tool execution policy
       - 禁止未启用工具被自动调用

    4. 将旧版 state 转成更稳定的 Workspace DTO
       实现思路:
       - 目前 papers / gaps / ideas 仍未完整结构化
       - 需要增加 dedicated mapper，把旧版 state 明确映射到前端友好的 schema
    """

    def __init__(
        self,
        *,
        task_repository: ResearchTaskRepository,
        workspace_repository: WorkspaceRepository,
    ) -> None:
        self.task_repository = task_repository
        self.workspace_repository = workspace_repository

    def create_task(self, *, conversation_id: str, topic: str, mode: str = "default") -> ResearchTask:
        """
        创建一条新的研究分析任务记录。

        调用者:
        - ProductApiHandlers.create_research_task

        参数:
        - conversation_id: 该任务所属会话
        - topic: 本次任务要分析的主题
        - mode: 运行模式，预留 default / fast / balanced

        返回:
        - ResearchTask: 已持久化的任务对象

        待补充:
        - trigger_message_id
        - use_shared_knowledge
        - enabled_tools
        - task-level skill selection

        副作用:
        - 调用 task_repository.create 持久化任务

        约束:
        - conversation_id 必须对应有效会话
        - mode 必须属于受支持集合
        """
        task = ResearchTask(
            task_id=f"task_{uuid4().hex[:12]}",
            conversation_id=conversation_id,
            topic=topic,
            mode=mode,
            status="created",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        return self.task_repository.create(task)

    def run_task(self, task: ResearchTask) -> ResearchWorkspace:
        """
        运行一条研究任务，并把 Agent 结果投影为产品工作台数据。

        调用者:
        - ProductApiHandlers.run_research_task

        参数:
        - task: 已创建的 ResearchTask

        返回:
        - ResearchWorkspace: 可供前端工作台消费的任务快照

        TODO(iter3-workspace-projection):
        1. 把 paper / gaps / ideas 全量映射为结构化 DTO，而不是先留空
        2. 为工作台提供更适合前端直接渲染的 summary / sections
        3. 接入 trace 压缩，避免大状态直接推给前端
        4. 增加 context_inputs 字段，记录本轮使用过哪些上下文和知识来源

        当前副作用:
        - 调用 `product_agent.research_agent.pipeline.run_pipeline`
        - 调用 workspace_repository.save 保存工作台快照
        - 更新 task 状态为 completed

        后续约束:
        - 这里应逐步成为“产品态 -> Agent态 -> 产品态”的唯一编排入口
        - 前端不应直接调用 Agent pipeline
        """
        state = run_pipeline(task.topic, show_progress=False)
        workspace: ResearchWorkspace = workspace_from_agent_state(task_id=task.task_id, topic=task.topic, state=state)
        self.workspace_repository.save(workspace)
        task.status = "completed"
        task.updated_at = datetime.now(UTC)
        self.task_repository.update(task)
        return workspace
