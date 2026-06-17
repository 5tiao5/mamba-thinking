from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Any, TYPE_CHECKING
from uuid import uuid4

from product_agent.domain import ResearchTask, ResearchTaskEvent, ResearchWorkspace
from product_agent.repositories import (
    ConversationRepository,
    ResearchTaskEventRepository,
    ResearchTaskRepository,
    WorkspaceRepository,
)
from product_agent.services.query_intent import QueryIntent, build_search_seed, derive_query_intent
from product_agent.services.errors import ConversationNotFoundError, InvalidTaskModeError, TaskNotFoundError
from product_agent.services.text_cleaning import clean_internal_context_items, clean_internal_context_text
from product_agent.services.workspace_mapper import workspace_from_agent_state

if TYPE_CHECKING:
    from product_agent.services.knowledge_service import KnowledgeHit, KnowledgeService
    from product_agent.services.message_service import MessageService
    from product_agent.services.research_paper_service import ResearchPaperService
    from product_agent.services.working_memory_service import WorkingMemoryService


@dataclass
class ResearchContextBundle:
    conversation_topic: str
    knowledge_scope: str
    research_mode: str
    query_intent: dict[str, Any]
    recent_context: list[dict[str, Any]]
    knowledge_hits: list[dict[str, Any]]
    knowledge_context: list[str]
    conversation_workspace_context: list[str]
    conversation_workspace_summary: str
    working_memory_summary: str
    working_memory_current_focus: str
    working_memory_findings: list[str]
    working_memory_open_questions: list[str]
    working_memory_constraints: list[str]
    previous_round_task_id: str
    previous_round_paper_ids: list[str]
    previous_round_papers: list[dict[str, Any]]
    previous_round_query_intent: dict[str, Any]
    research_papers: list[dict[str, Any]]
    context_inputs: list[dict[str, Any]]
    selected_skill_ids: list[str] = None
    skill_descriptions: list[str] = None

    def __post_init__(self):
        if self.selected_skill_ids is None:
            self.selected_skill_ids = []
        if self.skill_descriptions is None:
            self.skill_descriptions = []

    def to_pipeline_payload(self) -> dict[str, Any]:
        return {
            "conversation_topic": self.conversation_topic,
            "knowledge_scope": self.knowledge_scope,
            "research_mode": self.research_mode,
            "query_intent": dict(self.query_intent),
            "recent_context": list(self.recent_context),
            "knowledge_hits": list(self.knowledge_hits),
            "knowledge_context": list(self.knowledge_context),
            "conversation_workspace_context": list(self.conversation_workspace_context),
            "conversation_workspace_summary": self.conversation_workspace_summary,
            "working_memory_summary": self.working_memory_summary,
            "working_memory_current_focus": self.working_memory_current_focus,
            "working_memory_findings": list(self.working_memory_findings),
            "working_memory_open_questions": list(self.working_memory_open_questions),
            "working_memory_constraints": list(self.working_memory_constraints),
            "previous_round_task_id": self.previous_round_task_id,
            "previous_round_paper_ids": list(self.previous_round_paper_ids),
            "previous_round_papers": list(self.previous_round_papers),
            "previous_round_query_intent": dict(self.previous_round_query_intent),
            "research_papers": list(self.research_papers),
            "context_inputs": list(self.context_inputs),
            "selected_skill_ids": list(self.selected_skill_ids),
            "skill_descriptions": list(self.skill_descriptions),
        }


