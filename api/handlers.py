from __future__ import annotations

from dataclasses import asdict
from typing import Any

from product_agent.llm_client import call_openai_text
from product_agent.schemas import (
    ContinueConversationRequest,
    ContinueConversationResponse,
    CreateKnowledgeDocumentRequest,
    CreateConversationRequest,
    CreateMessageRequest,
    CreateResearchTaskRequest,
    FollowUpTaskPreview,
    UpdateToolRequest,
)
from product_agent.services.errors import ConversationNotFoundError, InvalidTaskModeError, TaskNotFoundError
from product_agent.services.text_cleaning import clean_internal_context_items, clean_internal_context_text

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
        knowledge_service,
    ):
        self.conversation_service = conversation_service
        self.message_service = message_service
        self.research_service = research_service
        self.workspace_service = workspace_service
        self.tool_service = tool_service
        self.skill_service = skill_service
        self.knowledge_service = knowledge_service

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

    def delete_conversation(self, conversation_id: str):
        """Delete a conversation and its dependent messages, tasks, and workspaces."""
        result = self.conversation_service.delete_conversation(conversation_id)
        if not result.get("deleted"):
            return fail("conversation_not_found", "Conversation does not exist.")
        return ok(result)


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
        - 检索相关知识库文档
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

        # Retrieve related knowledge from knowledge base
        knowledge_query = f"{conversation.topic} {request.content} {request.focus or ''}"
        knowledge_context = self.knowledge_service.retrieve_for_context(
            knowledge_query, top_k=3, max_chars_per_doc=250,
        )
        display_knowledge_context = clean_internal_context_items(knowledge_context, max_length=180)

        follow_up_task = None
        if request.create_follow_up_task:
            enriched_focus = request.focus
            knowledge_hints = self._extract_knowledge_hints(display_knowledge_context)

            try:
                task = self.research_service.create_follow_up_task(
                    conversation_id=conversation.conversation_id,
                    base_topic=conversation.topic,
                    latest_message_content=request.content,
                    focus=enriched_focus,
                    knowledge_hints=knowledge_hints,
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
            knowledge_context=display_knowledge_context,
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

        # Invalidate conversation workspace cache so next read picks up new data
        self.workspace_service.invalidate_conversation_cache(task.conversation_id)
        display_topic = self._display_topic_for_task_workspace(task=task, workspace=workspace)

        assistant_message = self.message_service.create_assistant_message(
            conversation_id=task.conversation_id,
            content=self._build_task_result_message(task=task, workspace=workspace),
            metadata={
                "kind": "task_result",
                "task_id": workspace.task_id,
                "task_status": "completed",
                "topic": display_topic,
                "alignment_score": workspace.alignment_score,
                "paper_count": len(workspace.papers),
                "gap_count": len(workspace.gaps),
                "idea_count": len(workspace.ideas),
            },
        )

        # Auto-save workspace summary as reusable knowledge
        self._auto_save_workspace_knowledge(task=task, workspace=workspace)

        return ok(
            {
                "task_id": workspace.task_id,
                "topic": display_topic,
                "alignment_score": workspace.alignment_score,
                "trace_keys": list(workspace.trace.keys()),
                "assistant_message_id": assistant_message.message_id if assistant_message else None,
            }
        )

    def _auto_save_workspace_knowledge(self, *, task, workspace) -> None:
        """Extract key findings from workspace and save as reusable knowledge document."""
        try:
            # Build a concise knowledge summary from workspace
            parts: list[str] = []
            if workspace.summary:
                summary = clean_internal_context_text(workspace.summary, max_length=600)
                if summary:
                    parts.append(summary)

            top_papers = workspace.papers[:5]
            if top_papers:
                parts.append("Key papers:")
                for p in top_papers:
                    title = clean_internal_context_text(p.title, max_length=160)
                    source = clean_internal_context_text(p.source, max_length=80)
                    if title:
                        parts.append(f"- {title} ({source})" if source else f"- {title}")

            top_gaps = workspace.gaps[:3]
            if top_gaps:
                parts.append("Research gaps:")
                for g in top_gaps:
                    summary = clean_internal_context_text(g.summary, max_length=120)
                    if summary:
                        parts.append(f"- [{g.severity}] {summary}")

            # Extract tags from taxonomy branches
            taxonomy = workspace.taxonomy or {}
            branches = taxonomy.get("branches", []) if isinstance(taxonomy, dict) else []
            tags = [
                b["name"] for b in branches
                if b.get("evidence_tier") in ("strong", "moderate")
            ][:5]

            content = "\n".join(parts)
            if content.strip():
                self.knowledge_service.save_summary(
                    title=f"[Auto] {workspace.topic[:100]}",
                    content=content,
                    source_task_id=task.task_id,
                    tags=tags if tags else None,
                    index_immediately=True,  # async indexing won't block task completion
                )
        except Exception:
            pass  # knowledge auto-save is best-effort, never block task completion

    def get_workspace(self, task_id: str):
        """获取某次任务的工作台快照。"""
        snapshot = self.workspace_service.get_workspace_snapshot(task_id)
        if snapshot is None:
            return fail("workspace_not_found", "Workspace does not exist.")
        return ok(snapshot.model_dump())

    def get_conversation_workspace(self, conversation_id: str):
        snapshot = self.workspace_service.get_conversation_workspace_snapshot(conversation_id)
        if snapshot is None:
            return fail("conversation_workspace_not_found", "Conversation workspace does not exist.")
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

    def list_knowledge_documents(self):
        documents = self.knowledge_service.list_documents()
        return ok({"items": [self._knowledge_payload(item) for item in documents]})

    def create_knowledge_document(self, request: CreateKnowledgeDocumentRequest):
        document = self.knowledge_service.import_document(
            title=request.title,
            content=request.content,
            tags=request.tags,
            source_url=request.source_url,
            source_task_id=request.source_task_id,
            notes=request.notes,
        )
        return ok(self._knowledge_payload(document))

    def delete_knowledge_document(self, document_id: str):
        deleted = self.knowledge_service.delete_document(document_id)
        if not deleted:
            return fail("knowledge_document_not_found", "Knowledge document does not exist.")
        return ok({"document_id": document_id, "deleted": True})

    def search_knowledge(self, *, q: str = "", by: str = "keyword", limit: int = 10):
        """搜索知识库文档。by='keyword' 使用关键词检索，by='tags' 按标签过滤。"""
        if not q.strip():
            return ok({"items": []})

        if by == "tags":
            tags = [t.strip() for t in q.split(",") if t.strip()]
            docs = self.knowledge_service.retrieve_by_tags(tags, limit=limit)
        else:
            docs = self.knowledge_service.search_by_keyword(q, limit=limit)

        return ok({
            "items": [self._knowledge_payload(doc) for doc in docs],
            "query": q,
            "total": len(docs),
        })

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
    def _knowledge_payload(document) -> dict:
        return {
            "document_id": document.document_id,
            "title": document.title,
            "source_task_id": document.source_task_id,
            "content": document.content,
            "tags": list(document.tags),
            "metadata": dict(document.metadata),
        }

    def _build_task_result_message(self, *, task, workspace) -> str:
        """Build a natural research summary from workspace data.

        Uses LLM when available for richer responses; falls back to
        a detailed template that reads like a research assistant finding,
        not a task log.
        """
        return self._build_natural_assistant_message(task=task, workspace=workspace).strip()

    def _build_natural_assistant_message(self, *, task, workspace) -> str:
        """Generate a natural-language research assistant response.

        Tries LLM first; falls back to a rich template that includes
        specific paper titles, top gaps, and key ideas.
        """
        return self._build_template_assistant_message(task=task, workspace=workspace)

    def _try_llm_assistant_message(self, *, task, workspace) -> str | None:
        """Attempt LLM-powered response. Returns None if unavailable."""
        papers_preview = []
        for p in workspace.papers[:5]:
            papers_preview.append(f"- {p.title} ({p.source})")

        gaps_preview = []
        for g in workspace.gaps[:3]:
            gaps_preview.append(f"[{g.severity}] {g.summary[:150]}")

        ideas_preview = []
        for idea in workspace.ideas[:2]:
            ideas_preview.append(idea.title[:120])

        prompt = (
            f"You are a research assistant. Summarize the following research findings "
            f"in 3-5 natural Chinese sentences. Be concise and informative.\n\n"
            f"Research topic: {task.topic}\n"
            f"Papers found ({len(workspace.papers)}):\n"
            f"{chr(10).join(papers_preview)}\n"
            f"Research gaps ({len(workspace.gaps)}):\n"
            f"{chr(10).join(gaps_preview)}\n"
            f"Ideas ({len(workspace.ideas)}):\n"
            f"{chr(10).join(ideas_preview)}\n"
            f"Alignment score: {workspace.alignment_score:.3f}\n\n"
            f"Start directly with the findings. Do NOT say 'here is a summary'. "
            f"End with: '详细结果可在工作台中查看。'"
        )
        try:
            text = call_openai_text(prompt, temperature=0.5, max_output_tokens=400)
            if text and len(text.strip()) > 30:
                return text.strip()
        except Exception:
            pass
        return None

    def _build_template_assistant_message(self, *, task, workspace) -> str:
        """Template-based, user-facing research summary."""
        evidence = workspace.evidence_status or {}
        insufficient = bool(evidence.get("insufficient", False))
        total_papers = len(workspace.papers)
        real_papers = [p for p in workspace.papers if p.source not in ("seed", "fallback")]
        fallback_count = total_papers - len(real_papers)
        raw_topic = clean_internal_context_text(workspace.topic or task.topic, max_length=300)
        topic = self._display_topic_for_task_workspace(task=task, workspace=workspace)

        lines: list[str] = [
            "\u7814\u7a76\u5206\u6790\u5b8c\u6210",
            "",
            f"\u7814\u7a76\u4e3b\u9898\uff1a{topic}",
            "",
            "\u672c\u8f6e\u6982\u89c8",
            f"- \u68c0\u7d22\u8bba\u6587\uff1a{total_papers} \u7bc7",
            f"- \u7814\u7a76\u7a7a\u767d\uff1a{len(workspace.gaps)} \u6761",
            f"- \u7814\u7a76\u5efa\u8bae\uff1a{len(workspace.ideas)} \u6761",
            f"- \u5bf9\u9f50\u5206\u6570\uff1a{workspace.alignment_score:.2f}",
        ]

        if insufficient:
            lines.append("- \u8bc1\u636e\u72b6\u6001\uff1a\u5f53\u524d\u8bc1\u636e\u504f\u5c11\uff0c\u7ed3\u679c\u66f4\u9002\u5408\u4f5c\u4e3a\u63a2\u7d22\u65b9\u5411")
        elif fallback_count:
            lines.append(f"- \u8bc1\u636e\u72b6\u6001\uff1a\u5305\u542b {fallback_count} \u7bc7\u7cfb\u7edf\u56de\u9000\u8bba\u6587\uff0c\u5efa\u8bae\u7ee7\u7eed\u8865\u5145\u771f\u5b9e\u6587\u732e")

        top_papers = (real_papers or workspace.papers)[:3]
        if top_papers:
            lines.extend(["", "\u4ee3\u8868\u6027\u8bba\u6587"])
            for paper in top_papers:
                title = clean_internal_context_text(paper.title, max_length=180) or paper.paper_id
                source = clean_internal_context_text(paper.source, max_length=60)
                cite = f"\uff08\u5f15\u7528 {paper.citation_count}\uff09" if paper.citation_count > 0 else ""
                source_text = f"\uff0c{source}" if source else ""
                lines.append(f"- {title}{source_text}{cite}")

        if workspace.gaps:
            lines.extend(["", "\u5173\u952e\u7814\u7a76\u7a7a\u767d"])
            for gap in workspace.gaps[:3]:
                summary = clean_internal_context_text(gap.summary, max_length=180)
                if summary:
                    lines.append(f"- {summary}")

        if workspace.ideas:
            lines.extend(["", "\u53ef\u7ee7\u7eed\u63a8\u8fdb\u7684\u9009\u9898"])
            for idea in workspace.ideas[:3]:
                title = clean_internal_context_text(idea.title, max_length=180)
                if raw_topic and raw_topic != topic:
                    title = title.replace(raw_topic, topic)
                title = title.replace(f"{topic};", topic).replace(f"{topic} ;", topic)
                if title:
                    lines.append(f"- {title}")

        lines.extend([
            "",
            "\u4e0b\u4e00\u6b65",
            "- \u5982\u679c\u65b9\u5411\u592a\u5bbd\uff0c\u53ef\u4ee5\u7ee7\u7eed\u8ffd\u95ee\u5e76\u6307\u5b9a\u5e74\u4efd\u3001\u65b9\u6cd5\u6216\u5e94\u7528\u573a\u666f\u3002",
            f"- \u5b8c\u6574 taxonomy\u3001\u6f14\u8fdb\u56fe\u548c\u8bc1\u636e\u660e\u7ec6\u53ef\u5728\u5de5\u4f5c\u53f0\u67e5\u770b\uff08\u4efb\u52a1\uff1a{workspace.task_id}\uff09\u3002",
        ])

        return "\n".join(lines)

    def _display_topic_for_task_workspace(self, *, task, workspace) -> str:
        raw_topic = clean_internal_context_text(workspace.topic or task.topic, max_length=300)
        topic = clean_internal_context_text(raw_topic, max_length=160) or "research topic"
        if self._looks_like_internal_topic(topic):
            conversation = self.conversation_service.get_conversation(task.conversation_id)
            if conversation is not None:
                topic = clean_internal_context_text(conversation.topic, max_length=160) or topic
        return topic

    @staticmethod
    def _looks_like_internal_topic(topic: str) -> bool:
        normalized = topic.lower()
        return any(
            marker in normalized
            for marker in (
                "missing required concepts",
                "missing taxonomy branch",
                "优先关注",
                "关键研究空白",
                "research gaps",
            )
        )

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

    @staticmethod
    def _extract_knowledge_hints(knowledge_context: list[str]) -> list[str]:
        hints: list[str] = []
        seen = set()
        for item in knowledge_context:
            text = str(item or "").strip()
            text = clean_internal_context_text(text, max_length=120)
            if not text:
                continue
            if ":" in text:
                title_part = text.split(":", 1)[0]
            else:
                title_part = text
            title_part = title_part.replace("[Knowledge]", "").strip()
            if "]" in title_part:
                title_part = title_part.split("]", 1)[-1].strip()
            if not title_part:
                continue
            normalized = title_part.lower()
            if normalized in seen:
                continue
            seen.add(normalized)
            hints.append(title_part[:80])
            if len(hints) >= 2:
                break
        return hints
