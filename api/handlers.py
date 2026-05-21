from __future__ import annotations

from dataclasses import asdict

from product_agent.schemas import (
    ContinueConversationRequest,
    ContinueConversationResponse,
    CreateConversationRequest,
    CreateMessageRequest,
    CreateResearchTaskRequest,
    FollowUpTaskPreview,
    UpdateToolRequest,
)
from product_agent.services.errors import ConversationNotFoundError, InvalidTaskModeError, TaskNotFoundError

from .response import fail, ok


class ProductApiHandlers:
    """
    不绑定具体 Web 框架的 API handler 集合。

    合同约束：
    - handler 只负责接收输入、调 service、返回统一响应
    - handler 不直接访问 repository
    - handler 不直接调用外部工具
    - 所有输出统一包装成 ApiResponse
    """

    def __init__(
        self,
        *,
        conversation_service,
        message_service,
        research_service,
        workspace_service,
        tool_service,
        skill_service,
    ):
        self.conversation_service = conversation_service
        self.message_service = message_service
        self.research_service = research_service
        self.workspace_service = workspace_service
        self.tool_service = tool_service
        self.skill_service = skill_service

    def create_conversation(self, request: CreateConversationRequest):
        """创建新会话。"""
        conversation = self.conversation_service.create_conversation(topic=request.topic, title=request.title)
        return ok(
            {
                "conversation_id": conversation.conversation_id,
                "topic": conversation.topic,
                "title": conversation.title,
            }
        )

    def list_conversations(self, *, limit: int | None = None):
        """列出历史会话，供历史页和会话选择器使用。"""
        items = self.conversation_service.list_conversations(limit=limit)
        return ok({"items": [self._conversation_payload(item) for item in items]})

    def get_conversation(self, conversation_id: str):
        """获取单个会话详情。"""
        conversation = self.conversation_service.get_conversation(conversation_id)
        if conversation is None:
            return fail("conversation_not_found", "Conversation does not exist.")

        messages = self.message_service.list_messages(conversation_id)
        message_count = len(messages or [])
        payload = self._conversation_payload(conversation)
        payload["message_count"] = message_count
        return ok(payload)

    def list_messages(self, conversation_id: str):
        """列出某个会话的消息。"""
        messages = self.message_service.list_messages(conversation_id)
        if messages is None:
            return fail("conversation_not_found", "Conversation does not exist.")
        return ok(
            {
                "conversation_id": conversation_id,
                "items": [self._message_payload(item) for item in messages],
            }
        )

    def create_message(self, conversation_id: str, request: CreateMessageRequest):
        """在指定会话中创建一条消息。"""
        message = self.message_service.create_message(
            conversation_id=conversation_id,
            role=request.role,
            content=request.content,
            metadata=request.metadata,
        )
        if message is None:
            return fail("conversation_not_found", "Conversation does not exist.")
        return ok(self._message_payload(message))

    def continue_conversation(self, request: ContinueConversationRequest):
        """
        在已有会话上继续追问。

        当前版本已经会：
        - 写入用户消息
        - 读取最近上下文预览
        - 可选创建一条 follow-up 研究任务记录
        """
        conversation = self.conversation_service.get_conversation(request.conversation_id)
        if conversation is None:
            return fail("conversation_not_found", "Conversation does not exist.")

        message = self.message_service.create_message(
            conversation_id=request.conversation_id,
            role="user",
            content=request.content,
            metadata={"focus": request.focus or ""},
        )
        if message is None:
            return fail("conversation_not_found", "Conversation does not exist.")

        recent_context = self.message_service.get_recent_context(request.conversation_id, limit=4) or []
        context_preview = [f"{item.role}: {item.content[:80]}" for item in recent_context]

        follow_up_task = None
        if request.create_follow_up_task:
            try:
                task = self.research_service.create_follow_up_task(
                    conversation_id=conversation.conversation_id,
                    base_topic=conversation.topic,
                    latest_message_content=request.content,
                    focus=request.focus,
                    mode=request.mode,
                    trigger_message_id=message.message_id,
                )
            except InvalidTaskModeError as error:
                return fail("task_invalid_mode", str(error))

            follow_up_task = FollowUpTaskPreview(
                task_id=task.task_id,
                topic=task.topic,
                status=task.status,
                trigger_message_id=task.trigger_message_id,
            )

        response = ContinueConversationResponse(
            conversation_id=conversation.conversation_id,
            next_focus=request.focus or "follow_up",
            message=request.content,
            message_id=message.message_id,
            context_preview=context_preview,
            follow_up_task=follow_up_task,
        )
        return ok(response.model_dump())

    def create_research_task(self, request: CreateResearchTaskRequest):
        """创建研究任务，但不立即运行。"""
        try:
            task = self.research_service.create_task(
                conversation_id=request.conversation_id,
                topic=request.topic,
                mode=request.mode,
            )
        except ConversationNotFoundError:
            return fail("conversation_not_found", "Conversation does not exist.")
        except InvalidTaskModeError as error:
            return fail("task_invalid_mode", str(error))

        return ok(
            {
                "task_id": task.task_id,
                "conversation_id": task.conversation_id,
                "status": task.status,
            }
        )

    def list_research_tasks(self, *, conversation_id: str | None = None, limit: int | None = None):
        """列出历史研究任务，供历史页或会话详情页使用。"""
        tasks = self.research_service.list_tasks(conversation_id=conversation_id, limit=limit)
        return ok({"items": [self._task_payload(item) for item in tasks]})

    def get_research_task(self, task_id: str):
        """获取单个研究任务的状态与元数据。"""
        try:
            task = self.research_service.get_task(task_id)
        except TaskNotFoundError:
            return fail("task_not_found", "Research task does not exist.")
        return ok(self._task_payload(task))

    def run_research_task(self, task_id: str):
        """运行已创建的研究任务。"""
        try:
            task = self.research_service.get_task(task_id)
        except TaskNotFoundError:
            return fail("task_not_found", "Research task does not exist.")

        try:
            workspace = self.research_service.run_task(task)
        except Exception as error:
            self.message_service.create_assistant_message(
                conversation_id=task.conversation_id,
                content=self._build_task_failure_message(task=task, error_message=str(error)),
                metadata={
                    "kind": "task_result",
                    "task_id": task.task_id,
                    "task_status": "failed",
                    "topic": task.topic,
                },
            )
            return fail("task_run_failed", str(error))

        assistant_message = self.message_service.create_assistant_message(
            conversation_id=task.conversation_id,
            content=self._build_task_result_message(task=task, workspace=workspace),
            metadata={
                "kind": "task_result",
                "task_id": workspace.task_id,
                "task_status": "completed",
                "topic": workspace.topic,
                "alignment_score": workspace.alignment_score,
                "paper_count": len(workspace.papers),
                "gap_count": len(workspace.gaps),
                "idea_count": len(workspace.ideas),
            },
        )

        return ok(
            {
                "task_id": workspace.task_id,
                "topic": workspace.topic,
                "alignment_score": workspace.alignment_score,
                "trace_keys": list(workspace.trace.keys()),
                "assistant_message_id": assistant_message.message_id if assistant_message else None,
            }
        )

    def get_workspace(self, task_id: str):
        """获取某次任务的工作台快照。"""
        snapshot = self.workspace_service.get_workspace_snapshot(task_id)
        if snapshot is None:
            return fail("workspace_not_found", "Workspace does not exist.")
        return ok(snapshot.model_dump())

    def list_tools(self):
        """列出当前已注册工具及其开关状态。"""
        tools = self.tool_service.list_tools()
        return ok([asdict(tool) for tool in tools])

    def update_tool(self, tool_id: str, request: UpdateToolRequest):
        """更新某个工具的启用状态与配置。"""
        descriptor = self.tool_service.update_tool_enabled(tool_id, request.enabled)
        if descriptor is None:
            return fail("tool_not_found", "Tool does not exist.")
        descriptor.config = request.config
        return ok(asdict(descriptor))

    def list_skills(self):
        """列出当前已注册 skill。"""
        skills = self.skill_service.list_skills()
        return ok([asdict(skill) for skill in skills])

    @staticmethod
    def _message_payload(message) -> dict:
        return {
            "message_id": message.message_id,
            "conversation_id": message.conversation_id,
            "role": message.role,
            "content": message.content,
            "metadata": message.metadata,
            "created_at": message.created_at.isoformat(),
        }

    @staticmethod
    def _conversation_payload(conversation) -> dict:
        return {
            "conversation_id": conversation.conversation_id,
            "topic": conversation.topic,
            "title": conversation.title,
            "status": conversation.status,
            "latest_task_id": conversation.latest_task_id,
            "created_at": conversation.created_at.isoformat(),
            "updated_at": conversation.updated_at.isoformat(),
        }

    @staticmethod
    def _task_payload(task) -> dict:
        return {
            "task_id": task.task_id,
            "conversation_id": task.conversation_id,
            "topic": task.topic,
            "status": task.status,
            "mode": task.mode,
            "trigger_message_id": task.trigger_message_id,
            "created_at": task.created_at.isoformat(),
            "updated_at": task.updated_at.isoformat(),
        }

    @staticmethod
    def _build_task_result_message(*, task, workspace) -> str:
        summary = " ".join((workspace.summary or "").split())
        if len(summary) > 220:
            summary = f"{summary[:217]}..."

        lines = [
            f"已完成本轮研究任务：{task.topic}",
            f"- 论文数：{len(workspace.papers)}",
            f"- 研究空白：{len(workspace.gaps)}",
            f"- 研究建议：{len(workspace.ideas)}",
            f"- 对齐分数：{workspace.alignment_score:.3f}",
        ]
        if summary:
            lines.append(f"- 摘要：{summary}")
        lines.append(f"- 工作台任务：{workspace.task_id}")
        return "\n".join(lines)

    @staticmethod
    def _build_task_failure_message(*, task, error_message: str) -> str:
        compact_error = " ".join((error_message or "").split())
        if len(compact_error) > 220:
            compact_error = f"{compact_error[:217]}..."
        return "\n".join(
            [
                f"本轮研究任务运行失败：{task.topic}",
                f"- 任务编号：{task.task_id}",
                f"- 错误信息：{compact_error or '未知错误'}",
                "- 建议：可以调整追问范围、切换模式，或稍后重试。",
            ]
        )