class ResearchService:
    """
    编排一轮研究任务。

    当前约束：
    - 任务创建、任务执行、任务状态流转统一由本服务负责
    - handler 不应直接访问 task repository
    """

    SUPPORTED_MODES = {"default", "fast", "balanced"}
    SUPPORTED_RESEARCH_MODES = {"hybrid", "imported_only", "search_only"}

    def __init__(
        self,
        *,
        conversation_repository: ConversationRepository,
        task_repository: ResearchTaskRepository,
        workspace_repository: WorkspaceRepository,
        task_event_repository: ResearchTaskEventRepository | None = None,
        workspace_service=None,
        message_service: MessageService | None = None,
        knowledge_service: KnowledgeService | None = None,
        research_paper_service: ResearchPaperService | None = None,
        working_memory_service: WorkingMemoryService | None = None,
        skill_service=None,
    ) -> None:
        self.conversation_repository = conversation_repository
        self.task_repository = task_repository
        self.task_event_repository = task_event_repository
        self.workspace_repository = workspace_repository
        self.workspace_service = workspace_service
        self.message_service = message_service
        self.knowledge_service = knowledge_service
        self.research_paper_service = research_paper_service
        self.working_memory_service = working_memory_service
        self.skill_service = skill_service

    def create_task(
        self,
        *,
        conversation_id: str,
        topic: str,
        mode: str = "default",
        knowledge_scope: str = "shared",
        research_mode: str = "hybrid",
        trigger_message_id: str | None = None,
        selected_skill_ids: list[str] | None = None,
    ) -> ResearchTask:
        """
        创建一条新的研究分析任务记录。

        约束：
        - `conversation_id` 必须对应有效会话
        - `mode` 必须属于受支持集合
        """
        conversation = self.conversation_repository.get(conversation_id)
        if conversation is None:
            raise ConversationNotFoundError(f"Conversation `{conversation_id}` does not exist.")
        if mode not in self.SUPPORTED_MODES:
            raise InvalidTaskModeError(
                f"Mode `{mode}` is invalid. Supported modes: {sorted(self.SUPPORTED_MODES)}."
            )
        if research_mode not in self.SUPPORTED_RESEARCH_MODES:
            raise InvalidTaskModeError(
                f"Research mode `{research_mode}` is invalid. "
                f"Supported modes: {sorted(self.SUPPORTED_RESEARCH_MODES)}."
            )

        task = ResearchTask(
            task_id=f"task_{uuid4().hex[:12]}",
            conversation_id=conversation_id,
            topic=topic,
            mode=mode,
            knowledge_scope=knowledge_scope,
            research_mode=research_mode,
            trigger_message_id=trigger_message_id,
            selected_skill_ids=list(selected_skill_ids or []),
            status="created",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        created_task = self.task_repository.create(task)
        self._append_task_event(
            task_id=created_task.task_id,
            stage="task",
            status="created",
            message="Research task created.",
            payload={
                "mode": created_task.mode,
                "knowledge_scope": created_task.knowledge_scope,
                "research_mode": created_task.research_mode,
            },
        )
        conversation.latest_task_id = created_task.task_id
        conversation.updated_at = datetime.now(timezone.utc)
        self.conversation_repository.update(conversation)
        return created_task

    def create_follow_up_task(
        self,
        *,
        conversation_id: str,
        base_topic: str,
        latest_message_content: str,
        focus: str | None = None,
        knowledge_hints: list[str] | None = None,
        workspace_hints: list[str] | None = None,
        mode: str = "default",
        knowledge_scope: str = "shared",
        research_mode: str = "hybrid",
        trigger_message_id: str | None = None,
        selected_skill_ids: list[str] | None = None,
    ) -> ResearchTask:
        """
        基于一轮新追问创建 follow-up 研究任务。

        设计目标：
        - 让"继续对话"不只是写消息，而是真正落到任务链路中
        - 前端可以选择立即运行该任务，或先把任务展示给用户
        """
        follow_up_topic = self._derive_follow_up_topic(
            base_topic=base_topic,
            latest_message_content=latest_message_content,
            focus=focus,
            knowledge_hints=knowledge_hints,
            workspace_hints=workspace_hints,
        )
        return self.create_task(
            conversation_id=conversation_id,
            topic=follow_up_topic,
            mode=mode,
            knowledge_scope=knowledge_scope,
            research_mode=research_mode,
            trigger_message_id=trigger_message_id,
            selected_skill_ids=selected_skill_ids,
        )

    def get_task(self, task_id: str) -> ResearchTask:
        """按 ID 获取任务；找不到时抛出显式业务异常。"""
        task = self.task_repository.get(task_id)
        if task is None:
            raise TaskNotFoundError(f"Research task `{task_id}` does not exist.")
        return task

    def list_tasks(
        self,
        *,
        conversation_id: str | None = None,
        limit: int | None = None,
    ) -> list[ResearchTask]:
        """
        列出历史研究任务。
        约束:
        - 若指定 `conversation_id`，则只返回对应会话下的任务
        - 默认按最近更新时间倒序返回
        """
        items = self.task_repository.list_all()
        if conversation_id is not None:
            items = [item for item in items if item.conversation_id == conversation_id]
        if limit is not None:
            return items[:limit]
        return items

    def list_task_events(self, task_id: str) -> list[ResearchTaskEvent]:
        self.get_task(task_id)
        if self.task_event_repository is None:
            return []
        return self.task_event_repository.list_by_task(task_id)

    def run_task(self, task: ResearchTask) -> ResearchWorkspace:
        """
        运行一条研究任务，并把 Agent 结果投影为产品工作台数据。

        当前副作用：
        - 调用 `product_agent.research_agent.pipeline.run_pipeline`
        - 调用 `workspace_repository.save` 保存工作台快照
        - 根据运行结果更新 `task.status=completed/degraded/step_limit_reached`
        - 失败时更新 `task.status=failed`
        """
        task.status = "running"
        task.updated_at = datetime.now(timezone.utc)
        self.task_repository.update(task)
        self._append_task_event(
            task_id=task.task_id,
            stage="runtime",
            status="started",
            message="Research task started.",
            payload={
                "topic": task.topic,
                "mode": task.mode,
                "knowledge_scope": task.knowledge_scope,
                "research_mode": task.research_mode,
            },
        )

        try:
            from product_agent.research_agent.pipeline import run_pipeline

            research_context = self._build_research_context(task)
            state_event_recorder = self._build_state_event_recorder(task.task_id)
            state = run_pipeline(
                task.topic,
                mode=task.mode,
                conversation_workspace_context=research_context.conversation_workspace_context,
                research_context=research_context.to_pipeline_payload(),
                show_progress=False,
                state_callback=state_event_recorder,
            )
            workspace: ResearchWorkspace = workspace_from_agent_state(
                task_id=task.task_id,
                topic=task.topic,
                state=state,
            )
            # 将 selected_skill_ids 显式记录到 trace 中
            if task.selected_skill_ids:
                trace = dict(workspace.trace)
                trace["selected_skill_ids"] = list(task.selected_skill_ids)
                workspace.trace = trace
            saved_workspace = self.workspace_repository.save(workspace)
            run_status = str(state.get("run_status", "step_limit_reached") or "step_limit_reached")
            if self.working_memory_service is not None and state.get("synthesis_completed"):
                self.working_memory_service.refresh_from_workspace(
                    task=task,
                    workspace=saved_workspace,
                    query_intent=research_context.query_intent,
                    conversation_topic=research_context.conversation_topic,
                )
            task.status = run_status
            task.updated_at = datetime.now(timezone.utc)
            self.task_repository.update(task)
            self._append_task_event(
                task_id=task.task_id,
                stage="runtime",
                status=run_status,
                message=f"Research task finished with status {run_status}.",
                payload={
                    "termination_reason": str(state.get("termination_reason", "") or ""),
                    "degraded_reason": str(state.get("degraded_reason", "") or ""),
                    "paper_count": len(workspace.papers),
                    "gap_count": len(workspace.gaps),
                    "idea_count": len(workspace.ideas),
                },
            )
            return saved_workspace
        except Exception as error:
            task.status = "failed"
            task.updated_at = datetime.now(timezone.utc)
            self.task_repository.update(task)
            self._append_task_event(
                task_id=task.task_id,
                stage="runtime",
                status="failed",
                message="Research task failed.",
                payload={"error": str(error)},
            )
            raise

    def _append_task_event(
        self,
        *,
        task_id: str,
        stage: str,
        status: str,
        message: str = "",
        payload: dict[str, Any] | None = None,
    ) -> ResearchTaskEvent | None:
        if self.task_event_repository is None:
            return None

        try:
            existing = self.task_event_repository.list_by_task(task_id)
            next_sequence = (existing[-1].sequence + 1) if existing else 1
            event = ResearchTaskEvent(
                event_id=f"event_{uuid4().hex[:12]}",
                task_id=task_id,
                sequence=next_sequence,
                stage=stage,
                status=status,
                message=message,
                payload=dict(payload or {}),
                created_at=datetime.now(timezone.utc),
            )
            return self.task_event_repository.append(event)
        except Exception:
            return None

    def _build_state_event_recorder(self, task_id: str):
        last_log_count = 0

        def record_state_event(state: dict[str, Any]) -> None:
            nonlocal last_log_count
            logs = list(state.get("logs", []) or [])
            new_logs = logs[last_log_count:]
            last_log_count = len(logs)
            if not new_logs:
                return

            for log in new_logs:
                stage, status = self._stage_status_from_log(str(log))
                self._append_task_event(
                    task_id=task_id,
                    stage=stage,
                    status=status,
                    message=str(log),
                    payload=self._state_event_payload(state),
                )

        return record_state_event

    @staticmethod
    def _stage_status_from_log(log: str) -> tuple[str, str]:
        if log.startswith("Action started:"):
            return log.split(":", 1)[1].strip() or "pipeline", "started"
        match = re.match(r"Action\s+([A-Za-z0-9_\-]+)\s+complete:", log)
        if match:
            return match.group(1), "completed"
        if log.startswith("Run terminated:"):
            status_match = re.search(r"status=([^,\s]+)", log)
            return "runtime", status_match.group(1) if status_match else "completed"
        return "pipeline", "progress"

    @staticmethod
    def _state_event_payload(state: dict[str, Any]) -> dict[str, Any]:
        paper_nodes = state.get("paper_nodes", {}) or {}
        evidence_pool = state.get("evidence_pool", paper_nodes) or {}
        taxonomy = state.get("expert_taxonomy", {}) or {}
        branches = taxonomy.get("branches", []) if isinstance(taxonomy, dict) else []
        return {
            "next_action": str(state.get("next_action", "") or ""),
            "current_goal": str(state.get("current_goal", "") or ""),
            "pending_actions": list(state.get("pending_actions", []) or [])[:8],
            "paper_count": len(paper_nodes) if hasattr(paper_nodes, "__len__") else 0,
            "evidence_pool_count": len(evidence_pool) if hasattr(evidence_pool, "__len__") else 0,
            "taxonomy_branch_count": len(branches) if hasattr(branches, "__len__") else 0,
            "graph_edge_count": len(state.get("evolution_graph", []) or []),
            "gap_count": len(state.get("detected_gaps", []) or []),
            "idea_count": len(state.get("generated_ideas", []) or []),
            "run_status": str(state.get("run_status", "") or ""),
        }

    @staticmethod
    def _derive_follow_up_topic(
        *,
        base_topic: str,
        latest_message_content: str,
        focus: str | None = None,
        knowledge_hints: list[str] | None = None,
        workspace_hints: list[str] | None = None,
    ) -> str:
        base_topic = clean_internal_context_text(base_topic, max_length=140) or base_topic
        latest_message_content = clean_internal_context_text(latest_message_content, max_length=180)
        focus_text = clean_internal_context_text(focus or "", max_length=100)
        if focus_text:
            topic = f"{base_topic} - {focus_text}"
        else:
            snippet = " ".join(latest_message_content.strip().split())
            if not snippet:
                topic = base_topic
            else:
                topic = f"{base_topic} - {snippet[:80]}"

        workspace_context = clean_internal_context_items(workspace_hints or [], max_length=70)
        knowledge_context = clean_internal_context_items(knowledge_hints or [], max_length=80)
        if workspace_context or knowledge_context:
            return clean_internal_context_text(topic, max_length=180) or topic
        return topic

    def _build_research_context(self, task: ResearchTask) -> ResearchContextBundle:
        conversation = self.conversation_repository.get(task.conversation_id)
        conversation_topic = clean_internal_context_text(
            getattr(conversation, "topic", "") or task.topic,
            max_length=180,
        ) or task.topic
        workspace_hints = self._conversation_workspace_hints(task.conversation_id)
        workspace_summary = self._conversation_workspace_summary(task.conversation_id)
        working_memory = self._conversation_working_memory(task.conversation_id)
        working_memory_summary = clean_internal_context_text(
            getattr(working_memory, "summary", "") if working_memory else "",
            max_length=280,
        )
        working_memory_current_focus = clean_internal_context_text(
            getattr(working_memory, "current_focus", "") if working_memory else "",
            max_length=180,
        )
        working_memory_findings = clean_internal_context_items(
            list(getattr(working_memory, "stable_findings", []) or []),
            max_length=120,
        )
        working_memory_open_questions = clean_internal_context_items(
            list(getattr(working_memory, "open_questions", []) or []),
            max_length=140,
        )
        working_memory_constraints = clean_internal_context_items(
            list(getattr(working_memory, "active_constraints", []) or []),
            max_length=120,
        )
        recent_context = self._recent_message_context(task.conversation_id)
        previous_round = self._previous_round_context_for_task(task)
        research_papers, excluded_document_ids = self._research_paper_context_for_task(
            task.conversation_id,
            research_mode=task.research_mode,
        )
        raw_user_request = self._raw_user_request_for_task(task, recent_context=recent_context)
        initial_query_intent = derive_query_intent(
            raw_user_request=raw_user_request,
            task_topic=task.topic,
            conversation_topic=conversation_topic,
            knowledge_scope=task.knowledge_scope,
            workspace_hints=workspace_hints,
            knowledge_hints=[
                *working_memory_findings[:2],
                *working_memory_open_questions[:1],
                *working_memory_constraints[:2],
            ],
            recent_context=recent_context,
        )
        knowledge_hits, knowledge_context = self._knowledge_context_for_task(
            task,
            conversation_topic=conversation_topic,
            recent_context=recent_context,
            workspace_hints=workspace_hints,
            query_intent=initial_query_intent,
            working_memory_summary=working_memory_summary,
            working_memory_findings=working_memory_findings,
            working_memory_open_questions=working_memory_open_questions,
            excluded_document_ids=excluded_document_ids,
        )
        query_intent = derive_query_intent(
            raw_user_request=raw_user_request,
            task_topic=task.topic,
            conversation_topic=conversation_topic,
            knowledge_scope=task.knowledge_scope,
            workspace_hints=workspace_hints,
            knowledge_hints=(
                [
                    *working_memory_findings[:2],
                    *working_memory_open_questions[:1],
                ]
                + [
                    str(hit.get("title", "") or hit.get("snippet", "")).strip()
                    for hit in knowledge_hits
                    if str(hit.get("title", "") or hit.get("snippet", "")).strip()
                ]
            ),
            recent_context=recent_context,
        )
        context_inputs = [
            {
                "kind": "research_context_bundle",
                "knowledge_scope": task.knowledge_scope,
                "research_mode": task.research_mode,
                "conversation_topic": conversation_topic,
                "raw_user_request": raw_user_request,
                "query_intent_summary": query_intent.summary,
                "knowledge_hit_count": len(knowledge_hits),
                "knowledge_titles": [str(hit.get("title", "")).strip() for hit in knowledge_hits[:3]],
                "workspace_hints": list(workspace_hints[:3]),
                "workspace_summary": workspace_summary,
                "working_memory_summary": working_memory_summary,
                "working_memory_current_focus": working_memory_current_focus,
                "working_memory_findings": list(working_memory_findings[:3]),
                "working_memory_open_questions": list(working_memory_open_questions[:2]),
                "working_memory_constraints": list(working_memory_constraints[:3]),
                "previous_round_task_id": previous_round["task_id"],
                "previous_round_paper_count": len(previous_round["paper_ids"]),
                "research_paper_count": len(research_papers),
                "core_research_paper_count": sum(
                    1 for paper in research_papers if paper.get("status") == "core"
                ),
                "recent_turns": [
                    f"{entry.get('role', 'unknown')}: {entry.get('content', '')}"
                    for entry in recent_context[-3:]
                ],
            },
            {
                "kind": "research_paper_pool",
                "paper_count": len(research_papers),
                "core_count": sum(
                    1 for paper in research_papers if paper.get("status") == "core"
                ),
                "candidate_count": sum(
                    1 for paper in research_papers if paper.get("status") == "candidate"
                ),
                "excluded_count": len(excluded_document_ids),
                "papers": [
                    {
                        "paper_id": paper.get("paper_id", ""),
                        "title": paper.get("title", ""),
                        "status": paper.get("status", ""),
                        "origin": paper.get("origin", ""),
                    }
                    for paper in research_papers[:20]
                ],
            },
            {
                "kind": "working_memory",
                "summary": working_memory_summary,
                "current_focus": working_memory_current_focus,
                "stable_findings": list(working_memory_findings[:4]),
                "open_questions": list(working_memory_open_questions[:3]),
                "active_constraints": list(working_memory_constraints[:4]),
                "source_task_id": getattr(working_memory, "source_task_id", None) if working_memory else None,
                "supporting_task_ids": list(getattr(working_memory, "supporting_task_ids", []) or [])[:6] if working_memory else [],
            },
            query_intent.to_context_input(),
        ]

        # ── Skill context injection ──
        skill_descriptions: list[str] = []
        if self.skill_service is not None and task.selected_skill_ids:
            skill_descriptions = self.skill_service.get_enabled_skill_descriptions(task.selected_skill_ids)
            if skill_descriptions:
                context_inputs.append({
                    "kind": "selected_skills",
                    "skill_ids": list(task.selected_skill_ids),
                    "descriptions": skill_descriptions,
                })

        return ResearchContextBundle(
            conversation_topic=conversation_topic,
            knowledge_scope=task.knowledge_scope,
            research_mode=task.research_mode,
            query_intent=query_intent.to_dict(),
            recent_context=recent_context,
            knowledge_hits=knowledge_hits,
            knowledge_context=knowledge_context,
            conversation_workspace_context=workspace_hints,
            conversation_workspace_summary=workspace_summary,
            working_memory_summary=working_memory_summary,
            working_memory_current_focus=working_memory_current_focus,
            working_memory_findings=working_memory_findings,
            working_memory_open_questions=working_memory_open_questions,
            working_memory_constraints=working_memory_constraints,
            previous_round_task_id=previous_round["task_id"],
            previous_round_paper_ids=previous_round["paper_ids"],
            previous_round_papers=previous_round["papers"],
            previous_round_query_intent=previous_round["query_intent"],
            research_papers=research_papers,
            context_inputs=context_inputs,
            selected_skill_ids=list(task.selected_skill_ids),
            skill_descriptions=skill_descriptions,
        )

    def _recent_message_context(self, conversation_id: str, *, limit: int = 6) -> list[dict[str, Any]]:
        if self.message_service is None:
            return []
        try:
            messages = self.message_service.get_recent_context(conversation_id, limit=limit) or []
        except Exception:
            return []

        recent_context: list[dict[str, Any]] = []
        for message in messages:
            role = str(getattr(message, "role", "") or "").strip().lower()
            if role not in {"user", "assistant"}:
                continue
            content = clean_internal_context_text(getattr(message, "content", ""), max_length=200)
            if not content:
                continue
            recent_context.append(
                {
                    "message_id": str(getattr(message, "message_id", "") or ""),
                    "role": role,
                    "content": content,
                }
            )
        return recent_context[-4:]

    def _knowledge_context_for_task(
        self,
        task: ResearchTask,
        *,
        conversation_topic: str,
        recent_context: list[dict[str, Any]],
        workspace_hints: list[str],
        query_intent: QueryIntent,
        working_memory_summary: str,
        working_memory_findings: list[str],
        working_memory_open_questions: list[str],
        excluded_document_ids: set[str] | None = None,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        if self.knowledge_service is None or task.knowledge_scope == "none":
            return [], []

        query = self._knowledge_query_for_task(
            task=task,
            conversation_topic=conversation_topic,
            recent_context=recent_context,
            workspace_hints=workspace_hints,
            query_intent=query_intent,
            working_memory_summary=working_memory_summary,
            working_memory_findings=working_memory_findings,
            working_memory_open_questions=working_memory_open_questions,
        )
        hits = self.knowledge_service.retrieve_hits_for_context(
            query,
            top_k=4,
            knowledge_scope=task.knowledge_scope,
            conversation_id=task.conversation_id,
        )
        excluded_ids = excluded_document_ids or set()
        hits = [hit for hit in hits if hit.document_id not in excluded_ids]
        topic_anchor = " ".join(
            [
                str(query_intent.core_topic or ""),
                str(conversation_topic or ""),
                *[
                    str(term)
                    for term in list(query_intent.focus_terms or [])[:4]
                    if str(term).strip()
                ],
            ]
        )
        hits = [
            hit
            for hit in hits
            if self._knowledge_hit_is_relevant(
                hit,
                topic_anchor=topic_anchor,
            )
        ]
        hit_dicts = [self._serialize_knowledge_hit(hit) for hit in hits]
        knowledge_context = [self.knowledge_service.format_hit_for_context(hit) for hit in hits]
        return hit_dicts, knowledge_context

    @classmethod
    def _knowledge_hit_is_relevant(
        cls,
        hit: KnowledgeHit,
        *,
        topic_anchor: str,
    ) -> bool:
        if str(hit.scope or "").casefold() == "conversation":
            return True

        score = float(hit.score or 0.0)
        if score < 0.25:
            return False
        if score >= 0.55:
            return True

        anchor_terms = cls._knowledge_anchor_terms(topic_anchor)
        if not anchor_terms:
            return False
        hit_text = " ".join(
            [
                str(hit.title or ""),
                str(hit.snippet or ""),
                *[
                    str(snippet)
                    for snippet in list(hit.supporting_snippets or [])[:2]
                ],
            ]
        ).casefold()
        matched_terms = {
            term for term in anchor_terms if term in hit_text
        }
        chinese_matches = {
            term
            for term in matched_terms
            if any("\u4e00" <= character <= "\u9fff" for character in term)
        }
        english_matches = matched_terms - chinese_matches
        return bool(chinese_matches) or len(english_matches) >= 2

    @staticmethod
    def _knowledge_anchor_terms(value: str) -> set[str]:
        text = str(value or "").casefold()
        english_stopwords = {
            "about",
            "analysis",
            "approach",
            "based",
            "model",
            "models",
            "paper",
            "papers",
            "research",
            "study",
            "using",
        }
        terms = {
            token
            for token in re.findall(r"[a-z][a-z0-9-]{2,}", text)
            if token not in english_stopwords
        }
        for segment in re.findall(r"[\u4e00-\u9fff]{4,}", text):
            for width in (4, 5, 6):
                terms.update(
                    segment[index : index + width]
                    for index in range(max(0, len(segment) - width + 1))
                )
        return terms

    def _research_paper_context_for_task(
        self,
        conversation_id: str,
        *,
        research_mode: str = "hybrid",
    ) -> tuple[list[dict[str, Any]], set[str]]:
        if self.research_paper_service is None or self.knowledge_service is None:
            return [], set()

        papers: list[dict[str, Any]] = []
        excluded_document_ids: set[str] = set()
        for entry in self.research_paper_service.list_papers(conversation_id):
            if research_mode == "search_only":
                excluded_document_ids.add(entry.document_id)
                continue
            if entry.status == "excluded":
                excluded_document_ids.add(entry.document_id)
                continue

            document = self.knowledge_service.get_document(entry.document_id)
            if document is None:
                continue
            metadata = {**dict(document.metadata or {}), **dict(entry.metadata or {})}
            abstract, review_text = self._paper_text_context(document.content)
            authors = metadata.get("authors", [])
            if isinstance(authors, str):
                authors = [item.strip() for item in re.split(r"[,;]", authors) if item.strip()]
            elif not isinstance(authors, list):
                authors = []

            arxiv_id = str(metadata.get("arxiv_id", "") or "").strip()
            doi = str(metadata.get("doi", "") or "").strip()
            if arxiv_id:
                paper_id = re.sub(r"v\d+$", "", arxiv_id, flags=re.IGNORECASE)
            elif doi:
                paper_id = doi.removeprefix("https://doi.org/").removeprefix("http://doi.org/")
            else:
                paper_id = f"imported:{entry.paper_entry_id}"

            citation_count = metadata.get("citation_count", 0)
            try:
                citation_count = max(int(citation_count or 0), 0)
            except (TypeError, ValueError):
                citation_count = 0

            papers.append(
                {
                    "paper_id": paper_id,
                    "paper_entry_id": entry.paper_entry_id,
                    "document_id": document.document_id,
                    "title": entry.title or document.title,
                    "abstract": abstract,
                    "review_text": review_text,
                    "authors": authors,
                    "keywords": list(document.tags or []),
                    "publish_date": str(metadata.get("year", "") or ""),
                    "source": entry.origin,
                    "origin": entry.origin,
                    "status": entry.status,
                    "taxonomy_category": str(metadata.get("category", "") or ""),
                    "citation_count": citation_count,
                    "citation_count_known": "citation_count" in metadata,
                    "citation_source": str(metadata.get("citation_source", "") or ""),
                    "url": entry.source_url or str(metadata.get("source_url", "") or ""),
                    "doi": doi,
                    "references": list(metadata.get("references", []) or []),
                }
            )
        return papers, excluded_document_ids

    @staticmethod
    def _paper_text_context(content: str) -> tuple[str, str]:
        text = re.sub(r"(?im)^\[Page \d+\]\s*$", "", str(content or ""))
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            return "", ""

        abstract = ""
        match = re.search(r"\babstract\b[\s:.-]*", text, flags=re.IGNORECASE)
        if match:
            tail = text[match.end():]
            heading = re.search(
                r"\b(?:1[.\s]+)?(?:introduction|keywords|index terms)\b",
                tail,
                flags=re.IGNORECASE,
            )
            abstract = tail[: heading.start() if heading else 2500].strip()
        if not abstract:
            abstract = text[:2000].strip()
        return abstract[:3000], text[:6000]

    def _knowledge_query_for_task(
        self,
        *,
        task: ResearchTask,
        conversation_topic: str,
        recent_context: list[dict[str, Any]],
        workspace_hints: list[str],
        query_intent: QueryIntent,
        working_memory_summary: str,
        working_memory_findings: list[str],
        working_memory_open_questions: list[str],
    ) -> str:
        parts: list[str] = []
        seen: set[str] = set()

        def add_part(value: str, *, max_length: int) -> None:
            cleaned = clean_internal_context_text(value, max_length=max_length)
            if not cleaned:
                return
            key = cleaned.casefold()
            if key in seen:
                return
            seen.add(key)
            parts.append(cleaned)

        add_part(build_search_seed(query_intent, fallback_topic=task.topic), max_length=180)
        add_part(query_intent.raw_user_request, max_length=160)
        add_part(conversation_topic, max_length=140)
        for label in query_intent.paper_scope[:2]:
            add_part(label, max_length=80)
        for term in query_intent.focus_terms[:2]:
            add_part(term, max_length=80)
        for hint in workspace_hints[:2]:
            add_part(hint, max_length=100)
        add_part(working_memory_summary, max_length=140)
        for finding in working_memory_findings[:2]:
            add_part(finding, max_length=120)
        for question in working_memory_open_questions[:1]:
            add_part(question, max_length=120)
        for entry in recent_context:
            if entry.get("role") != "user":
                continue
            add_part(str(entry.get("content", "")), max_length=120)
        query = " ".join(parts[:6]).strip()
        return query or task.topic

    @staticmethod
    def _raw_user_request_for_task(task: ResearchTask, *, recent_context: list[dict[str, Any]]) -> str:
        trigger_message_id = str(getattr(task, "trigger_message_id", "") or "").strip()
        if trigger_message_id:
            for entry in reversed(recent_context):
                if str(entry.get("message_id", "")).strip() != trigger_message_id:
                    continue
                if str(entry.get("role", "")).lower() != "user":
                    continue
                content = clean_internal_context_text(entry.get("content", ""), max_length=220)
                if content:
                    return content

        for entry in reversed(recent_context):
            if str(entry.get("role", "")).lower() != "user":
                continue
            content = clean_internal_context_text(entry.get("content", ""), max_length=220)
            if content:
                return content
        return clean_internal_context_text(task.topic, max_length=220) or task.topic

    @staticmethod
    def _serialize_knowledge_hit(hit: KnowledgeHit) -> dict[str, Any]:
        return {
            "document_id": hit.document_id,
            "title": hit.title,
            "snippet": hit.snippet,
            "score": float(hit.score),
            "scope": hit.scope,
            "source_task_id": hit.source_task_id,
            "source_type": hit.source_type,
            "evidence_level": hit.evidence_level,
            "matched_chunk_count": int(hit.matched_chunk_count),
            "supporting_snippets": list(hit.supporting_snippets),
        }

    def _previous_round_context_for_task(self, task: ResearchTask) -> dict[str, Any]:
        current_created_at = _datetime_order_value(
            getattr(task, "created_at", None)
        )
        previous_tasks = sorted(
            [
                item
                for item in self.task_repository.list_all()
                if item.conversation_id == task.conversation_id
                and item.task_id != task.task_id
                and _datetime_order_value(getattr(item, "created_at", None))
                < current_created_at
            ],
            key=lambda item: (
                _datetime_order_value(getattr(item, "created_at", None)),
                _datetime_order_value(getattr(item, "updated_at", None)),
            ),
            reverse=True,
        )
        if not previous_tasks:
            return {"task_id": "", "paper_ids": [], "papers": [], "query_intent": {}}

        previous_task = None
        workspace = None
        for candidate in previous_tasks:
            candidate_workspace = self.workspace_repository.get_by_task(candidate.task_id)
            if candidate_workspace is None:
                continue
            previous_task = candidate
            workspace = candidate_workspace
            break
        if previous_task is None or workspace is None:
            return {"task_id": "", "paper_ids": [], "papers": [], "query_intent": {}}

        paper_ids = [str(getattr(paper, "paper_id", "")).strip() for paper in workspace.papers if str(getattr(paper, "paper_id", "")).strip()]
        papers = [
            {
                "paper_id": str(getattr(paper, "paper_id", "") or "").strip(),
                "title": str(getattr(paper, "title", "") or ""),
                "abstract": str(getattr(paper, "abstract", "") or ""),
                "review_text": str(getattr(paper, "review_text", "") or ""),
                "authors": list(getattr(paper, "authors", []) or []),
                "keywords": list(getattr(paper, "keywords", []) or []),
                "publish_date": str(getattr(paper, "publish_date", "") or ""),
                "source": str(getattr(paper, "source", "") or ""),
                "taxonomy_category": str(getattr(paper, "taxonomy_category", "") or ""),
                "citation_count": int(getattr(paper, "citation_count", 0) or 0),
                "citation_count_known": bool(
                    getattr(paper, "citation_count_known", False)
                ),
                "citation_source": str(
                    getattr(paper, "citation_source", "") or ""
                ),
                "url": str(getattr(paper, "url", "") or ""),
                "relevance_score": float(
                    getattr(paper, "relevance_score", 0.0) or 0.0
                ),
                "relevance_tier": str(
                    getattr(paper, "relevance_tier", "candidate") or "candidate"
                ),
                "relevance_reasons": list(
                    getattr(paper, "relevance_reasons", []) or []
                ),
                "paper_pool_status": str(
                    getattr(paper, "paper_pool_status", "") or ""
                ),
                "document_id": str(getattr(paper, "document_id", "") or ""),
                "origin": str(getattr(paper, "origin", "") or ""),
            }
            for paper in workspace.papers
            if str(getattr(paper, "paper_id", "") or "").strip()
        ]
        query_intent = {}
        trace = getattr(workspace, "trace", {}) or {}
        context_inputs = trace.get("context_inputs", []) if isinstance(trace, dict) else []
        for entry in reversed(context_inputs):
            if isinstance(entry, dict) and str(entry.get("kind", "")).strip() == "query_intent":
                query_intent = dict(entry)
                break
        return {
            "task_id": previous_task.task_id,
            "paper_ids": paper_ids,
            "papers": papers,
            "query_intent": query_intent,
        }

    def _conversation_workspace_hints(self, conversation_id: str) -> list[str]:
        if self.workspace_service is None:
            return []
        try:
            return self.workspace_service.get_conversation_workspace_hints(conversation_id)
        except Exception:
            return []

    def _conversation_workspace_summary(self, conversation_id: str) -> str:
        if self.workspace_service is None:
            return ""
        try:
            snapshot = self.workspace_service.get_conversation_workspace_snapshot(conversation_id)
        except Exception:
            return ""
        if snapshot is None:
            return ""
        return clean_internal_context_text(getattr(snapshot, "summary", ""), max_length=280)

    def _conversation_working_memory(self, conversation_id: str):
        if self.working_memory_service is None:
            return None
        try:
            return self.working_memory_service.get_conversation_memory(conversation_id)
        except Exception:
            return None


def _datetime_order_value(value: Any) -> float:
    if not isinstance(value, datetime):
        return float("-inf")
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.timestamp()

