from __future__ import annotations

from dataclasses import asdict
from typing import Any

from product_agent.llm_client import call_openai_text
from product_agent.schemas import (
    BatchPdfImportResponse,
    ContinueConversationRequest,
    ContinueConversationResponse,
    CreateKnowledgeDocumentRequest,
    CreateConversationRequest,
    CreateMessageRequest,
    CreateResearchTaskRequest,
    CreateSkillRequest,
    FollowUpTaskPreview,
    ImportPaperCandidateRequest,
    ListPaperImportCandidatesResponse,
    ListResearchPapersResponse,
    PaperImportCandidateView,
    PdfImportItemView,
    ResearchPaperView,
    SearchPaperCandidatesRequest,
    UpdateResearchPaperRequest,
    UpdateSkillRequest,
    UpdateToolRequest,
)
from product_agent.services.errors import ConversationNotFoundError, InvalidTaskModeError, TaskNotFoundError
from product_agent.services.research_paper_service import ResearchPaperServiceError
from product_agent.services.skill_service import SkillServiceError
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
        research_paper_service,
        pdf_import_service=None,
    ):
        self.conversation_service = conversation_service
        self.message_service = message_service
        self.research_service = research_service
        self.workspace_service = workspace_service
        self.tool_service = tool_service
        self.skill_service = skill_service
        self.knowledge_service = knowledge_service
        self.research_paper_service = research_paper_service
        self.pdf_import_service = pdf_import_service

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

        knowledge_scope = request.resolve_knowledge_scope()
        message = self.message_service.create_message(
            conversation_id=request.conversation_id,
            role="user",
            content=request.content,
            metadata={
                "focus": request.focus or "",
                "knowledge_scope": knowledge_scope,
                "research_mode": request.research_mode,
            },
        )
        if message is None:
            return fail("conversation_not_found", "Conversation does not exist.")

        recent_context = self.message_service.get_recent_context(request.conversation_id, limit=4) or []
        context_preview = [f"{item.role}: {item.content[:80]}" for item in recent_context]

        # Retrieve related knowledge from knowledge base
        knowledge_query = f"{conversation.topic} {request.content} {request.focus or ''}"
        knowledge_hits = self.knowledge_service.retrieve_hits_for_context(
            knowledge_query,
            top_k=3,
            max_chars_per_doc=250,
            knowledge_scope=knowledge_scope,
            conversation_id=request.conversation_id,
        )
        if request.research_mode == "search_only":
            imported_document_ids = {
                paper.document_id
                for paper in self.research_paper_service.list_papers(
                    request.conversation_id
                )
                if paper.document_id
            }
            knowledge_hits = [
                hit
                for hit in knowledge_hits
                if hit.document_id not in imported_document_ids
            ]
        knowledge_context = [
            self.knowledge_service.format_hit_for_context(hit)
            for hit in knowledge_hits
        ]
        display_knowledge_context = clean_internal_context_items(knowledge_context, max_length=180)
        workspace_context = self.workspace_service.get_conversation_workspace_hints(request.conversation_id)

        follow_up_task = None
        if request.create_follow_up_task:
            # 校验 selected_skill_ids
            if request.selected_skill_ids:
                skill_errors = self.skill_service.validate_skills_for_task(request.selected_skill_ids)
                if skill_errors:
                    return fail("skill_invalid", "; ".join(skill_errors))

            enriched_focus = request.focus
            knowledge_hints = self._extract_knowledge_hints(display_knowledge_context)

            try:
                task = self.research_service.create_follow_up_task(
                    conversation_id=conversation.conversation_id,
                    base_topic=conversation.topic,
                    latest_message_content=request.content,
                    focus=enriched_focus,
                    knowledge_hints=knowledge_hints,
                    workspace_hints=workspace_context,
                    mode=request.mode,
                    knowledge_scope=knowledge_scope,
                    research_mode=request.research_mode,
                    trigger_message_id=message.message_id,
                    selected_skill_ids=request.selected_skill_ids,
                )
            except InvalidTaskModeError as error:
                return fail("task_invalid_mode", str(error))

            follow_up_task = FollowUpTaskPreview(
                task_id=task.task_id,
                topic=task.topic,
                status=task.status,
                trigger_message_id=task.trigger_message_id,
                research_mode=task.research_mode,
            )

        response = ContinueConversationResponse(
            conversation_id=conversation.conversation_id,
            next_focus=request.focus or "follow_up",
            message=request.content,
            message_id=message.message_id,
            context_preview=context_preview,
            knowledge_scope_applied=knowledge_scope,
            research_mode_applied=request.research_mode,
            knowledge_context=display_knowledge_context,
            knowledge_hits=[self._knowledge_hit_payload(hit) for hit in knowledge_hits],
            workspace_context=workspace_context,
            follow_up_task=follow_up_task,
        )
        return ok(response.model_dump())

    def create_research_task(self, request: CreateResearchTaskRequest):
        """创建研究任务，但不立即运行。"""
        knowledge_scope = request.resolve_knowledge_scope()

        # 校验 selected_skill_ids
        if request.selected_skill_ids:
            skill_errors = self.skill_service.validate_skills_for_task(request.selected_skill_ids)
            if skill_errors:
                return fail("skill_invalid", "; ".join(skill_errors))

        try:
            task = self.research_service.create_task(
                conversation_id=request.conversation_id,
                topic=request.topic,
                mode=request.mode,
                knowledge_scope=knowledge_scope,
                research_mode=request.research_mode,
                selected_skill_ids=request.selected_skill_ids,
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
                "knowledge_scope": task.knowledge_scope,
                "research_mode": task.research_mode,
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
        workspace_snapshot = self.workspace_service.get_workspace_snapshot(workspace.task_id)
        source_trace_payload = self._workspace_source_trace_payload(workspace_snapshot)
        inherited_context_payload = self._workspace_inherited_context_payload(workspace_snapshot)

        assistant_message = self.message_service.create_assistant_message(
            conversation_id=task.conversation_id,
            content=self._build_task_result_message(task=task, workspace=workspace),
            metadata={
                "kind": "task_result",
                "task_id": workspace.task_id,
                "task_status": task.status,
                "topic": display_topic,
                "alignment_score": workspace.alignment_score,
                "paper_count": len(workspace.papers),
                "gap_count": len(workspace.gaps),
                "idea_count": len(workspace.ideas),
                "knowledge_scope": task.knowledge_scope,
                "source_trace": source_trace_payload,
                "inherited_context": inherited_context_payload,
            },
        )

        # Auto-save workspace summary as reusable knowledge
        if task.status in {"completed", "degraded"}:
            self._auto_save_workspace_knowledge(task=task, workspace=workspace)

        return ok(
            {
                "task_id": workspace.task_id,
                "task_status": task.status,
                "topic": display_topic,
                "alignment_score": workspace.alignment_score,
                "trace_keys": list(workspace.trace.keys()),
                "assistant_message_id": assistant_message.message_id if assistant_message else None,
                "source_trace": source_trace_payload,
                "inherited_context": inherited_context_payload,
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
                    conversation_id=task.conversation_id,
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
        return ok([
            {
                "skill_id": s.skill_id,
                "display_name": s.display_name,
                "description": s.description,
                "enabled": s.enabled,
                "required_tools": list(s.required_tools),
                "created_at": s.created_at.isoformat() if getattr(s, "created_at", None) else None,
                "updated_at": s.updated_at.isoformat() if getattr(s, "updated_at", None) else None,
            }
            for s in skills
        ])

    def create_skill(self, request: CreateSkillRequest):
        """创建新的 skill。"""
        try:
            descriptor = self.skill_service.create_skill(
                skill_id=request.skill_id,
                display_name=request.display_name,
                description=request.description,
                required_tools=request.required_tools,
                enabled=request.enabled,
            )
        except SkillServiceError as error:
            return fail("skill_invalid", str(error))

        return ok({
            "skill_id": descriptor.skill_id,
            "display_name": descriptor.display_name,
            "description": descriptor.description,
            "enabled": descriptor.enabled,
            "required_tools": list(descriptor.required_tools),
            "created_at": descriptor.created_at.isoformat() if getattr(descriptor, "created_at", None) else None,
            "updated_at": descriptor.updated_at.isoformat() if getattr(descriptor, "updated_at", None) else None,
        })

    def update_skill(self, skill_id: str, request: UpdateSkillRequest):
        """更新已有 skill。"""
        try:
            descriptor = self.skill_service.update_skill(
                skill_id=skill_id,
                display_name=request.display_name,
                description=request.description,
                required_tools=request.required_tools,
                enabled=request.enabled,
            )
        except SkillServiceError as error:
            return fail("skill_invalid", str(error))

        return ok({
            "skill_id": descriptor.skill_id,
            "display_name": descriptor.display_name,
            "description": descriptor.description,
            "enabled": descriptor.enabled,
            "required_tools": list(descriptor.required_tools),
            "created_at": descriptor.created_at.isoformat() if getattr(descriptor, "created_at", None) else None,
            "updated_at": descriptor.updated_at.isoformat() if getattr(descriptor, "updated_at", None) else None,
        })

    def delete_skill(self, skill_id: str):
        """删除 skill。"""
        deleted = self.skill_service.delete_skill(skill_id)
        if not deleted:
            return fail("skill_not_found", f"Skill `{skill_id}` does not exist.")
        return ok({"skill_id": skill_id, "deleted": True})

    def list_knowledge_documents(self):
        documents = self.knowledge_service.list_documents()
        return ok({"items": [self._knowledge_payload(item) for item in documents]})

    def create_knowledge_document(self, request: CreateKnowledgeDocumentRequest):
        if request.conversation_id:
            conversation = self.conversation_service.get_conversation(request.conversation_id)
            if conversation is None:
                return fail("conversation_not_found", "Conversation does not exist.")
        document = self.knowledge_service.import_document(
            title=request.title,
            content=request.content,
            tags=request.tags,
            source_url=request.source_url,
            source_task_id=request.source_task_id,
            conversation_id=request.conversation_id,
            notes=request.notes,
        )
        return ok(self._knowledge_payload(document))

    def search_paper_candidates(self, request: SearchPaperCandidatesRequest):
        candidates = self.knowledge_service.search_paper_candidates(
            request.query,
            limit=request.limit,
        )
        response = ListPaperImportCandidatesResponse(
            items=[self._paper_candidate_payload(item) for item in candidates]
        )
        return ok(response.model_dump())

    def import_paper_candidate(self, request: ImportPaperCandidateRequest):
        if request.conversation_id:
            conversation = self.conversation_service.get_conversation(request.conversation_id)
            if conversation is None:
                return fail("conversation_not_found", "Conversation does not exist.")
        try:
            document = self.knowledge_service.import_paper_candidate(
                request.candidate_id,
                conversation_id=request.conversation_id,
                notes=request.notes,
                tags=request.tags,
            )
        except KeyError:
            return fail("paper_candidate_not_found", "Paper candidate does not exist or has expired.")
        payload = self._knowledge_payload(document)
        if request.conversation_id:
            paper = self.research_paper_service.add_document(
                conversation_id=request.conversation_id,
                document=document,
                origin="user_import",
            )
            payload["research_paper"] = self._research_paper_payload(paper)
        return ok(payload)

    def import_research_pdfs(
        self,
        conversation_id: str,
        uploads,
        *,
        status: str = "candidate",
    ):
        if self.conversation_service.get_conversation(conversation_id) is None:
            return fail("conversation_not_found", "Conversation does not exist.")
        if self.pdf_import_service is None:
            return fail("pdf_import_unavailable", "PDF import service is not configured.")
        try:
            results = self.pdf_import_service.import_batch(
                conversation_id=conversation_id,
                uploads=uploads,
                status=status,
            )
        except ResearchPaperServiceError as error:
            return fail("research_paper_status_invalid", str(error))

        items = []
        for result in results:
            document_payload = (
                self._knowledge_payload(result.document)
                if result.document is not None
                else None
            )
            paper_payload = (
                self._research_paper_payload(result.research_paper)
                if result.research_paper is not None
                else None
            )
            items.append(
                PdfImportItemView(
                    filename=result.filename,
                    success=result.success,
                    document=document_payload,
                    research_paper=paper_payload,
                    parsed_pages=result.parsed_pages,
                    total_pages=result.total_pages,
                    duplicate_replaced=result.duplicate_replaced,
                    warnings=result.warnings or [],
                    error_code=result.error_code,
                    error_message=result.error_message,
                )
            )
        response = BatchPdfImportResponse(
            items=items,
            imported_count=sum(1 for item in items if item.success),
            failed_count=sum(1 for item in items if not item.success),
        )
        return ok(response.model_dump())

    def list_research_papers(self, conversation_id: str, *, status: str | None = None):
        if self.conversation_service.get_conversation(conversation_id) is None:
            return fail("conversation_not_found", "Conversation does not exist.")
        try:
            papers = self.research_paper_service.list_papers(conversation_id, status=status)
        except ResearchPaperServiceError as error:
            return fail("research_paper_status_invalid", str(error))
        response = ListResearchPapersResponse(
            items=[ResearchPaperView(**self._research_paper_payload(item)) for item in papers],
            total=len(papers),
        )
        return ok(response.model_dump())

    def update_research_paper(
        self,
        conversation_id: str,
        paper_entry_id: str,
        request: UpdateResearchPaperRequest,
    ):
        if self.conversation_service.get_conversation(conversation_id) is None:
            return fail("conversation_not_found", "Conversation does not exist.")
        try:
            paper = self.research_paper_service.update_status(
                conversation_id=conversation_id,
                paper_entry_id=paper_entry_id,
                status=request.status,
            )
        except KeyError:
            return fail("research_paper_not_found", "Research paper does not exist in this conversation.")
        except ResearchPaperServiceError as error:
            return fail("research_paper_status_invalid", str(error))
        return ok(self._research_paper_payload(paper))

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
            "knowledge_scope": task.knowledge_scope,
            "research_mode": task.research_mode,
            "trigger_message_id": task.trigger_message_id,
            "selected_skill_ids": list(getattr(task, "selected_skill_ids", []) or []),
            "created_at": task.created_at.isoformat(),
            "updated_at": task.updated_at.isoformat(),
        }

    @staticmethod
    def _knowledge_payload(document) -> dict:
        return {
            "document_id": document.document_id,
            "title": document.title,
            "source_task_id": document.source_task_id,
            "conversation_id": document.metadata.get("conversation_id"),
            "content": document.content,
            "tags": list(document.tags),
            "metadata": dict(document.metadata),
        }

    @staticmethod
    def _knowledge_hit_payload(hit) -> dict:
        return {
            "document_id": hit.document_id,
            "title": hit.title,
            "snippet": hit.snippet,
            "score": hit.score,
            "scope": hit.scope,
            "source_task_id": hit.source_task_id,
            "source_type": hit.source_type,
            "evidence_level": hit.evidence_level,
            "matched_chunk_count": int(hit.matched_chunk_count),
            "supporting_snippets": list(hit.supporting_snippets),
        }

    @staticmethod
    def _paper_candidate_payload(candidate) -> PaperImportCandidateView:
        return PaperImportCandidateView(
            candidate_id=candidate.candidate_id,
            title=candidate.title,
            authors=list(candidate.authors),
            year=candidate.year,
            abstract=candidate.abstract,
            source_url=candidate.source_url,
            pdf_url=candidate.pdf_url,
            doi=candidate.doi,
            arxiv_id=candidate.arxiv_id,
            source=candidate.source,
            venue=candidate.venue,
            is_exact_match=candidate.is_exact_match,
        )

    @staticmethod
    def _research_paper_payload(paper) -> dict[str, Any]:
        return {
            "paper_entry_id": paper.paper_entry_id,
            "conversation_id": paper.conversation_id,
            "document_id": paper.document_id,
            "canonical_key": paper.canonical_key,
            "title": paper.title,
            "origin": paper.origin,
            "status": paper.status,
            "source_url": paper.source_url,
            "metadata": dict(paper.metadata),
            "created_at": paper.created_at.isoformat(),
            "updated_at": paper.updated_at.isoformat(),
        }

    @staticmethod
    def _workspace_source_trace_payload(snapshot) -> dict[str, Any]:
        if snapshot is None or getattr(snapshot, "source_trace", None) is None:
            return {}
        if hasattr(snapshot.source_trace, "model_dump"):
            return snapshot.source_trace.model_dump()
        return dict(snapshot.source_trace)

    @staticmethod
    def _workspace_inherited_context_payload(snapshot) -> dict[str, Any]:
        if snapshot is None or getattr(snapshot, "inherited_context", None) is None:
            return {}
        if hasattr(snapshot.inherited_context, "model_dump"):
            return snapshot.inherited_context.model_dump()
        return dict(snapshot.inherited_context)

    def _build_task_result_message(self, *, task, workspace) -> str:
        """Build a natural research summary from workspace data.

        Uses LLM when available for richer responses; falls back to
        a detailed template that reads like a research assistant finding,
        not a task log.
        """
        content = self._build_natural_assistant_message(task=task, workspace=workspace).strip()
        if task.status == "degraded":
            return (
                "本轮已完成分析；直接证据不足的具体方向已在结果中标为探索性方向。\n\n"
                f"{content}"
            )
        if task.status == "step_limit_reached":
            return (
                "本轮在完成最终合成前达到控制器步数上限，工作台保留了部分结果供排查，"
                "但这些内容不会自动沉淀为长期知识。\n\n"
                f"{content}"
            )
        return content

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
            f"\u5df2\u5b8c\u6210\u672c\u8f6e\u7814\u7a76\u4efb\u52a1\uff1a{topic}",
            "",
            (
                f"\u6211\u5148\u56f4\u7ed5\u300c{topic}\u300d\u68b3\u7406\u4e86 {total_papers} \u7bc7\u8bba\u6587\uff0c"
                f"\u8bc6\u522b\u51fa {len(workspace.gaps)} \u6761\u7814\u7a76\u7a7a\u767d\uff0c"
                f"\u6574\u7406\u51fa {len(workspace.ideas)} \u6761\u53ef\u7ee7\u7eed\u63a8\u8fdb\u7684\u65b9\u5411\uff0c"
                f"\u5f53\u524d\u5bf9\u9f50\u5206\u6570\u662f {workspace.alignment_score:.3f}\u3002"
            ),
        ]

        if insufficient:
            lines.append(
                "\u5f53\u524d\u771f\u5b9e\u8bc1\u636e\u504f\u5c11\uff0c\u8fd9\u8f6e\u7ed3\u679c\u66f4\u9002\u5408\u7528\u6765\u5e2e\u4f60\u6536\u7f29\u7814\u7a76\u65b9\u5411\uff0c"
                "\u540e\u7eed\u6700\u597d\u7ee7\u7eed\u8865\u5145\u8bba\u6587\u6216\u5bfc\u5165\u4f60\u81ea\u5df1\u627e\u5230\u7684\u8d44\u6599\u3002"
            )
        elif fallback_count:
            lines.append(
                f"\u8fd9\u4e00\u8f6e\u91cc\u6709 {fallback_count} \u7bc7\u662f\u7cfb\u7edf\u56de\u9000\u8bba\u6587\uff0c"
                "\u8bf4\u660e\u5916\u90e8\u68c0\u7d22\u8bc1\u636e\u8fd8\u4e0d\u591f\u7a33\uff0c\u6240\u4ee5\u540e\u7eed\u4ecd\u5efa\u8bae\u7ee7\u7eed\u8865\u5145\u771f\u5b9e\u6587\u732e\u3002"
            )

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
            lines.extend(["", "\u4f18\u5148\u5173\u6ce8"])
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
            "- \u5982\u679c\u65b9\u5411\u8fd8\u662f\u504f\u5bbd\uff0c\u53ef\u4ee5\u7ee7\u7eed\u8ffd\u95ee\u5e76\u7f29\u5c0f\u5230\u5e74\u4efd\u3001\u65b9\u6cd5\u6216\u5177\u4f53\u5e94\u7528\u573a\u666f\u3002",
            "- \u5982\u679c\u4f60\u5df2\u7ecf\u6709\u81ea\u5df1\u627e\u5230\u7684\u8bba\u6587\u6216\u7b14\u8bb0\uff0c\u4e5f\u53ef\u4ee5\u5bfc\u5165\u8d44\u6599\u6765\u7ee7\u7eed\u8865\u5f3a\u8fd9\u8f6e\u7814\u7a76\u3002",
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

