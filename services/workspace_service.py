from __future__ import annotations

import hashlib
import os
import re
from concurrent.futures import ThreadPoolExecutor
from collections import OrderedDict, defaultdict
from copy import deepcopy

from product_agent.repositories import ConversationRepository, ResearchTaskRepository, WorkspaceRepository
from product_agent.schemas import (
    WorkspaceBriefItemView,
    WorkspaceBriefPaperView,
    WorkspacePaperClaimCheckView,
    WorkspaceEvidenceStatusView,
    WorkspaceEvidenceSnapshotView,
    WorkspaceGapView,
    WorkspaceGraphEdgeView,
    WorkspaceInheritedContextView,
    WorkspaceIdeaView,
    WorkspaceKnowledgeHitView,
    WorkspacePaperBriefView,
    WorkspacePaperView,
    WorkspaceResearchBriefView,
    WorkspaceSnapshotResponse,
    WorkspaceSourceTraceView,
    WorkspaceTraceView,
    WorkspaceWorkingMemoryView,
)
from product_agent.services.text_cleaning import clean_internal_context_items, clean_internal_context_text
from product_agent.services.conversation_synthesis_service import (
    select_conversation_core_paper_ids,
    synthesize_conversation_overview,
)
from product_agent.services.claim_verification_service import (
    extract_full_text_claim_candidates,
    summarize_full_text_verification,
    verify_claim_against_full_text,
)
from product_agent.services.brief_compression_service import compress_research_brief_with_llm
from product_agent.services.paper_brief_llm_service import (
    enhance_paper_brief_with_llm,
    paper_brief_llm_enabled,
)


_CONV_CACHE_MAX_SIZE = 128
_GENERIC_RELEVANCE_LABELS = {
    "abstract",
    "adjacent",
    "background",
    "benchmark",
    "candidate",
    "category",
    "citation",
    "dataset",
    "direct",
    "evaluation",
    "evidence",
    "focus",
    "high",
    "keyword",
    "keywords",
    "llm",
    "method",
    "metadata",
    "multimodal",
    "paper",
    "process",
    "query",
    "recent",
    "relevance",
    "relevant",
    "retrieval",
    "score",
    "selected",
    "survey",
    "team",
    "title",
    "user",
    "workflow",
}


class WorkspaceService:
    """
    负责工作台数据的读取、聚合与导出前整理。

    当前目标：
    - 对外优先返回稳定的 `WorkspaceSnapshotResponse`
    - 避免 handler 或前端继续理解 domain object 细节
    """

    def __init__(
        self,
        repository: WorkspaceRepository,
        conversation_repository: ConversationRepository | None = None,
        task_repository: ResearchTaskRepository | None = None,
        working_memory_service=None,
    ) -> None:
        self.repository = repository
        self.conversation_repository = conversation_repository
        self.task_repository = task_repository
        self.working_memory_service = working_memory_service
        # conversation 总 workspace 缓存：conv_id -> (latest_task_ts, snapshot)
        self._conv_ws_cache: OrderedDict[str, tuple[str, WorkspaceSnapshotResponse]] = OrderedDict()

    def invalidate_conversation_cache(self, conversation_id: str) -> None:
        """当 conversation 下有新 task 完成时调用，使对应缓存失效。"""
        self._conv_ws_cache.pop(conversation_id, None)

    def _get_conversation_latest_ts(self, conversation_id: str) -> str:
        """获取 conversation 下所有 task 的最新更新时间戳，用于缓存键。"""
        if self.task_repository is None:
            return ""
        tasks = [
            t for t in self.task_repository.list_all()
            if t.conversation_id == conversation_id
        ]
        if not tasks:
            return ""
        return max(t.updated_at.isoformat() for t in tasks)

    def get_workspace(self, task_id: str):
        """根据 `task_id` 读取工作台 domain 对象。"""
        return self.repository.get_by_task(task_id)

    def get_workspace_snapshot(self, task_id: str) -> WorkspaceSnapshotResponse | None:
        """根据 `task_id` 读取并投影为前端稳定消费的工作台响应。"""
        workspace = self.repository.get_by_task(task_id)
        if workspace is None:
            return None
        workspace = self._inherit_previous_paper_metadata(task_id, workspace)

        trace = workspace.trace or {}
        evidence_status = _build_evidence_status(workspace)
        summary = _normalize_workspace_summary(
            topic=workspace.topic,
            summary=workspace.summary,
            summary_payload=workspace.summary_payload or {},
        )
        source_trace = _build_source_trace_view(
            summary_payload=workspace.summary_payload or {},
            trace=trace,
        )
        inherited_context = _build_inherited_context_view(trace)
        working_memory = self._workspace_working_memory(task_id=task_id)
        evidence_snapshot = _build_evidence_snapshot_view(workspace.summary_payload or {})
        analysis_paper_ids = _workspace_analysis_paper_ids(workspace)
        research_brief = _build_workspace_research_brief(
            mode="task",
            topic=workspace.topic,
            task_id=workspace.task_id,
            summary=summary,
            papers=workspace.papers,
            analysis_paper_ids=analysis_paper_ids,
            taxonomy=workspace.taxonomy,
            gaps=workspace.gaps,
            ideas=workspace.ideas,
            evidence_status=evidence_status,
            source_trace=source_trace,
        )
        return WorkspaceSnapshotResponse(
            task_id=workspace.task_id,
            topic=workspace.topic,
            summary=summary,
            research_brief=research_brief,
            papers=_workspace_paper_views(workspace.papers, topic=workspace.topic),
            analysis_paper_ids=analysis_paper_ids,
            taxonomy=workspace.taxonomy,
            graph_edges=[
                WorkspaceGraphEdgeView(
                    source=str(edge.get("source", "")),
                    target=str(edge.get("target", "")),
                    relationship=str(edge.get("relationship", "")),
                    reasoning=str(edge.get("reasoning", "")),
                    provenance=str(edge.get("provenance", "")),
                    confidence=float(edge.get("confidence", 0.0) or 0.0),
                    evidence_level=str(edge.get("evidence_level", "candidate")),
                    evidence=str(edge.get("evidence", "")),
                    evidence_snippets=[
                        str(item) for item in edge.get("evidence_snippets", []) if str(item).strip()
                    ],
                    evidence_details=[
                        dict(item)
                        for item in edge.get("evidence_details", [])
                        if isinstance(item, dict)
                    ],
                )
                for edge in _visible_workspace_graph_edges(workspace.graph_edges)
            ],
            gaps=[
                WorkspaceGapView(
                    summary=gap.summary,
                    severity=gap.severity,
                    evidence=list(gap.evidence),
                    supporting_paper_ids=list(gap.supporting_paper_ids),
                    evidence_level=gap.evidence_level,
                    evidence_reason=gap.evidence_reason,
                )
                for gap in workspace.gaps
            ],
            ideas=[
                WorkspaceIdeaView(
                    title=idea.title,
                    motivation=idea.motivation,
                    approach=idea.approach,
                    feasibility=idea.feasibility,
                    contribution=idea.contribution,
                    supporting_paper_ids=list(idea.supporting_paper_ids),
                    evidence_level=idea.evidence_level,
                    evidence_reason=idea.evidence_reason,
                    raw_text="",
                )
                for idea in workspace.ideas
            ],
            alignment_score=workspace.alignment_score,
            evidence_status=WorkspaceEvidenceStatusView(**evidence_status),
            evidence_snapshot=evidence_snapshot,
            source_trace=source_trace,
            inherited_context=inherited_context,
            working_memory=working_memory,
            trace=WorkspaceTraceView(
                thought_trace=_normalize_trace_entries(trace.get("thought_trace", [])),
                action_history=_normalize_trace_entries(trace.get("action_history", [])),
                context_inputs=_normalize_trace_entries(trace.get("context_inputs", [])),
                run_status=str(trace.get("run_status", "completed") or "completed"),
                termination_reason=str(trace.get("termination_reason", "") or ""),
                degraded_reason=str(trace.get("degraded_reason", "") or ""),
                repair_count=int(trace.get("repair_count", 0) or 0),
                max_repair_rounds=int(trace.get("max_repair_rounds", 0) or 0),
                repair_stop_reason=str(trace.get("repair_stop_reason", "") or ""),
                repair_history=list(trace.get("repair_history", [])),
            ),
        )

    def verify_workspace_paper(self, task_id: str, paper_id: str) -> WorkspacePaperView | None:
        """按需把某篇论文升级成更深的正文片段级 Paper Brief。"""
        workspace = self.repository.get_by_task(task_id)
        if workspace is None:
            return None
        workspace = self._inherit_previous_paper_metadata(task_id, workspace)
        normalized_paper_id = str(paper_id or "").strip()
        for paper in workspace.papers:
            if str(getattr(paper, "paper_id", "") or "").strip() == normalized_paper_id:
                return _workspace_paper_view(
                    paper,
                    topic=workspace.topic,
                    verification_mode="full",
                    paper_brief_llm_slot=1,
                )
        return None

    def _inherit_previous_paper_metadata(self, task_id: str, workspace):
        if self.task_repository is None:
            return workspace
        current_task = self.task_repository.get(task_id)
        if current_task is None:
            return workspace

        previous_tasks = sorted(
            (
                task
                for task in self.task_repository.list_all()
                if task.task_id != current_task.task_id
                and task.created_at < current_task.created_at
            ),
            key=lambda task: task.created_at,
            reverse=True,
        )
        previous_workspaces = [
            previous_workspace
            for task in previous_tasks
            if (previous_workspace := self.repository.get_by_task(task.task_id))
            is not None
        ]
        if not previous_workspaces:
            return workspace

        historical_by_id = {
            paper.paper_id: paper
            for paper in _merge_workspace_papers(previous_workspaces)
        }
        enriched = deepcopy(workspace)
        enriched.papers = [
            _inherit_workspace_paper_metadata(historical_by_id[paper.paper_id], paper)
            if paper.paper_id in historical_by_id
            else paper
            for paper in enriched.papers
        ]
        return enriched

    def get_conversation_workspace_snapshot(self, conversation_id: str) -> WorkspaceSnapshotResponse | None:
        """
        Build a conversation-level aggregated workspace by merging all completed
        task workspaces under the same conversation.

        Results are cached using the conversation's latest task timestamp as key.
        Call invalidate_conversation_cache() when a new task completes.
        """
        # Cache check: if no task changes since last compute, reuse cached result
        latest_ts = self._get_conversation_latest_ts(conversation_id)
        if conversation_id in self._conv_ws_cache:
            cached_ts, cached = self._conv_ws_cache[conversation_id]
            if cached_ts == latest_ts:
                self._conv_ws_cache.move_to_end(conversation_id)
                return cached

        if self.conversation_repository is not None:
            conversation = self.conversation_repository.get(conversation_id)
            if conversation is None:
                return None
            topic = conversation.topic
        else:
            topic = conversation_id

        if self.task_repository is None:
            return None

        tasks = [
            task
            for task in self.task_repository.list_all()
            if task.conversation_id == conversation_id
            and task.status in {"completed", "degraded"}
        ]
        if not tasks:
            return None

        tasks.sort(key=lambda item: item.updated_at, reverse=True)
        workspaces = [
            self._inherit_previous_paper_metadata(task.task_id, workspace)
            if workspace is not None
            else None
            for task in tasks
            for workspace in [self.repository.get_by_task(task.task_id)]
        ]
        valid_workspaces = [workspace for workspace in workspaces if workspace is not None]
        if not valid_workspaces:
            return None

        merged_papers = _merge_workspace_papers(valid_workspaces)
        merged_graph_edges = _merge_workspace_graph_edges(valid_workspaces)
        merged_gaps = _merge_workspace_gaps(valid_workspaces)
        merged_ideas = _merge_workspace_ideas(valid_workspaces)
        merged_taxonomy = _merge_workspace_taxonomy(valid_workspaces)
        merged_trace = _merge_workspace_trace(valid_workspaces, tasks)
        merged_alignment = round(
            sum(workspace.alignment_score for workspace in valid_workspaces) / len(valid_workspaces), 3
        )
        conversation_synthesis = synthesize_conversation_overview(
            topic=topic,
            workspaces=valid_workspaces,
            papers=merged_papers,
            gaps=merged_gaps,
            ideas=merged_ideas,
        )
        llm_core_paper_ids = select_conversation_core_paper_ids(
            topic=topic,
            workspaces=valid_workspaces,
            papers=merged_papers,
        )
        conversation_analysis_paper_ids = _select_conversation_analysis_paper_ids(
            workspaces=valid_workspaces,
            papers=merged_papers,
            llm_recommended_paper_ids=llm_core_paper_ids,
        )
        merged_summary_payload = _build_conversation_summary_payload(
            topic=topic,
            workspaces=valid_workspaces,
            papers=merged_papers,
            gaps=merged_gaps,
            ideas=merged_ideas,
            alignment_score=merged_alignment,
            conversation_synthesis=conversation_synthesis,
            analysis_paper_ids=conversation_analysis_paper_ids,
        )
        merged_summary = _merge_workspace_summaries(
            topic=topic,
            workspaces=valid_workspaces,
            paper_count=len(merged_papers),
            gap_count=len(merged_gaps),
            idea_count=len(merged_ideas),
            conversation_synthesis=conversation_synthesis,
        )

        synthetic_workspace = type("ConversationWorkspaceProjection", (), {})()
        synthetic_workspace.task_id = f"conversation::{conversation_id}"
        synthetic_workspace.topic = topic
        synthetic_workspace.summary = merged_summary
        synthetic_workspace.summary_payload = merged_summary_payload
        synthetic_workspace.papers = merged_papers
        synthetic_workspace.taxonomy = merged_taxonomy
        synthetic_workspace.graph_edges = merged_graph_edges
        synthetic_workspace.gaps = merged_gaps
        synthetic_workspace.ideas = merged_ideas
        synthetic_workspace.alignment_score = merged_alignment
        synthetic_workspace.trace = merged_trace

        trace = synthetic_workspace.trace or {}
        evidence_status = _build_evidence_status(synthetic_workspace)
        source_trace = _build_source_trace_view(
            summary_payload=synthetic_workspace.summary_payload or {},
            trace=trace,
        )
        inherited_context = _build_inherited_context_view(trace)
        working_memory = self._conversation_working_memory_view(conversation_id)
        evidence_snapshot = _build_evidence_snapshot_view(synthetic_workspace.summary_payload or {})
        analysis_paper_ids = _workspace_analysis_paper_ids(synthetic_workspace)
        research_brief = _build_workspace_research_brief(
            mode="conversation",
            topic=synthetic_workspace.topic,
            task_id=synthetic_workspace.task_id,
            summary=synthetic_workspace.summary,
            papers=synthetic_workspace.papers,
            analysis_paper_ids=analysis_paper_ids,
            taxonomy=synthetic_workspace.taxonomy,
            gaps=synthetic_workspace.gaps,
            ideas=synthetic_workspace.ideas,
            evidence_status=evidence_status,
            source_trace=source_trace,
            workspaces=valid_workspaces,
            conversation_synthesis=conversation_synthesis,
        )
        result = WorkspaceSnapshotResponse(
            task_id=synthetic_workspace.task_id,
            topic=synthetic_workspace.topic,
            summary=synthetic_workspace.summary,
            research_brief=research_brief,
            papers=_workspace_paper_views(
                synthetic_workspace.papers,
                topic=synthetic_workspace.topic,
                force_not_new=True,
            ),
            analysis_paper_ids=analysis_paper_ids,
            taxonomy=synthetic_workspace.taxonomy,
            graph_edges=[
                WorkspaceGraphEdgeView(
                    source=str(edge.get("source", "")),
                    target=str(edge.get("target", "")),
                    relationship=str(edge.get("relationship", "")),
                    reasoning=str(edge.get("reasoning", "")),
                    provenance=str(edge.get("provenance", "")),
                    confidence=float(edge.get("confidence", 0.0) or 0.0),
                    evidence_level=str(edge.get("evidence_level", "candidate")),
                    evidence=str(edge.get("evidence", "")),
                    evidence_snippets=[
                        str(item)
                        for item in edge.get("evidence_snippets", [])
                        if str(item).strip()
                    ],
                    evidence_details=[
                        dict(item)
                        for item in edge.get("evidence_details", [])
                        if isinstance(item, dict)
                    ],
                )
                for edge in _visible_workspace_graph_edges(
                    synthetic_workspace.graph_edges
                )
            ],
            gaps=[
                WorkspaceGapView(
                    summary=gap.summary,
                    severity=gap.severity,
                    evidence=list(gap.evidence),
                    supporting_paper_ids=list(gap.supporting_paper_ids),
                    evidence_level=gap.evidence_level,
                    evidence_reason=gap.evidence_reason,
                )
                for gap in synthetic_workspace.gaps
            ],
            ideas=[
                WorkspaceIdeaView(
                    title=idea.title,
                    motivation=idea.motivation,
                    approach=idea.approach,
                    feasibility=idea.feasibility,
                    contribution=idea.contribution,
                    supporting_paper_ids=list(idea.supporting_paper_ids),
                    evidence_level=idea.evidence_level,
                    evidence_reason=idea.evidence_reason,
                    raw_text="",
                )
                for idea in synthetic_workspace.ideas
            ],
            alignment_score=synthetic_workspace.alignment_score,
            evidence_status=WorkspaceEvidenceStatusView(**evidence_status),
            evidence_snapshot=evidence_snapshot,
            source_trace=source_trace,
            inherited_context=inherited_context,
            working_memory=working_memory,
            trace=WorkspaceTraceView(
                thought_trace=_normalize_trace_entries(trace.get("thought_trace", [])),
                action_history=_normalize_trace_entries(trace.get("action_history", [])),
                context_inputs=_normalize_trace_entries(trace.get("context_inputs", [])),
            ),
        )

        # Write cache
        self._conv_ws_cache[conversation_id] = (latest_ts, result)
        self._conv_ws_cache.move_to_end(conversation_id)
        if len(self._conv_ws_cache) > _CONV_CACHE_MAX_SIZE:
            self._conv_ws_cache.popitem(last=False)

        return result

    def get_conversation_workspace_hints(
        self,
        conversation_id: str,
        *,
        max_branches: int = 3,
        max_gaps: int = 2,
        max_papers: int = 2,
    ) -> list[str]:
        """
        Extract concise, reusable hints from the aggregated conversation workspace.

        These hints are intended for the next follow-up round so planner/searcher
        can reuse the conversation's strongest branches, gaps, and representative
        papers instead of restarting from zero.
        """
        snapshot = self.get_conversation_workspace_snapshot(conversation_id)
        if snapshot is None:
            return []

        hints: list[str] = []
        seen: set[str] = set()

        def add_hint(value: str, *, max_length: int = 90) -> None:
            text = clean_internal_context_text(value, max_length=max_length)
            if not text:
                return
            normalized = text.lower()
            if normalized in seen:
                return
            seen.add(normalized)
            hints.append(text)

        evidence_status = snapshot.evidence_status
        if snapshot.working_memory is not None:
            if snapshot.working_memory.current_focus:
                add_hint(snapshot.working_memory.current_focus, max_length=100)
            for finding in snapshot.working_memory.stable_findings[:max_branches]:
                add_hint(finding, max_length=100)
            for question in snapshot.working_memory.open_questions[:max_gaps]:
                add_hint(question, max_length=110)

        for branch_name in list(evidence_status.candidate_branches or [])[:max_branches]:
            add_hint(branch_name, max_length=80)

        branch_hints_added = len(hints)
        for branch in snapshot.taxonomy.get("branches", []) or []:
            if branch_hints_added >= max_branches:
                break
            branch_name = str(branch.get("name", "") or "").strip()
            paper_count = int(branch.get("paper_count", 0) or 0)
            if branch_name and paper_count > 0:
                add_hint(branch_name, max_length=80)
                branch_hints_added = len(hints)

        for gap in snapshot.gaps[:max_gaps]:
            add_hint(_gap_hint_from_summary(gap.summary), max_length=100)

        for paper in snapshot.papers[:max_papers]:
            add_hint(paper.title, max_length=100)

        return clean_internal_context_items(hints, max_length=100)

    def _workspace_working_memory(self, *, task_id: str) -> WorkspaceWorkingMemoryView | None:
        if self.task_repository is None:
            return None
        task = self.task_repository.get(task_id)
        if task is None:
            return None
        return self._conversation_working_memory_view(task.conversation_id)

    def _conversation_working_memory_view(self, conversation_id: str) -> WorkspaceWorkingMemoryView | None:
        if self.working_memory_service is None:
            return None
        try:
            memory = self.working_memory_service.get_conversation_memory(conversation_id)
        except Exception:
            return None
        if memory is None:
            return None
        return WorkspaceWorkingMemoryView(
            current_focus=clean_internal_context_text(memory.current_focus, max_length=180),
            summary=clean_internal_context_text(memory.summary, max_length=320),
            stable_findings=clean_internal_context_items(list(memory.stable_findings), max_length=140),
            open_questions=clean_internal_context_items(list(memory.open_questions), max_length=180),
            active_constraints=clean_internal_context_items(list(memory.active_constraints), max_length=140),
            supporting_task_ids=[str(task_id).strip() for task_id in memory.supporting_task_ids if str(task_id).strip()][:8],
            source_task_id=(str(memory.source_task_id).strip() or None) if memory.source_task_id else None,
            updated_at=memory.updated_at.isoformat(),
        )


def _build_evidence_status(workspace) -> dict:
    papers = list(workspace.papers or [])
    total_papers = len(papers)
    fallback_papers = [paper for paper in papers if (paper.source or "").lower() in {"fallback", "seed"}]
    fallback_paper_count = len(fallback_papers)
    real_paper_count = total_papers - fallback_paper_count
    fallback_ratio = round(fallback_paper_count / total_papers, 3) if total_papers else 0.0

    taxonomy = workspace.taxonomy or {}
    coverage = taxonomy.get("coverage", {}) or {}
    branches = taxonomy.get("branches", []) or []
    covered_branch_count = sum(
        1 for entry in coverage.values() if isinstance(entry, dict) and int(entry.get("paper_count", 0) or 0) > 0
    )

    branch_rankings = []
    for branch in branches:
        branch_id = str(branch.get("branch_id", "") or "")
        branch_name = str(branch.get("name", "") or "").strip()
        branch_coverage = coverage.get(branch_id, {}) or {}
        branch_rankings.append(
            (
                int(branch_coverage.get("paper_count", branch.get("paper_count", 0)) or 0),
                float(branch_coverage.get("coverage_score", 0.0) or 0.0),
                branch_name,
            )
        )
    branch_rankings.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    candidate_branches = [name for paper_count, _, name in branch_rankings if name and paper_count > 0][:4]

    insufficient = total_papers == 0 or real_paper_count < 3 or fallback_ratio >= 0.5
    if insufficient:
        if total_papers == 0:
            message = (
                "当前没有检索到可用论文证据，本轮只适合展示初步证据摘要与补证建议，"
                "不适合继续生成完整 taxonomy。"
            )
        elif fallback_paper_count:
            message = (
                f"当前仅有 {real_paper_count} 篇真实论文，且包含 {fallback_paper_count} 篇系统回退论文。"
                "这更像 evidence summary，不适合作为完整 taxonomy 成果。"
            )
        else:
            message = (
                f"当前只有 {real_paper_count} 篇真实论文，证据过薄。建议继续缩小问题、补充论文，"
                "或导入已有知识后再生成 taxonomy。"
            )
    else:
        message = "当前证据量已达到可解释 taxonomy 的最低门槛。"

    return {
        "insufficient": insufficient,
        "total_papers": total_papers,
        "real_paper_count": real_paper_count,
        "fallback_paper_count": fallback_paper_count,
        "fallback_ratio": fallback_ratio,
        "covered_branch_count": covered_branch_count,
        "candidate_branches": candidate_branches,
        "message": message,
    }


def _build_evidence_snapshot_view(
    summary_payload: dict,
) -> WorkspaceEvidenceSnapshotView | None:
    if not isinstance(summary_payload, dict):
        return None
    if summary_payload.get("aggregation_mode") == "conversation_workspace":
        return None
    snapshot = summary_payload.get("evidence_snapshot", {})
    if not isinstance(snapshot, dict) or not snapshot.get("snapshot_id"):
        return None
    return WorkspaceEvidenceSnapshotView(
        snapshot_id=str(snapshot.get("snapshot_id", "") or ""),
        version=str(snapshot.get("version", "") or "v1"),
        created_at=str(snapshot.get("created_at", "") or ""),
        topic=str(snapshot.get("topic", "") or ""),
        stats=dict(snapshot.get("stats", {}) or {}),
        retrieval_plan=dict(snapshot.get("retrieval_plan", {}) or {}),
        retrieval_outcome=dict(snapshot.get("retrieval_outcome", {}) or {}),
        alignment_score=float(snapshot.get("alignment_score", 0.0) or 0.0),
    )


def _workspace_paper_views(papers, *, topic: str, force_not_new: bool = False) -> list[WorkspacePaperView]:
    paper_list = list(papers or [])
    llm_slots = _paper_brief_llm_slots(paper_list)
    if not _workspace_paper_parallel_enabled(len(paper_list)):
        return [
            _workspace_paper_view(
                paper,
                topic=topic,
                force_not_new=force_not_new,
                paper_brief_llm_slot=llm_slots.get(id(paper), 0),
            )
            for paper in paper_list
        ]

    workers = _workspace_paper_worker_count(len(paper_list))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        return list(
            executor.map(
                lambda paper: _workspace_paper_view(
                    paper,
                    topic=topic,
                    force_not_new=force_not_new,
                    paper_brief_llm_slot=llm_slots.get(id(paper), 0),
                ),
                paper_list,
            )
        )


def _workspace_paper_parallel_enabled(paper_count: int) -> bool:
    if paper_count < 2 or os.environ.get("DISABLE_WORKSPACE_PAPER_PARALLEL") == "1":
        return False
    if os.environ.get("ENABLE_WORKSPACE_PAPER_PARALLEL") == "1":
        return True
    return paper_brief_llm_enabled() and paper_count >= 2


def _workspace_paper_worker_count(paper_count: int) -> int:
    raw = os.environ.get("WORKSPACE_PAPER_BRIEF_WORKERS", "4")
    try:
        configured = int(raw)
    except (TypeError, ValueError):
        configured = 4
    return max(1, min(configured, paper_count, 8))


def _paper_brief_llm_slots(papers) -> dict[int, int]:
    paper_list = list(papers or [])
    if not paper_brief_llm_enabled():
        return {}
    limit = _paper_brief_llm_max_per_workspace()
    if limit <= 0:
        return {}

    candidates = [
        (_paper_brief_llm_priority(paper), index, paper)
        for index, paper in enumerate(paper_list)
        if _paper_has_brief_evidence(paper)
    ]
    candidates = [
        (score, index, paper)
        for score, index, paper in candidates
        if score > 0
    ]
    candidates.sort(key=lambda item: (-item[0], item[1]))
    return {
        id(paper): slot
        for slot, (_, _, paper) in enumerate(candidates[:limit], start=1)
    }


def _paper_brief_llm_max_per_workspace() -> int:
    raw = os.environ.get("PAPER_BRIEF_LLM_MAX_PER_WORKSPACE", "4")
    try:
        configured = int(raw)
    except (TypeError, ValueError):
        configured = 4
    return max(0, min(configured, 12))


def _paper_has_brief_evidence(paper) -> bool:
    return bool(
        str(getattr(paper, "review_text", "") or "").strip()
        or str(getattr(paper, "abstract", "") or "").strip()
    )


def _paper_brief_llm_priority(paper) -> float:
    score = float(getattr(paper, "relevance_score", 0.0) or 0.0) * 10
    if _is_user_uploaded_paper(paper):
        score += 120
    if str(getattr(paper, "paper_pool_status", "") or "").casefold() == "core":
        score += 80
    if bool(getattr(paper, "is_new_this_round", False)):
        score += 50
    tier = str(getattr(paper, "relevance_tier", "") or "").casefold()
    if tier == "direct":
        score += 35
    elif tier == "adjacent":
        score += 10
    if str(getattr(paper, "review_text", "") or "").strip():
        score += 20
    if str(getattr(paper, "abstract", "") or "").strip():
        score += 5
    if bool(getattr(paper, "citation_count_known", False)):
        score += min(max(int(getattr(paper, "citation_count", 0) or 0), 0) / 100, 5)
    return score


def _workspace_paper_view(
    paper,
    *,
    topic: str,
    force_not_new: bool = False,
    paper_brief_llm_slot: int = 0,
    verification_mode: str = "standard",
) -> WorkspacePaperView:
    return WorkspacePaperView(
        paper_id=str(getattr(paper, "paper_id", "") or ""),
        title=str(getattr(paper, "title", "") or ""),
        publish_date=str(getattr(paper, "publish_date", "") or ""),
        source=str(getattr(paper, "source", "") or ""),
        taxonomy_category=str(getattr(paper, "taxonomy_category", "") or ""),
        citation_count=max(int(getattr(paper, "citation_count", 0) or 0), 0),
        citation_count_known=bool(getattr(paper, "citation_count_known", False)),
        citation_source=str(getattr(paper, "citation_source", "") or ""),
        url=str(getattr(paper, "url", "") or ""),
        is_new_this_round=False if force_not_new else bool(getattr(paper, "is_new_this_round", False)),
        relevance_score=float(getattr(paper, "relevance_score", 0.0) or 0.0),
        relevance_tier=str(getattr(paper, "relevance_tier", "candidate") or "candidate"),
        relevance_reasons=list(getattr(paper, "relevance_reasons", []) or []),
        paper_pool_status=str(getattr(paper, "paper_pool_status", "") or ""),
        document_id=str(getattr(paper, "document_id", "") or ""),
        origin=str(getattr(paper, "origin", "") or ""),
        paper_brief=_build_workspace_paper_brief(
            paper,
            topic=topic,
            paper_brief_llm_slot=paper_brief_llm_slot,
            verification_mode=verification_mode,
        ),
    )


def _build_workspace_paper_brief(
    paper,
    *,
    topic: str,
    paper_brief_llm_slot: int = 0,
    verification_mode: str = "standard",
) -> WorkspacePaperBriefView:
    title = _clean_brief_text(getattr(paper, "title", ""), 180)
    raw_review_text = str(getattr(paper, "review_text", "") or "")
    review_text = _clean_brief_text(raw_review_text, 2500)
    full_verification = verification_mode == "full"
    claim_review_text = raw_review_text[:18000] if full_verification and raw_review_text.strip() else ""
    abstract = _clean_brief_text(getattr(paper, "abstract", ""), 520)
    category = _clean_brief_text(getattr(paper, "taxonomy_category", ""), 100)
    reasons = [
        _clean_brief_text(reason, 140)
        for reason in list(getattr(paper, "relevance_reasons", []) or [])
        if _clean_brief_text(reason, 140)
    ]
    tags = _paper_brief_tags(paper)
    if claim_review_text:
        source = "full_text_verified"
    elif review_text:
        source = "full_text"
    else:
        source = "abstract+metadata" if abstract else "metadata"
    problem = _paper_brief_problem(title=title, abstract=abstract, category=category, topic=topic)
    method = _paper_brief_method(title=title, abstract=abstract, tags=tags, paper=paper)
    contribution = _paper_brief_contribution(
        title=title,
        category=category,
        reasons=reasons,
        tags=tags,
        topic=topic,
    )
    limitation = _paper_brief_limitation(paper=paper, review_text=claim_review_text or review_text, abstract=abstract)
    relation_to_topic = _paper_brief_relation(category=category, reasons=reasons, topic=topic)
    selection_factors = _brief_paper_selection_factors(paper)
    why_selected = _paper_brief_why_selected(
        paper=paper,
        relation_to_topic=relation_to_topic,
        selection_factors=selection_factors,
    )
    read_focus = _paper_brief_read_focus(tags=tags, title=title, abstract=abstract)
    evidence_basis = _paper_brief_evidence_basis(
        paper=paper,
        source=source,
        selection_factors=selection_factors,
    )
    verification_boundary = _paper_brief_verification_boundary(
        paper=paper,
        source=source,
        review_text=claim_review_text or review_text,
        abstract=abstract,
    )
    brief = WorkspacePaperBriefView(
        problem=problem,
        method=method,
        contribution=contribution,
        limitation=limitation,
        relation_to_topic=relation_to_topic,
        why_selected=why_selected,
        read_focus=read_focus,
        evidence_basis=evidence_basis,
        verification_boundary=verification_boundary,
        tags=tags,
        source=source,
        claim_checks=_paper_claim_checks(
            paper=paper,
            title=title,
            review_text=claim_review_text,
            abstract=abstract,
            category=category,
            problem=problem,
            method=method,
            contribution=contribution,
            relation_to_topic=relation_to_topic,
            source=source,
        ),
    )
    if _should_enhance_paper_brief_with_llm(
        paper,
        source=source,
        paper_brief_llm_slot=paper_brief_llm_slot,
    ):
        return enhance_paper_brief_with_llm(
            topic=topic,
            paper_title=title,
            abstract=abstract,
            review_text=claim_review_text or review_text,
            brief=brief,
            selection_factors=selection_factors,
        )
    return brief


def _should_enhance_paper_brief_with_llm(
    paper,
    *,
    source: str,
    paper_brief_llm_slot: int,
) -> bool:
    if paper_brief_llm_slot <= 0:
        return False
    if source == "metadata":
        return False
    if _is_user_uploaded_paper(paper):
        return True
    if str(getattr(paper, "paper_pool_status", "") or "").casefold() == "core":
        return True
    if bool(getattr(paper, "is_new_this_round", False)):
        return True
    return str(getattr(paper, "relevance_tier", "") or "").casefold() == "direct"


def _paper_claim_checks(
    *,
    paper,
    title: str,
    review_text: str,
    abstract: str,
    category: str,
    problem: str,
    method: str,
    contribution: str,
    relation_to_topic: str,
    source: str,
) -> list[WorkspacePaperClaimCheckView]:
    has_full_text = source == "full_text_verified" and bool(review_text)
    source_level = (
        "full_text"
        if has_full_text
        else ("abstract" if abstract else "metadata")
    )
    section = "uploaded_text" if has_full_text else ("abstract" if abstract else "metadata")
    base_status = "partial" if (review_text or abstract) else "unknown"
    base_confidence = _claim_check_default_confidence(source_level=source_level, status=base_status)
    base_evidence = _paper_claim_evidence(
        title=title,
        review_text=review_text,
        abstract=abstract,
        category=category,
    )
    base_caveat = (
        "按需正文片段核查：已抽取局部 claim 并尝试定位支持证据，但仍需人工复核关键实验数值。"
        if has_full_text
        else (
        "摘要级核查：可支持快速筛读，但尚未定位正文实验、消融或局限段落。"
        if abstract
        else "元数据级核查：缺少摘要/正文片段，只能作为是否精读的候选判断。"
        )
    )
    checks: list[WorkspacePaperClaimCheckView] = []

    def add_check(claim_type: str, claim: str, *, status: str | None = None, caveat: str | None = None) -> None:
        clean_claim = _clean_brief_text(claim, 220)
        if not clean_claim or _looks_like_internal_relevance_signal(clean_claim):
            return
        if any(existing.claim == clean_claim for existing in checks):
            return
        fulltext_evidence = None
        if has_full_text and claim_type != "impact":
            fulltext_evidence = verify_claim_against_full_text(
                claim_type=claim_type,
                claim=clean_claim,
                full_text=review_text,
                title=title,
                category=category,
            )
        checks.append(
            WorkspacePaperClaimCheckView(
                claim_type=claim_type,
                claim=clean_claim,
                status=fulltext_evidence.status if fulltext_evidence else (status or base_status),
                evidence=fulltext_evidence.evidence if fulltext_evidence else base_evidence,
                source_level=fulltext_evidence.source_level if fulltext_evidence else source_level,
                section=fulltext_evidence.section if fulltext_evidence else section,
                page=fulltext_evidence.page if fulltext_evidence else 0,
                confidence=fulltext_evidence.confidence if fulltext_evidence else base_confidence,
                caveat=fulltext_evidence.caveat if fulltext_evidence else (caveat or base_caveat),
            )
        )

    add_check("problem", problem)
    add_check("method", method)
    add_check("contribution", contribution)
    if relation_to_topic:
        add_check(
            "topic_relation",
            relation_to_topic,
            status="partial" if review_text or abstract or category else "unknown",
        )
    candidate_claims = (
        [(candidate.claim_type, candidate.claim) for candidate in extract_full_text_claim_candidates(review_text)]
        if has_full_text
        else _paper_claim_candidates_from_text(abstract)
    )
    for claim_type, claim in candidate_claims:
        add_check(claim_type, claim, status="partial" if review_text or abstract else "unknown")
    if not bool(getattr(paper, "citation_count_known", False)):
        add_check(
            "impact",
            "当前无法用引用数判断论文影响力。",
            status="unknown",
            caveat="引用元数据未获取，不能把未获取误读为 0 引用。",
        )
    return checks[:8]


def _claim_check_default_confidence(*, source_level: str, status: str) -> float:
    if status == "verified":
        return 0.8
    if source_level == "full_text":
        return 0.58
    if source_level == "abstract":
        return 0.42
    return 0.25


def _paper_claim_candidates_from_text(text: str) -> list[tuple[str, str]]:
    clean_text = _clean_brief_text(text, 1400)
    if not clean_text:
        return []
    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?。！？])\s+", clean_text)
        if sentence.strip()
    ]
    candidates: list[tuple[str, str]] = []
    patterns = [
        (
            "method_claim",
            r"\b(propose|present|introduce|develop|design|align\w*|fus\w*|integrat\w*)\b|提出|设计|构建|开发|对齐|融合",
        ),
        (
            "evaluation_claim",
            r"\b(evaluate|experiment|benchmark|outperform|improve|achieve)\b|实验|评测|基准|优于|提升",
        ),
        (
            "limitation_claim",
            r"\b(limit|limitation|fail|challenge|future work|robust)\b|局限|失败|挑战|未来工作|鲁棒",
        ),
    ]
    for claim_type, pattern in patterns:
        added_for_type = 0
        for sentence in sentences[:16]:
            if re.search(pattern, sentence, flags=re.IGNORECASE):
                candidates.append((claim_type, _clean_brief_text(sentence, 220)))
                added_for_type += 1
                if claim_type != "method_claim" or added_for_type >= 2:
                    break
    return candidates[:3]


def _paper_claim_evidence(*, title: str, review_text: str, abstract: str, category: str) -> str:
    if review_text:
        return _best_full_text_evidence(review_text=review_text, title=title, category=category)
    if abstract:
        return _clean_brief_text(_first_brief_sentence(abstract) or abstract, 260)
    parts = [f"标题：{title}" if title else "", f"分类：{category}" if category else ""]
    return _clean_brief_text("；".join(part for part in parts if part), 260) or "当前仅有论文元数据。"


def _best_full_text_evidence(*, review_text: str, title: str, category: str) -> str:
    text = _clean_brief_text(review_text, 2500)
    if not text:
        return ""
    keywords = [
        word.casefold()
        for word in re.findall(r"[A-Za-z][A-Za-z0-9-]{3,}|[\u4e00-\u9fa5]{2,}", f"{title} {category}")
    ][:16]
    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?。！？])\s+", text)
        if sentence.strip()
    ]
    if not sentences:
        return _clean_brief_text(text, 300)

    def score_sentence(sentence: str) -> tuple[int, int]:
        normalized = sentence.casefold()
        hit_count = sum(1 for keyword in keywords if keyword and keyword in normalized)
        method_bonus = 1 if re.search(r"\b(propose|present|introduce|method|framework|architecture|evaluate)\b|提出|方法|框架|架构|评估", sentence, flags=re.IGNORECASE) else 0
        return hit_count + method_bonus, -abs(len(sentence) - 180)

    best = max(sentences[:24], key=score_sentence)
    return _clean_brief_text(best, 300)


def _paper_brief_tags(paper) -> list[str]:
    title = str(getattr(paper, "title", "") or "")
    abstract = str(getattr(paper, "abstract", "") or "")
    review_text = str(getattr(paper, "review_text", "") or "")
    category = str(getattr(paper, "taxonomy_category", "") or "")
    keywords = " ".join(str(item) for item in list(getattr(paper, "keywords", []) or []))
    text = f"{title} {abstract} {review_text[:1600]} {category} {keywords}".lower()
    tags: list[str] = []

    def add_tag(condition: bool, tag: str) -> None:
        if condition and tag not in tags:
            tags.append(tag)

    add_tag(bool(re.search(r"\b(survey|review|overview|taxonomy)\b|综述", text)), "survey")
    add_tag(bool(re.search(r"\b(benchmark|evaluation|evaluate|leaderboard|protocol)\b|评测|基准", text)), "benchmark")
    add_tag(bool(re.search(r"\b(dataset|data set|corpus)\b|数据集", text)), "dataset")
    add_tag(bool(re.search(r"\b(method|framework|architecture|model|system)\b|方法|框架|架构|模型|系统", text)), "method")
    add_tag(
        bool(
            re.search(
                r"\b(orchestrat\w*|schedul\w*|allocation|offload\w*|resource|mec|edge[- ]?cloud|cloud[- ]?edge|wireless|network|uav|inference workload|accelerat\w*)\b|编排|调度|资源|卸载|端云|边缘|无线|通信|网络|推理负载|加速器",
                text,
            )
        ),
        "orchestration",
    )
    add_tag(bool(re.search(r"\b(fusion|multimodal|cross-modal|alignment)\b|多模态|跨模态|融合|对齐", text)), "multimodal")
    add_tag(bool(re.search(r"\b(retrieval|search|ranking|representation)\b|检索|表征|排序", text)), "retrieval")
    add_tag(bool(re.search(r"\b(robust|failure|missing|uncertainty|noise)\b|鲁棒|失败|缺失|不确定", text)), "robustness")
    add_tag(bool(re.search(r"\b(llm|large language model|language model|agent)\b|大模型|智能体", text)), "llm")
    add_tag(bool(getattr(paper, "citation_count_known", False)) and int(getattr(paper, "citation_count", 0) or 0) >= 50, "high-citation")
    add_tag(_paper_publish_year(paper) >= 2024, "recent")
    origin = str(getattr(paper, "origin", "") or getattr(paper, "source", "") or "").lower()
    add_tag(origin in {"user_upload", "user_import"}, "user-provided")
    return tags[:6]


def _paper_publish_year(paper) -> int:
    match = re.search(r"\d{4}", str(getattr(paper, "publish_date", "") or ""))
    return int(match.group(0)) if match else 0


def _paper_brief_problem(*, title: str, abstract: str, category: str, topic: str) -> str:
    sentence = _first_brief_sentence(abstract)
    if sentence:
        return sentence
    if category:
        return f"围绕“{category}”方向中的具体问题展开，当前主要可从标题《{title}》判断其研究对象。"
    clean_topic = _clean_brief_text(topic, 80) or "当前研究主题"
    return f"围绕“{clean_topic}”中的相关问题展开；当前缺少摘要或全文，需结合原文进一步确认问题定义。"


def _paper_brief_method(*, title: str, abstract: str, tags: list[str], paper) -> str:
    text = f"{title} {abstract}".lower()
    if "survey" in tags:
        return "以综述、分类或路线梳理为主，适合快速建立领域结构和问题清单。"
    if "benchmark" in tags or "dataset" in tags:
        return "以评测基准、数据资源或实验协议为主，适合支撑后续方法比较与验证。"
    if "orchestration" in tags:
        return "围绕计算/通信/服务编排、资源调度或端云协同展开，适合观察系统约束和调度路线。"
    if "multimodal" in tags:
        return "围绕多模态表示、融合架构或跨模态对齐组织方法，适合观察融合路线。"
    if "retrieval" in tags:
        return "围绕检索、排序或表征匹配展开，适合支撑检索型研究方向。"
    if "robustness" in tags:
        return "关注鲁棒性、失败模式或缺失信息处理，适合作为风险和边界条件证据。"
    if "method" in tags:
        return "提出模型、框架或系统方法，适合作为技术路线参考。"
    keywords = [_clean_brief_text(value, 40) for value in list(getattr(paper, "keywords", []) or [])]
    keywords = [value for value in keywords if value][:3]
    if keywords:
        return f"元数据关键词显示其方法线索集中在：{' / '.join(keywords)}。"
    if re.search(r"\b(using|via|with|based on|framework|model)\b", text):
        return "标题显示其可能包含明确方法或系统设计，建议打开原文核查模型结构与实验设置。"
    return "当前没有足够结构化方法信息；系统先基于标题、分类和相关性理由给出保守判断。"


def _paper_brief_contribution(
    *,
    title: str,
    category: str,
    reasons: list[str],
    tags: list[str],
    topic: str,
) -> str:
    reason = _first_user_facing_reason(reasons)
    if reason:
        return f"与当前任务的主要价值是：{reason}"
    if "user-provided" in tags:
        return "来自用户上传资料，可作为当前研究的本地证据或对照论文；建议优先核查它与系统检索论文之间的关系。"
    if "survey" in tags:
        return "提供方向综述和问题地图，可帮助判断该主题已有路线与尚未覆盖的分支。"
    if "benchmark" in tags:
        return "提供评测视角，可帮助把研究建议落到可验证的任务和指标上。"
    if "dataset" in tags:
        return "提供数据资源或任务设定，可作为后续实验设计的候选基础。"
    if "orchestration" in tags:
        return "提供通信-计算协同、端云资源编排或推理调度证据，可帮助判断该方向的系统设计空间。"
    if category:
        return f"可作为“{category}”分支的代表证据，帮助解释该分支为什么进入 taxonomy。"
    clean_topic = _clean_brief_text(topic, 80) or "当前主题"
    return f"为“{clean_topic}”提供候选论文证据，适合继续阅读以确认具体贡献。"


def _paper_brief_limitation(*, paper, review_text: str, abstract: str) -> str:
    if review_text:
        return "当前已使用导入/上传材料中的正文片段，但仍未完成全篇覆盖、逐 claim 语义核验和冲突检测。"
    if not abstract:
        return "当前缺少摘要或全文片段，系统只能基于标题、分类和元数据判断；建议打开原文核查实验与局限。"
    if bool(getattr(paper, "citation_count_known", False)) is False:
        return "引用数据尚未获取，影响力判断不完整；建议以论文内容和实验设置为主进行人工复核。"
    return "当前 Paper Brief 仍是元数据/摘要级判断，尚未完成全文级 claim verification。"


def _paper_brief_relation(*, category: str, reasons: list[str], topic: str) -> str:
    reason = _first_user_facing_reason(reasons)
    if reason:
        return reason
    if category:
        return f"该论文被归入“{category}”，可用于支撑这一研究方向的证据阅读。"
    clean_topic = _clean_brief_text(topic, 80) or "当前研究主题"
    return f"系统将其作为“{clean_topic}”的候选证据；关系强度需要结合论文正文进一步确认。"


def _paper_brief_why_selected(*, paper, relation_to_topic: str, selection_factors: list[str]) -> str:
    if _is_user_uploaded_paper(paper):
        lead = "这篇论文来自用户上传/导入资料，适合作为本研究的本地证据锚点，并用于对照系统检索论文。"
    elif str(getattr(paper, "paper_pool_status", "") or "").casefold() == "core":
        lead = "这篇论文已进入核心分析池，会参与方向图、演进图、研究空白和建议生成。"
    elif str(getattr(paper, "relevance_tier", "") or "").casefold() == "direct":
        lead = "这篇论文与当前问题直接相关，适合优先阅读来确认主结论是否有论文支撑。"
    elif bool(getattr(paper, "is_new_this_round", False)):
        lead = "这篇论文是本轮新增证据，适合检查追问是否真的带来了新材料。"
    else:
        lead = "这篇论文被系统选为候选证据，适合先判断是否值得进入精读。"
    factor_text = f"选择依据：{'；'.join(selection_factors[:4])}。" if selection_factors else ""
    relation = _clean_brief_text(relation_to_topic, 160)
    relation_text = f"当前关系：{relation}" if relation else ""
    return _clean_brief_text("".join([lead, factor_text, relation_text]), 420)


def _paper_brief_read_focus(*, tags: list[str], title: str, abstract: str) -> str:
    text = f"{title} {abstract}".casefold()
    focus: list[str] = []
    if "survey" in tags:
        focus.append("先看分类框架、问题地图和代表论文表")
    if "benchmark" in tags or "dataset" in tags:
        focus.append("重点看任务定义、数据集、指标和实验协议")
    if "method" in tags:
        focus.append("重点看方法图、模块设计和与基线的差异")
    if "orchestration" in tags:
        focus.append("重点看任务模型、资源约束、调度目标和端云/无线协同假设")
    if "multimodal" in tags:
        focus.append("重点看融合位置、跨模态对齐方式和消融实验")
    if "retrieval" in tags:
        focus.append("重点看查询/表征/排序链路和检索评测设置")
    if "robustness" in tags:
        focus.append("重点看失败模式、缺失信息处理和鲁棒性实验")
    if not focus and re.search(r"\bexperiment|ablation|result|evaluation\b|实验|消融|结果|评测", text):
        focus.append("先看实验设置、消融和结果表，确认贡献是否可复现")
    if not focus:
        focus.append("先读摘要、方法段和实验设置，再决定是否进入精读")
    return "；".join(dict.fromkeys(focus[:3])) + "。"


def _paper_brief_evidence_basis(*, paper, source: str, selection_factors: list[str]) -> str:
    if source == "full_text_verified":
        source_text = "判断依据包含按需 Paper Analyst 抽取的正文片段。"
        fulltext_summary = summarize_full_text_verification(str(getattr(paper, "review_text", "") or ""))
        if fulltext_summary:
            source_text += fulltext_summary
    elif source == "full_text":
        source_text = "判断依据包含用户导入/上传材料中的正文片段。"
        fulltext_summary = summarize_full_text_verification(str(getattr(paper, "review_text", "") or ""))
        if fulltext_summary:
            source_text += fulltext_summary
    elif source == "abstract+metadata":
        source_text = "判断依据主要来自论文摘要、标题、分类和检索相关性。"
    else:
        source_text = "判断依据主要来自标题、来源、分类和检索相关性，信息较薄。"
    citation_known = bool(getattr(paper, "citation_count_known", False))
    if citation_known:
        citation_text = f"引用元数据已获取：{max(int(getattr(paper, 'citation_count', 0) or 0), 0)} 次。"
    else:
        citation_text = "引用元数据未获取，不能把它当作 0 引用论文。"
    factors = f"入选信号：{'；'.join(selection_factors[:4])}。" if selection_factors else ""
    return _clean_brief_text(source_text + citation_text + factors, 420)


def _paper_brief_verification_boundary(*, paper, source: str, review_text: str, abstract: str) -> str:
    if source == "full_text_verified" and review_text:
        fulltext_summary = summarize_full_text_verification(review_text)
        return (
            f"已完成本篇按需正文片段核验：{fulltext_summary}"
            "系统已抽取部分 claim 并定位支持片段；"
            "它能帮助筛读和发现疑点，但仍不是替代人工审稿的最终结论。"
        )
    if source == "full_text" and review_text:
        fulltext_summary = summarize_full_text_verification(review_text)
        return (
            f"当前达到正文片段级核查：{fulltext_summary}"
            "系统能引用上传/导入材料中的局部文本，"
            "但尚未完成全篇分段解析、逐 claim 支持/冲突判定和实验数值复核。"
        )
    if source == "abstract+metadata" and abstract:
        return (
            "当前达到摘要级核查：适合快速判断论文是否值得读，"
            "但方法细节、实验结论和局限仍需要打开全文人工复核。"
        )
    if _is_user_uploaded_paper(paper):
        return (
            "系统知道该论文来自用户资料，但当前缺少可用正文片段；"
            "建议重新导入可解析 PDF 或补充摘要后再做 claim verification。"
        )
    return "当前仅为元数据级判断，只能作为筛读线索，不能作为稳定研究结论。"


def _first_user_facing_reason(reasons: list[str]) -> str:
    for reason in reasons:
        clean_reason = _clean_brief_text(reason, 160)
        if clean_reason and not _looks_like_internal_relevance_signal(clean_reason):
            return clean_reason
    return ""


def _looks_like_internal_relevance_signal(reason: str) -> bool:
    normalized = reason.strip().casefold()
    if not normalized:
        return True
    if re.fullmatch(r"[a-z][a-z0-9]*(?:_[a-z0-9]+){1,6}", normalized):
        return True
    if normalized.startswith(("focus:", "title:", "abstract:", "query:", "user_selected:", "score:", "category:", "keywords:")):
        return True
    if "focus on" in normalized or "user_selected" in normalized:
        return True
    if any(marker in normalized for marker in ("shared_dimensions=", "target_added_dimensions=", "source_roles=", "target_roles=")):
        return True
    label_tokens = re.findall(r"[a-z][a-z0-9+-]*", normalized)
    has_sentence_signal = bool(re.search(r"[。！？.!?，,;；:]|\s(?:for|with|via|using|based|propose|introduce|improve|address)\s", normalized))
    if label_tokens and not has_sentence_signal:
        normalized_tokens = {
            token
            for token in label_tokens
            if token not in {"and", "or", "of", "the", "a", "an", "to", "in", "on"}
        }
        if normalized_tokens and normalized_tokens.issubset(_GENERIC_RELEVANCE_LABELS):
            return True
    if re.fullmatch(r"(?:[a-z][a-z0-9+-]*)(?:[\s/,_-]+[a-z][a-z0-9+-]*){0,5}", normalized):
        if set(re.findall(r"[a-z][a-z0-9+-]*", normalized)).issubset(_GENERIC_RELEVANCE_LABELS):
            return True
    return bool(re.fullmatch(r"[a-z_]+:[a-z0-9_ ./+-]+(?::[a-z0-9_ ./+-]+)*", normalized))


def _first_brief_sentence(text: str) -> str:
    clean_text = _clean_brief_text(text, 300)
    if not clean_text:
        return ""
    parts = re.split(r"(?<=[.!?。！？])\s+", clean_text)
    first = parts[0].strip() if parts else clean_text
    return _clean_brief_text(first, 180)


def _brief_paper_contribution_hint(paper) -> str:
    title = _clean_brief_text(getattr(paper, "title", ""), 180)
    abstract = _clean_brief_text(getattr(paper, "abstract", ""), 360)
    review_text = _clean_brief_text(getattr(paper, "review_text", ""), 360)
    category = _clean_brief_text(getattr(paper, "taxonomy_category", ""), 90)
    joined = " ".join([title, abstract, review_text, category]).casefold()

    if re.search(r"\b(survey|review|taxonomy|roadmap|challenge|direction)\b|综述|路线|方向|挑战", joined):
        return "梳理该方向的路线、挑战与代表工作，适合先用来建立阅读地图"
    if re.search(r"\b(benchmark|evaluation|dataset|leaderboard|metric|protocol)\b|评测|基准|数据集|指标", joined):
        return "提供评测任务、数据资源或实验协议，适合判断后续方案如何验证"
    if re.search(r"\b(orchestrat|schedule|scheduling|resource|communication|compute|overlap|edge|cloud|ran)\b|编排|调度|通信|计算|资源|端云|边缘", joined):
        return "讨论通信/计算协同、资源调度或系统编排，可用来判断当前方案的系统设计空间"
    if re.search(r"\b(multimodal|fusion|alignment|cross-modal|vision-language)\b|多模态|融合|对齐|跨模态", joined):
        return "围绕多模态表示、融合架构或跨模态对齐展开，适合判断技术路线是否贴合主题"
    if re.search(r"\b(retrieval|search|ranking|rerank|representation|embedding)\b|检索|搜索|排序|表征|嵌入", joined):
        return "围绕检索、排序或表征匹配展开，适合支撑检索链路和评价指标设计"
    if re.search(r"\b(robust|failure|missing|uncertain|noise)\b|鲁棒|失败|缺失|不确定|噪声", joined):
        return "关注失败模式、鲁棒性或边界条件，适合补充风险与实验检查视角"

    sentence = _first_brief_sentence(abstract or review_text)
    if sentence and not _looks_like_internal_relevance_signal(sentence):
        return f"核心内容可先看：{sentence}"
    if category:
        return f"可作为“{category}”分支的代表证据，帮助判断该路线是否值得继续深入"
    if title:
        return f"聚焦《{_clean_brief_text(title, 90)}》，建议先核查问题定义、方法假设和实验设置"
    return ""


def _brief_paper_read_focus_hint(paper) -> str:
    title = _clean_brief_text(getattr(paper, "title", ""), 180)
    joined = " ".join(
        [
            title,
            _clean_brief_text(getattr(paper, "abstract", ""), 260),
            _clean_brief_text(getattr(paper, "review_text", ""), 260),
            _clean_brief_text(getattr(paper, "taxonomy_category", ""), 80),
        ]
    ).casefold()
    is_uploaded = _is_user_uploaded_paper(paper)

    if re.search(r"\b(survey|review|taxonomy|roadmap|challenge|direction)\b|综述|路线|方向|挑战", joined):
        focus = "先看分类框架、挑战清单和代表工作，判断它是否能快速搭出领域地图"
    elif re.search(r"\b(benchmark|evaluation|dataset|metric|protocol)\b|评测|基准|数据集|指标", joined):
        focus = "先看任务定义、评价指标和实验协议，判断你的方案后续怎么验证"
    elif re.search(r"\b(orchestrat|schedule|resource|communication|compute|overlap|edge|cloud|ran)\b|编排|调度|通信|计算|资源|端云|边缘", joined):
        focus = "先看任务模型、资源/延迟约束、调度目标和系统假设是否贴合当前问题"
    elif re.search(r"\b(multimodal|fusion|alignment|cross-modal|vision-language)\b|多模态|融合|对齐|跨模态", joined):
        focus = "先看融合发生在哪一层、跨模态对齐怎么做、有没有缺失模态或消融实验"
    elif re.search(r"\b(retrieval|search|ranking|embedding|representation)\b|检索|搜索|排序|表征|嵌入", joined):
        focus = "先看查询/表征/排序链路和评价指标，判断是否能支撑检索型问题"
    else:
        focus = "先看摘要、方法图和实验设置，再决定是否进入精读"

    if is_uploaded:
        return _clean_brief_text(f"{focus}；同时核查它能否作为你上传材料里的本地证据锚点", 220)
    return _clean_brief_text(focus, 200)


def _brief_reason_with_factors(lead: str, factors: list[str], *, max_factors: int = 3) -> str:
    clean_lead = _trim_sentence_end(_clean_brief_text(lead, 220))
    factor_text = "；".join(factors[:max_factors])
    if factor_text:
        return _clean_brief_text(f"{clean_lead}。选择依据：{factor_text}", 360)
    return _clean_brief_text(clean_lead, 360)


def _build_workspace_research_brief(
    *,
    mode: str,
    topic: str,
    task_id: str,
    summary: str,
    papers: list,
    analysis_paper_ids: list[str],
    taxonomy: dict,
    gaps: list,
    ideas: list,
    evidence_status: dict,
    source_trace: WorkspaceSourceTraceView | None,
    workspaces: list | None = None,
    conversation_synthesis: dict | None = None,
) -> WorkspaceResearchBriefView:
    paper_by_id = {
        str(getattr(paper, "paper_id", "") or "").strip(): paper
        for paper in papers
        if str(getattr(paper, "paper_id", "") or "").strip()
    }
    source_task_ids_by_paper = _paper_source_task_id_map(
        papers=papers,
        workspaces=workspaces or [],
        fallback_task_id=task_id,
    )
    ordered_analysis_ids = _ordered_existing_paper_ids(analysis_paper_ids, paper_by_id)
    if not ordered_analysis_ids:
        ordered_analysis_ids = _ordered_existing_paper_ids(
            [str(getattr(paper, "paper_id", "") or "") for paper in papers],
            paper_by_id,
        )
    analysis_papers = [paper_by_id[paper_id] for paper_id in ordered_analysis_ids if paper_id in paper_by_id]
    top_routes = _top_taxonomy_routes(taxonomy=taxonomy, paper_by_id=paper_by_id)
    must_read_ids = _select_must_read_paper_ids(ordered_analysis_ids, paper_by_id, limit=4)
    must_read_papers = [
        WorkspaceBriefPaperView(
            paper_id=paper_id,
            title=_clean_brief_text(getattr(paper_by_id[paper_id], "title", ""), 180),
            contribution=_brief_paper_contribution_hint(paper_by_id[paper_id]),
            read_focus=_brief_paper_read_focus_hint(paper_by_id[paper_id]),
            reason=_brief_paper_reason(paper_by_id[paper_id]),
            source_task_ids=source_task_ids_by_paper.get(paper_id, [task_id] if task_id else []),
            evidence_level="direct",
        )
        for paper_id in must_read_ids
    ]

    synthesis = conversation_synthesis or {}
    key_findings = []
    if synthesis:
        key_findings.extend(
            _brief_items_from_synthesis(
                synthesis=synthesis,
                field_name="strengthened_findings",
                source_task_ids_by_paper=source_task_ids_by_paper,
                fallback_task_id=task_id,
            )
        )
        key_findings.extend(
            _brief_items_from_synthesis(
                synthesis=synthesis,
                field_name="new_findings",
                source_task_ids_by_paper=source_task_ids_by_paper,
                fallback_task_id=task_id,
            )
        )
        key_findings.extend(
            _brief_items_from_synthesis(
                synthesis=synthesis,
                field_name="revised_findings",
                source_task_ids_by_paper=source_task_ids_by_paper,
                fallback_task_id=task_id,
            )
        )
    if not key_findings:
        key_findings = _taxonomy_brief_items(
            taxonomy=taxonomy,
            paper_by_id=paper_by_id,
            source_task_ids_by_paper=source_task_ids_by_paper,
            fallback_task_id=task_id,
        )

    open_gaps = (
        _brief_items_from_synthesis(
            synthesis=synthesis,
            field_name="open_questions",
            source_task_ids_by_paper=source_task_ids_by_paper,
            fallback_task_id=task_id,
        )
        if synthesis
        else []
    )
    if not open_gaps:
        open_gaps = _gap_brief_items(gaps, paper_by_id=paper_by_id, fallback_task_id=task_id)

    recommended_next_steps = (
        _brief_items_from_synthesis(
            synthesis=synthesis,
            field_name="current_recommendations",
            source_task_ids_by_paper=source_task_ids_by_paper,
            fallback_task_id=task_id,
        )
        if synthesis
        else []
    )
    if not recommended_next_steps:
        recommended_next_steps = _idea_brief_items(ideas, paper_by_id=paper_by_id, fallback_task_id=task_id)
    if not recommended_next_steps:
        recommended_next_steps = _fallback_next_step_items(
            must_read_papers=must_read_papers,
            open_gaps=open_gaps,
            source_trace=source_trace,
            fallback_task_id=task_id,
        )

    round_evolution = _conversation_round_evolution_items(
        synthesis=synthesis,
        source_task_ids_by_paper=source_task_ids_by_paper,
        fallback_task_id=task_id,
    )
    if mode == "task" and source_trace is not None:
        round_evolution = _task_round_evolution_items(
            source_trace=source_trace,
            fallback_task_id=task_id,
        )

    key_findings = _dedupe_brief_items(key_findings)[:4]
    open_gaps = _dedupe_brief_items(open_gaps)[:4]
    recommended_next_steps = _dedupe_brief_items(recommended_next_steps)[:4]
    round_evolution = _dedupe_brief_items(round_evolution)[:5]

    headline = _clean_brief_text(str(synthesis.get("headline", "") or ""), 120)
    if not headline:
        headline = f"{topic} 的{'累计' if mode == 'conversation' else '本轮'}研究简报"
    executive_summary = _build_research_brief_summary(
        topic=topic,
        summary=summary,
        use_summary_as_candidate=bool(synthesis and synthesis.get("source") == "llm"),
        analysis_papers=analysis_papers,
        top_routes=top_routes,
        key_findings=key_findings,
        must_read_papers=must_read_papers,
        open_gaps=open_gaps,
        recommended_next_steps=recommended_next_steps,
        evidence_status=evidence_status,
        source_trace=source_trace,
    )
    landscape_overview = _build_research_landscape_overview(
        topic=topic,
        analysis_papers=analysis_papers,
        top_routes=top_routes,
        must_read_papers=must_read_papers,
    )
    evidence_rationale = _build_research_evidence_rationale(
        analysis_papers=analysis_papers,
        must_read_papers=must_read_papers,
        source_trace=source_trace,
    )
    decision_advice = _build_research_decision_advice(
        must_read_papers=must_read_papers,
        open_gaps=open_gaps,
        recommended_next_steps=recommended_next_steps,
        evidence_status=evidence_status,
    )
    follow_up_prompts = _build_research_follow_up_prompts(
        must_read_papers=must_read_papers,
        open_gaps=open_gaps,
        recommended_next_steps=recommended_next_steps,
        top_routes=top_routes,
    )

    brief = WorkspaceResearchBriefView(
        mode=mode,
        headline=headline,
        executive_summary=executive_summary,
        landscape_overview=landscape_overview,
        evidence_rationale=evidence_rationale,
        decision_advice=decision_advice,
        key_findings=key_findings,
        must_read_papers=must_read_papers,
        open_gaps=open_gaps,
        recommended_next_steps=recommended_next_steps,
        evidence_warnings=_brief_evidence_warnings(
            evidence_status=evidence_status,
            source_trace=source_trace,
            analysis_paper_count=len(ordered_analysis_ids),
        ),
        round_evolution=round_evolution,
        follow_up_prompts=follow_up_prompts,
        source=str(synthesis.get("source", "") or "deterministic"),
    )
    return compress_research_brief_with_llm(topic=topic, brief=brief)


def _paper_source_task_id_map(*, papers: list, workspaces: list, fallback_task_id: str) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = defaultdict(list)
    for workspace in workspaces:
        source_task_id = str(getattr(workspace, "task_id", "") or "").strip()
        if not source_task_id:
            continue
        for paper in list(getattr(workspace, "papers", []) or []):
            paper_id = str(getattr(paper, "paper_id", "") or "").strip()
            if paper_id and source_task_id not in mapping[paper_id]:
                mapping[paper_id].append(source_task_id)
    fallback = [fallback_task_id] if fallback_task_id else []
    for paper in papers:
        paper_id = str(getattr(paper, "paper_id", "") or "").strip()
        if paper_id and not mapping.get(paper_id):
            mapping[paper_id] = list(fallback)
    return dict(mapping)


def _ordered_existing_paper_ids(candidate_ids: list[str], paper_by_id: dict[str, object]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for paper_id in candidate_ids:
        normalized = str(paper_id or "").strip()
        if normalized and normalized in paper_by_id and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def _select_must_read_paper_ids(
    ordered_analysis_ids: list[str],
    paper_by_id: dict[str, object],
    *,
    limit: int,
) -> list[str]:
    indexed_ids = [
        (index, paper_id)
        for index, paper_id in enumerate(ordered_analysis_ids)
        if paper_id in paper_by_id
    ]
    indexed_ids.sort(
        key=lambda item: (
            _brief_paper_priority(paper_by_id[item[1]]),
            -item[0],
        ),
        reverse=True,
    )
    return [paper_id for _, paper_id in indexed_ids[:limit]]


def _brief_paper_priority(paper) -> tuple[int, int, int, float, int]:
    pool_status = str(getattr(paper, "paper_pool_status", "") or "").lower()
    relevance_tier = str(getattr(paper, "relevance_tier", "") or "").lower()
    citation_count = max(int(getattr(paper, "citation_count", 0) or 0), 0)
    citation_known = bool(getattr(paper, "citation_count_known", False))
    return (
        1 if pool_status == "core" else 0,
        2 if relevance_tier == "direct" else 1 if relevance_tier == "adjacent" else 0,
        1 if bool(getattr(paper, "is_new_this_round", False)) else 0,
        min(citation_count, 500) / 500 if citation_known else 0.0,
        1 if _paper_publish_year(paper) >= 2024 else 0,
    )


def _brief_paper_reason(paper) -> str:
    factors = _brief_paper_selection_factors(paper)
    contribution_hint = _brief_paper_contribution_hint(paper)
    if _is_user_uploaded_paper(paper):
        lead = "用户上传/导入论文，优先价值是承接你的本地阅读上下文"
        if contribution_hint:
            lead = f"{lead}；{contribution_hint}"
        return _brief_reason_with_factors(lead, factors, max_factors=4)

    user_facing_reason = _first_user_facing_reason(
        [
            _clean_brief_text(reason, 160)
            for reason in list(getattr(paper, "relevance_reasons", []) or [])
            if _clean_brief_text(reason, 160)
        ]
    )
    if user_facing_reason:
        reason = _trim_sentence_end(user_facing_reason)
        if contribution_hint and contribution_hint.casefold() not in reason.casefold():
            reason = f"{contribution_hint}；{reason}"
        if factors:
            reason = f"{reason}。选择依据：{'；'.join(factors[:3])}"
        return _clean_brief_text(reason, 320)
    if contribution_hint:
        return _brief_reason_with_factors(contribution_hint, factors)
    if str(getattr(paper, "paper_pool_status", "") or "").lower() == "core":
        return _clean_brief_text(
            "用户指定或导入的核心论文，优先作为本轮研究的本地证据锚点。"
            + (f"选择依据：{'；'.join(factors[:3])}" if factors else ""),
            320,
        )
    if str(getattr(paper, "relevance_tier", "") or "").lower() == "direct":
        return _clean_brief_text(
            "与当前问题达到直接相关，适合优先阅读以确认主结论是否站得住。"
            + (f"选择依据：{'；'.join(factors[:3])}" if factors else ""),
            320,
        )
    if bool(getattr(paper, "is_new_this_round", False)):
        return _clean_brief_text(
            "本轮新增论文，适合优先检查它是否补上了追问提出的新约束。"
            + (f"选择依据：{'；'.join(factors[:3])}" if factors else ""),
            320,
        )
    category = _clean_brief_text(getattr(paper, "taxonomy_category", ""), 80)
    if category:
        return _clean_brief_text(
            f"覆盖研究方向“{category}”，可作为该分支的代表证据。"
            + (f"选择依据：{'；'.join(factors[:3])}" if factors else ""),
            320,
        )
    citation_count = int(getattr(paper, "citation_count", 0) or 0)
    citation_known = bool(getattr(paper, "citation_count_known", False))
    if citation_known and citation_count >= 50:
        return f"引用影响力较高（{citation_count} 次），适合作为领域背景或方法基线。"
    return _clean_brief_text(
        "进入核心分析池，可作为当前结论、方向图或研究建议的基础证据。"
        + (f"选择依据：{'；'.join(factors[:3])}" if factors else ""),
        320,
    )


def _brief_paper_selection_factors(paper) -> list[str]:
    factors: list[str] = []
    if _is_user_uploaded_paper(paper):
        factors.append("来自用户上传/导入资料，可承接本地阅读上下文")
    else:
        source = _clean_brief_text(getattr(paper, "source", ""), 40)
        if source:
            factors.append(f"来自系统检索的 {source} 论文")
    tier = str(getattr(paper, "relevance_tier", "") or "").casefold()
    if tier == "direct":
        factors.append("与当前主题直接相关")
    elif tier == "adjacent":
        factors.append("作为相邻方向证据补充")
    citation_count = int(getattr(paper, "citation_count", 0) or 0)
    if bool(getattr(paper, "citation_count_known", False)) and citation_count >= 50:
        factors.append(f"引用较高（{citation_count} 次）")
    if bool(getattr(paper, "is_new_this_round", False)):
        factors.append("本轮新增，能检验追问是否带来新证据")
    category = _clean_brief_text(getattr(paper, "taxonomy_category", ""), 60)
    if category:
        factors.append(f"覆盖“{category}”分支")
    if str(getattr(paper, "paper_pool_status", "") or "").casefold() == "core":
        factors.append("已进入核心分析池")
    year = _paper_publish_year(paper)
    if year >= 2024:
        factors.append(f"{year} 年近年论文")
    if getattr(paper, "review_text", ""):
        factors.append("已有正文片段，可做更细的 claim 核查")
    return list(dict.fromkeys(factors))


def _is_user_uploaded_paper(paper) -> bool:
    source = str(getattr(paper, "source", "") or "").casefold()
    origin = str(getattr(paper, "origin", "") or "").casefold()
    return source in {"user_upload", "user_import", "local_pdf"} or origin in {
        "user_upload",
        "user_import",
        "local_pdf",
    }


def _brief_items_from_synthesis(
    *,
    synthesis: dict,
    field_name: str,
    source_task_ids_by_paper: dict[str, list[str]],
    fallback_task_id: str,
    label: str = "",
) -> list[WorkspaceBriefItemView]:
    items: list[WorkspaceBriefItemView] = []
    for item in list(synthesis.get(field_name, []) or []):
        if not isinstance(item, dict):
            continue
        text = _clean_brief_text(item.get("text", ""), 260)
        if not text:
            continue
        supporting_paper_ids = _paper_ids_from_evidence_ids(item.get("evidence_ids", []))
        source_task_ids = [
            str(value).strip()
            for value in list(item.get("source_task_ids", []) or [])
            if str(value).strip()
        ]
        if not source_task_ids:
            for paper_id in supporting_paper_ids:
                source_task_ids.extend(source_task_ids_by_paper.get(paper_id, []))
        if not source_task_ids and fallback_task_id:
            source_task_ids = [fallback_task_id]
        items.append(
            WorkspaceBriefItemView(
                text=f"{label}：{text}" if label else text,
                supporting_paper_ids=supporting_paper_ids,
                source_task_ids=list(dict.fromkeys(source_task_ids)),
                evidence_level="direct" if supporting_paper_ids else "exploratory",
            )
        )
    return items


def _paper_ids_from_evidence_ids(evidence_ids: list) -> list[str]:
    paper_ids = []
    for evidence_id in evidence_ids or []:
        text = str(evidence_id or "").strip()
        if text.startswith("paper::"):
            paper_ids.append(text.split("paper::", 1)[1])
    return list(dict.fromkeys(paper_ids))


def _taxonomy_brief_items(
    *,
    taxonomy: dict,
    paper_by_id: dict[str, object],
    source_task_ids_by_paper: dict[str, list[str]],
    fallback_task_id: str,
) -> list[WorkspaceBriefItemView]:
    branches = _top_taxonomy_routes(taxonomy=taxonomy, paper_by_id=paper_by_id)
    items: list[WorkspaceBriefItemView] = []
    for branch in branches[:3]:
        if not isinstance(branch, dict):
            continue
        name = _clean_brief_text(branch.get("name", ""), 100)
        description = _clean_brief_text(branch.get("description", ""), 180)
        matched_paper_ids = [
            str(value).strip()
            for value in list(branch.get("matched_paper_ids", []) or [])
            if str(value).strip()
        ][:6]
        paper_count = int(branch.get("paper_count", 0) or len(matched_paper_ids))
        if not name or (paper_count <= 0 and not matched_paper_ids):
            continue
        source_task_ids = []
        for paper_id in matched_paper_ids:
            source_task_ids.extend(source_task_ids_by_paper.get(paper_id, []))
        if not source_task_ids and fallback_task_id:
            source_task_ids = [fallback_task_id]
        evidence_tier = str(branch.get("evidence_tier", "") or "candidate")
        titles = _paper_titles_for_ids(matched_paper_ids, paper_by_id, limit=2)
        description_text = f"：{description}" if description else f"，匹配 {paper_count} 篇论文"
        title_text = f"；代表论文包括 {_format_title_list(titles)}" if titles else ""
        items.append(
            WorkspaceBriefItemView(
                text=(
                    f"当前证据主要覆盖方向“{name}”"
                    + description_text
                    + title_text
                    + "。"
                ),
                supporting_paper_ids=list(dict.fromkeys(matched_paper_ids)),
                source_task_ids=list(dict.fromkeys(source_task_ids)),
                evidence_level=_brief_evidence_level_from_tier(evidence_tier),
            )
        )
    return items


def _top_taxonomy_routes(*, taxonomy: dict, paper_by_id: dict[str, object], limit: int = 4) -> list[dict]:
    branches = [
        dict(branch)
        for branch in list((taxonomy or {}).get("branches", []) or [])
        if isinstance(branch, dict)
    ]
    coverage = taxonomy.get("coverage", {}) if isinstance(taxonomy, dict) else {}
    for branch in branches:
        branch_id = str(branch.get("branch_id", "") or "")
        branch_coverage = coverage.get(branch_id, {}) if isinstance(coverage, dict) else {}
        if isinstance(branch_coverage, dict):
            branch["matched_paper_ids"] = _merge_string_ids(
                branch.get("matched_paper_ids", []),
                branch_coverage.get("matched_paper_ids", []),
            )
            if branch["matched_paper_ids"]:
                branch["paper_count"] = len(branch["matched_paper_ids"])
            branch["coverage_score"] = max(
                float(branch.get("coverage_score", 0.0) or 0.0),
                float(branch_coverage.get("coverage_score", 0.0) or 0.0),
            )
            branch["evidence_tier"] = _stronger_evidence_tier(
                str(branch.get("evidence_tier", "") or ""),
                str(branch_coverage.get("evidence_tier", "") or ""),
            )
    branches.sort(
        key=lambda branch: (
            int(branch.get("paper_count", 0) or 0),
            float(branch.get("coverage_score", 0.0) or branch.get("branch_confidence", 0.0) or 0.0),
            len(_paper_titles_for_ids(branch.get("matched_paper_ids", []), paper_by_id, limit=3)),
        ),
        reverse=True,
    )
    return branches[:limit]


def _brief_evidence_level_from_tier(value: str) -> str:
    normalized = str(value or "").casefold()
    if normalized in {"strong", "direct", "confirmed"}:
        return "direct"
    if normalized in {"moderate", "weak", "indirect", "supported"}:
        return "indirect"
    return "exploratory"


def _paper_titles_for_ids(
    paper_ids: list[str],
    paper_by_id: dict[str, object],
    *,
    limit: int,
) -> list[str]:
    titles: list[str] = []
    for paper_id in list(paper_ids or []):
        paper = paper_by_id.get(str(paper_id).strip())
        if paper is None:
            continue
        title = _clean_brief_text(getattr(paper, "title", ""), 120)
        if title and title != "未识别论文":
            titles.append(title)
        if len(titles) >= limit:
            break
    return titles


def _format_title_list(titles: list[str]) -> str:
    if not titles:
        return ""
    return "、".join(f"《{title}》" for title in titles)


def _gap_brief_items(gaps: list, *, paper_by_id: dict[str, object], fallback_task_id: str) -> list[WorkspaceBriefItemView]:
    items = []
    for gap in list(gaps or [])[:4]:
        text = _clean_brief_text(getattr(gap, "summary", ""), 260)
        if not text:
            continue
        supporting_paper_ids = [
            str(value).strip()
            for value in list(getattr(gap, "supporting_paper_ids", []) or [])
            if str(value).strip()
        ]
        titles = _paper_titles_for_ids(supporting_paper_ids, paper_by_id, limit=2)
        if supporting_paper_ids:
            support_text = f"证据依据：{len(set(supporting_paper_ids))} 篇论文"
            if titles:
                support_text += f"（{_format_title_list(titles)}）"
            support_text += "；仍需结合全文核查具体 claim。"
        else:
            support_text = "当前主要来自覆盖审计或语义缺口判断，尚未绑定直接论文证据。"
        items.append(
            WorkspaceBriefItemView(
                text=_clean_brief_text(f"{_trim_sentence_end(text)}。{support_text}", 360),
                supporting_paper_ids=list(dict.fromkeys(supporting_paper_ids)),
                source_task_ids=[fallback_task_id] if fallback_task_id else [],
                evidence_level=str(getattr(gap, "evidence_level", "") or "exploratory"),
            )
        )
    return items


def _idea_brief_items(ideas: list, *, paper_by_id: dict[str, object], fallback_task_id: str) -> list[WorkspaceBriefItemView]:
    items = []
    for idea in list(ideas or [])[:4]:
        title = _clean_brief_text(getattr(idea, "title", ""), 150)
        detail = _clean_brief_text(
            getattr(idea, "motivation", "")
            or getattr(idea, "approach", "")
            or getattr(idea, "contribution", ""),
            180,
        )
        if not title and not detail:
            continue
        supporting_paper_ids = [
            str(value).strip()
            for value in list(getattr(idea, "supporting_paper_ids", []) or [])
            if str(value).strip()
        ]
        titles = _paper_titles_for_ids(supporting_paper_ids, paper_by_id, limit=2)
        evidence_level = str(getattr(idea, "evidence_level", "") or "exploratory")
        evidence_label = _brief_level_label(evidence_level)
        support_text = ""
        if supporting_paper_ids:
            support_text = f"依据 {len(set(supporting_paper_ids))} 篇核心论文启发"
            if titles:
                support_text += f"（{_format_title_list(titles)}）"
            support_text += f"，当前属于{evidence_label}。"
        else:
            support_text = "当前未绑定论文证据，应先作为待验证假设处理。"
        items.append(
            WorkspaceBriefItemView(
                text=_clean_brief_text(
                    f"{title}：{detail}。{support_text}" if title and detail else f"{title or detail}。{support_text}",
                    380,
                ),
                supporting_paper_ids=list(dict.fromkeys(supporting_paper_ids)),
                source_task_ids=[fallback_task_id] if fallback_task_id else [],
                evidence_level=evidence_level,
            )
        )
    return items


def _fallback_next_step_items(
    *,
    must_read_papers: list[WorkspaceBriefPaperView],
    open_gaps: list[WorkspaceBriefItemView],
    source_trace: WorkspaceSourceTraceView | None,
    fallback_task_id: str,
) -> list[WorkspaceBriefItemView]:
    if must_read_papers:
        paper_ids = [paper.paper_id for paper in must_read_papers[:3] if paper.paper_id]
        titles = [paper.title for paper in must_read_papers[:2] if paper.title]
        text = (
            f"建议先精读 {_format_title_list(titles)}，确认这些核心证据是否真的支撑当前路线，"
            "再决定继续补搜还是收敛选题。"
        )
        return [
            WorkspaceBriefItemView(
                text=_clean_brief_text(text, 320),
                supporting_paper_ids=paper_ids,
                source_task_ids=[fallback_task_id] if fallback_task_id else [],
                evidence_level="indirect",
            )
        ]
    if open_gaps:
        text = (
            f"建议围绕“{_trim_sentence_end(open_gaps[0].text)}”继续补搜或上传相关 PDF，"
            "先把证据链补齐，再生成更稳定的研究建议。"
        )
        return [
            WorkspaceBriefItemView(
                text=_clean_brief_text(text, 320),
                source_task_ids=[fallback_task_id] if fallback_task_id else [],
                evidence_level="exploratory",
            )
        ]
    if source_trace is not None and bool(getattr(source_trace, "refresh_triggered", False)):
        text = "本轮已经执行增补检索；如果仍没有稳定建议，建议收窄问题 facet 或补充 1-2 篇种子论文。"
    else:
        text = "建议先补充更明确的应用场景、年份范围或种子论文，再生成下一轮研究建议。"
    return [
        WorkspaceBriefItemView(
            text=text,
            source_task_ids=[fallback_task_id] if fallback_task_id else [],
            evidence_level="exploratory",
        )
    ]


def _conversation_round_evolution_items(
    *,
    synthesis: dict,
    source_task_ids_by_paper: dict[str, list[str]],
    fallback_task_id: str,
) -> list[WorkspaceBriefItemView]:
    section_labels = (
        ("new_findings", "本轮新增"),
        ("strengthened_findings", "得到补强"),
        ("revised_findings", "发生修正"),
    )
    items = []
    for field_name, label in section_labels:
        items.extend(
            _brief_items_from_synthesis(
                synthesis=synthesis,
                field_name=field_name,
                source_task_ids_by_paper=source_task_ids_by_paper,
                fallback_task_id=fallback_task_id,
                label=label,
            )
        )
    return items


def _task_round_evolution_items(
    *,
    source_trace: WorkspaceSourceTraceView,
    fallback_task_id: str,
) -> list[WorkspaceBriefItemView]:
    items: list[WorkspaceBriefItemView] = []
    novel_count = int(getattr(source_trace, "novel_paper_count", 0) or 0)
    reused_count = int(getattr(source_trace, "reused_paper_count", 0) or 0)
    if novel_count or reused_count:
        if novel_count:
            text = f"本轮补入 {novel_count} 篇新增论文，同时沿用 {reused_count} 篇历史高相关证据。"
            level = "direct"
        else:
            text = f"本轮补搜未找到更高相关新增论文，系统沿用 {reused_count} 篇历史高相关证据继续分析。"
            level = "indirect"
        items.append(
            WorkspaceBriefItemView(
                text=text,
                source_task_ids=[fallback_task_id] if fallback_task_id else [],
                evidence_level=level,
            )
        )
    if bool(getattr(source_trace, "refresh_triggered", False)):
        items.append(
            WorkspaceBriefItemView(
                text="追问触发了增补检索，系统已尝试按新约束更新证据池。",
                source_task_ids=[fallback_task_id] if fallback_task_id else [],
                evidence_level="direct",
            )
        )
    return items


def _dedupe_brief_items(items: list[WorkspaceBriefItemView]) -> list[WorkspaceBriefItemView]:
    result = []
    seen: set[str] = set()
    for item in items:
        normalized = _normalized_merge_text(item.text)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(item)
    return result


def _build_research_brief_summary(
    *,
    topic: str,
    summary: str,
    use_summary_as_candidate: bool,
    analysis_papers: list,
    top_routes: list[dict],
    key_findings: list[WorkspaceBriefItemView],
    must_read_papers: list[WorkspaceBriefPaperView],
    open_gaps: list[WorkspaceBriefItemView],
    recommended_next_steps: list[WorkspaceBriefItemView],
    evidence_status: dict,
    source_trace: WorkspaceSourceTraceView | None,
) -> str:
    candidate_summary = _clean_brief_text(summary, 520)
    clean_topic = _clean_brief_text(topic, 100) or "当前主题"

    parts: list[str] = []
    route_names = [
        _clean_brief_text(branch.get("name", ""), 80)
        for branch in top_routes[:3]
        if isinstance(branch, dict) and _clean_brief_text(branch.get("name", ""), 80)
    ]
    paper_count = len(analysis_papers)
    direct_count = sum(
        1
        for paper in analysis_papers
        if str(getattr(paper, "relevance_tier", "") or "").casefold() == "direct"
    )
    uploaded_count = sum(1 for paper in analysis_papers if _is_user_uploaded_paper(paper))
    system_count = max(paper_count - uploaded_count, 0)
    if route_names:
        route_text = " / ".join(route_names)
        evidence_text = f"{paper_count} 篇核心论文"
        if paper_count:
            evidence_text += f"（直接相关 {direct_count} 篇"
            if uploaded_count:
                evidence_text += f"，用户上传 {uploaded_count} 篇"
            if system_count:
                evidence_text += f"，系统检索 {system_count} 篇"
            evidence_text += "）"
        parts.append(f"整体进展：围绕“{clean_topic}”，当前证据主要落在 {route_text} 等路线，证据骨架由 {evidence_text} 支撑")
    elif source_trace is not None and bool(getattr(source_trace, "refresh_triggered", False)):
        novel_count = int(getattr(source_trace, "novel_paper_count", 0) or 0)
        reused_count = int(getattr(source_trace, "reused_paper_count", 0) or 0)
        direct_count = int(getattr(source_trace, "direct_paper_count", 0) or 0)
        adjacent_count = int(getattr(source_trace, "adjacent_paper_count", 0) or 0)
        parts.append(
            f"整体进展：围绕“{clean_topic}”已按追问重新检索，"
            f"新增 {novel_count} 篇论文、沿用 {reused_count} 篇旧证据；"
            f"当前 {direct_count} 篇为直接证据、{adjacent_count} 篇为邻近证据"
        )
    elif key_findings:
        parts.append(f"整体进展：{_trim_sentence_end(key_findings[0].text)}")
    elif must_read_papers:
        first_title = _clean_brief_text(must_read_papers[0].title, 100)
        parts.append(f"整体进展：当前证据骨架首先由《{first_title}》等核心论文支撑")
    elif use_summary_as_candidate and candidate_summary and not _looks_like_metric_summary(candidate_summary):
        parts.append(f"整体进展：{_trim_sentence_end(candidate_summary)}")
    else:
        parts.append(f"整体进展：围绕“{clean_topic}”的研究结果已整理为论文证据、方向结构和下一步建议")

    if key_findings and _trim_sentence_end(key_findings[0].text) not in parts[0]:
        parts.append(f"最稳的观察是{_trim_sentence_end(key_findings[0].text)}")
    if source_trace is not None and bool(getattr(source_trace, "refresh_triggered", False)) and route_names:
        novel_count = int(getattr(source_trace, "novel_paper_count", 0) or 0)
        reused_count = int(getattr(source_trace, "reused_paper_count", 0) or 0)
        parts.append(f"追问已触发补搜：新增 {novel_count} 篇、沿用 {reused_count} 篇，说明系统确实按新约束更新了证据池")
    if open_gaps:
        gap_level = _brief_level_label(open_gaps[0].evidence_level)
        parts.append(f"主要不确定性在于{_brief_summary_item_text(open_gaps[0].text)}（{gap_level}）")
    if recommended_next_steps:
        step_level = _brief_level_label(recommended_next_steps[0].evidence_level)
        parts.append(f"下一步建议{_brief_summary_item_text(recommended_next_steps[0].text)}（{step_level}）")
    if evidence_status.get("insufficient"):
        parts.append("当前证据仍偏薄，建议把结论视为选题线索而不是最终判断")
    return "；".join(part for part in parts if part).strip() + "。"


def _build_research_landscape_overview(
    *,
    topic: str,
    analysis_papers: list,
    top_routes: list[dict],
    must_read_papers: list[WorkspaceBriefPaperView],
) -> str:
    clean_topic = _clean_brief_text(topic, 100) or "当前主题"
    route_names = [
        _clean_brief_text(branch.get("name", ""), 80)
        for branch in top_routes[:3]
        if isinstance(branch, dict) and _clean_brief_text(branch.get("name", ""), 80)
    ]
    route_text = "、".join(route_names)
    paper_titles = [paper.title for paper in must_read_papers[:2] if paper.title]
    title_text = _format_title_list(paper_titles)
    paper_count = len(analysis_papers)
    direct_count = sum(
        1
        for paper in analysis_papers
        if str(getattr(paper, "relevance_tier", "") or "").casefold() == "direct"
    )
    recent_count = sum(1 for paper in analysis_papers if _paper_publish_year(paper) >= 2024)
    if route_text and title_text:
        return (
            f"围绕“{clean_topic}”，当前证据显示主题主要分布在 {route_text} 等路线；"
            f"{title_text} 构成优先阅读入口。核心分析池共 {paper_count} 篇，"
            f"其中直接相关 {direct_count} 篇、近年论文 {recent_count} 篇。"
        )
    if route_text:
        return (
            f"围绕“{clean_topic}”，当前证据主要覆盖 {route_text} 等路线；"
            f"核心分析池共 {paper_count} 篇，仍需结合论文详情判断每条路线的证据强度。"
        )
    if title_text:
        return f"当前尚未形成清晰 taxonomy 路线，但 {title_text} 可以先作为阅读锚点，帮助判断“{clean_topic}”是否有足够证据继续深入。"
    return f"当前围绕“{clean_topic}”整理了初步证据，但路线结构仍偏薄，建议先补搜或上传代表论文。"


def _build_research_evidence_rationale(
    *,
    analysis_papers: list,
    must_read_papers: list[WorkspaceBriefPaperView],
    source_trace: WorkspaceSourceTraceView | None,
) -> str:
    uploaded_count = sum(1 for paper in analysis_papers if _is_user_uploaded_paper(paper))
    system_count = max(len(analysis_papers) - uploaded_count, 0)
    direct_count = sum(
        1
        for paper in analysis_papers
        if str(getattr(paper, "relevance_tier", "") or "").casefold() == "direct"
    )
    high_citation_count = sum(
        1
        for paper in analysis_papers
        if bool(getattr(paper, "citation_count_known", False))
        and int(getattr(paper, "citation_count", 0) or 0) >= 50
    )
    reason_parts = [
        f"核心论文优先从 {len(analysis_papers)} 篇分析池中选择",
        f"直接相关 {direct_count} 篇",
        f"用户上传/导入 {uploaded_count} 篇",
        f"系统检索 {system_count} 篇",
    ]
    if high_citation_count:
        reason_parts.append(f"高引用论文 {high_citation_count} 篇")
    if source_trace is not None and bool(getattr(source_trace, "refresh_triggered", False)):
        reason_parts.append(
            f"本轮补搜新增 {int(getattr(source_trace, 'novel_paper_count', 0) or 0)} 篇、沿用 {int(getattr(source_trace, 'reused_paper_count', 0) or 0)} 篇"
        )
    if must_read_papers:
        titles = _format_title_list([paper.title for paper in must_read_papers[:2] if paper.title])
        reason_parts.append(f"优先阅读入口为 {titles} 等论文")
    return "；".join(part for part in reason_parts if part) + "。这些选择依据只说明阅读优先级，最终结论仍以论文详情和 claim 核查为准。"


def _build_research_decision_advice(
    *,
    must_read_papers: list[WorkspaceBriefPaperView],
    open_gaps: list[WorkspaceBriefItemView],
    recommended_next_steps: list[WorkspaceBriefItemView],
    evidence_status: dict,
) -> str:
    if evidence_status.get("insufficient"):
        warning = _clean_brief_text(evidence_status.get("message", ""), 140)
        return warning or "当前证据偏薄，建议先补搜或上传 1-2 篇代表论文，再把建议上升为稳定结论。"
    if recommended_next_steps:
        level = _brief_level_label(recommended_next_steps[0].evidence_level)
        return f"下一步优先执行：{_brief_summary_item_text(recommended_next_steps[0].text)}（{level}）。"
    if open_gaps:
        level = _brief_level_label(open_gaps[0].evidence_level)
        return f"下一步优先围绕空白补证：{_brief_summary_item_text(open_gaps[0].text)}（{level}）。"
    if must_read_papers:
        titles = _format_title_list([paper.title for paper in must_read_papers[:2] if paper.title])
        return f"下一步先精读 {titles}，确认核心证据是否支撑当前路线，再决定是否继续补搜或收敛选题。"
    return "下一步建议先明确应用场景、年份范围或代表论文，再运行下一轮调研。"


def _build_research_follow_up_prompts(
    *,
    must_read_papers: list[WorkspaceBriefPaperView],
    open_gaps: list[WorkspaceBriefItemView],
    recommended_next_steps: list[WorkspaceBriefItemView],
    top_routes: list[dict],
) -> list[str]:
    prompts: list[str] = []
    for item in recommended_next_steps[:2]:
        prompts.append(_brief_follow_up_from_text("验证", item.text))
    for item in open_gaps[:3]:
        prompts.append(_brief_follow_up_from_text("补充证据", item.text))
    for paper in must_read_papers[:2]:
        title = _short_prompt_text(paper.title, 34)
        if title:
            prompts.append(f"精读《{title}》并核查结论")
    for route in top_routes[:2]:
        name = _short_prompt_text(str(route.get("name", "") or ""), 32)
        if name:
            prompts.append(f"展开“{name}”方向的近三年论文")
    return _dedupe_follow_up_prompts(prompts)[:5]


_FOLLOW_UP_CAVEAT_PATTERN = re.compile(
    r"(?:该方向当前缺少分支级直接论文证据|以下内容仅作为待验证假设|当前属于|需复核|选择依据|证据等级|依据\s*\d+\s*篇核心论文)[\s\S]*"
)
_FOLLOW_UP_DIRECTION_GAP_PATTERN = re.compile(r"方向[“\"]([^”\"]{2,96})[”\"]缺少关键概念[：:]\s*([^。；;，,\n]{0,80})")
_FOLLOW_UP_DIRECTION_PATTERN = re.compile(r"方向[“\"]([^”\"]{2,96})[”\"]")
_FOLLOW_UP_CONCEPT_PATTERN = re.compile(r"缺少关键概念[：:]\s*([^。；;，,\n]{2,80})")


def _brief_follow_up_from_text(prefix: str, value: str) -> str:
    text = _clean_follow_up_seed(value)
    if not text:
        return ""

    direction_gap = _FOLLOW_UP_DIRECTION_GAP_PATTERN.search(text)
    if direction_gap:
        direction = _short_prompt_text(direction_gap.group(1), 34)
        concept = _short_prompt_text(direction_gap.group(2), 24)
        if direction and concept:
            return f"补充“{direction}”方向中“{concept}”的论文证据"
        if direction:
            return f"补充“{direction}”方向的直接论文证据"

    direction = _FOLLOW_UP_DIRECTION_PATTERN.search(text)
    if prefix == "补充证据" and direction:
        return f"补充“{_short_prompt_text(direction.group(1), 34)}”方向的直接论文证据"

    concept = _FOLLOW_UP_CONCEPT_PATTERN.search(text)
    if concept:
        return f"补充“{_short_prompt_text(concept.group(1), 30)}”的代表论文"

    if prefix == "验证":
        return f"验证“{_short_prompt_text(text, 34)}”是否有直接证据"
    if prefix == "补充证据":
        return f"补充“{_short_prompt_text(text, 34)}”的论文证据"
    return _short_prompt_text(text, 48)


def _clean_follow_up_seed(value: str) -> str:
    text = _clean_brief_text(value, 260)
    text = text.replace("《", "").replace("》", "")
    text = re.sub(r"\b(\d{4})\.\s+(\d{4,5}v\d)\b", r"\1.\2", text)
    text = re.sub(r"[（(][^（）()]{48,}[）)]", " ", text)
    text = _FOLLOW_UP_CAVEAT_PATTERN.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip(" ，,；;：:-")


def _short_prompt_text(value: str, max_length: int) -> str:
    text = _clean_brief_text(value, max_length * 3)
    if len(text) <= max_length:
        return text.strip(" ，,；;：:-")
    sliced = text[:max_length]
    boundary = max(sliced.rfind(marker) for marker in ("。", "；", ";", "，", ",", "、", " "))
    if boundary >= int(max_length * 0.55):
        sliced = sliced[:boundary]
    return re.sub(r"[A-Za-z]{1,8}$", "", sliced).strip(" ，,；;：:-")


def _dedupe_follow_up_prompts(prompts: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    banned_fragments = ("以下内容仅作为", "待验证假设", "选择依据", "证据等级", "依据 ")
    for prompt in prompts:
        cleaned = _clean_brief_text(prompt, 90).strip(" ，,；;：:-")
        if not cleaned or any(fragment in cleaned for fragment in banned_fragments):
            continue
        key = re.sub(r"\s+", "", cleaned).casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(cleaned)
    return result


def _brief_level_label(level: str) -> str:
    normalized = str(level or "").lower()
    if normalized in {"direct", "strong"}:
        return "有直接论文支撑"
    if normalized in {"indirect", "moderate", "weak"}:
        return "间接证据，需复核"
    return "待验证假设"


def _looks_like_metric_summary(value: str) -> bool:
    text = str(value or "")
    metric_markers = ("本轮分析共得到", "当前累计", "汇总论文", "论文线索", "研究空白", "研究建议")
    return sum(marker in text for marker in metric_markers) >= 2


def _trim_sentence_end(value: str) -> str:
    return str(value or "").strip().rstrip("。.;；")


def _brief_summary_item_text(value: str) -> str:
    first_sentence = str(value or "").split("。", 1)[0]
    return _clean_brief_text(_trim_sentence_end(first_sentence), 180)


def _brief_evidence_warnings(
    *,
    evidence_status: dict,
    source_trace: WorkspaceSourceTraceView | None,
    analysis_paper_count: int,
) -> list[str]:
    warnings: list[str] = []
    if evidence_status.get("insufficient"):
        message = _clean_brief_text(evidence_status.get("message", ""), 180)
        warnings.append(message or "当前证据不足，结论应作为探索性线索阅读。")
    if int(evidence_status.get("fallback_paper_count", 0) or 0) > 0:
        warnings.append("结果中仍包含回退论文，展示时应优先核查真实论文证据。")
    if analysis_paper_count < 4:
        warnings.append("核心分析论文偏少，暂不适合把研究建议解释为稳定结论。")
    if source_trace is not None and bool(getattr(source_trace, "external_search_skipped", False)):
        warnings.append("本轮外部检索未执行，结论主要依赖导入论文或已有上下文。")
    return list(dict.fromkeys(warnings))[:4]


def _clean_brief_text(value, max_length: int) -> str:
    return clean_internal_context_text(str(value or ""), max_length=max_length)


def _merge_workspace_summaries(
    *,
    topic: str,
    workspaces: list,
    paper_count: int | None = None,
    gap_count: int | None = None,
    idea_count: int | None = None,
    conversation_synthesis: dict | None = None,
) -> str:
    paper_count = len(_merge_workspace_papers(workspaces)) if paper_count is None else paper_count
    gap_count = len(_merge_workspace_gaps(workspaces)) if gap_count is None else gap_count
    idea_count = len(_merge_workspace_ideas(workspaces)) if idea_count is None else idea_count
    task_count = len(workspaces)

    synthesis = conversation_synthesis or {}
    lines = [
        str(synthesis.get("headline", "") or f"{topic} 的会话级研究工作台"),
        str(
            synthesis.get("summary", "")
            or (
                f"当前累计 {task_count} 轮有效研究，汇总论文 {paper_count} 篇、"
                f"研究空白 {gap_count} 条、研究建议 {idea_count} 条。"
            )
        ),
    ]
    section_labels = (
        ("new_findings", "本轮新增"),
        ("strengthened_findings", "得到补强"),
        ("revised_findings", "发生修正"),
        ("open_questions", "仍待验证"),
        ("current_recommendations", "当前建议"),
    )
    emitted_texts: set[str] = set()
    for field_name, label in section_labels:
        texts = []
        for item in list(synthesis.get(field_name, []) or []):
            if not isinstance(item, dict):
                continue
            text = str(item.get("text", "") or "").strip()
            normalized = _normalized_merge_text(text)
            if not text or normalized in emitted_texts:
                continue
            texts.append(text)
            emitted_texts.add(normalized)
            if len(texts) == 2:
                break
        if texts:
            lines.append(f"{label}：{'；'.join(texts)}")
    return "\n".join(lines)


def _build_conversation_summary_payload(
    *,
    topic: str,
    workspaces: list,
    papers: list,
    gaps: list,
    ideas: list,
    alignment_score: float,
    conversation_synthesis: dict | None = None,
    analysis_paper_ids: list[str] | None = None,
) -> dict:
    latest_payload = next((dict(workspace.summary_payload or {}) for workspace in workspaces if workspace.summary_payload), {})
    top_gaps = [
        {"summary": clean_internal_context_text(getattr(gap, "summary", ""), max_length=160)}
        for gap in gaps[:3]
        if clean_internal_context_text(getattr(gap, "summary", ""), max_length=160)
    ]
    top_ideas = [
        {"title": clean_internal_context_text(getattr(idea, "title", ""), max_length=140)}
        for idea in ideas[:3]
        if clean_internal_context_text(getattr(idea, "title", ""), max_length=140)
    ]
    payload = dict(latest_payload)
    payload.update(
        {
            "headline": f"{topic} 已累计整合 {len(workspaces)} 轮研究结果。",
            "score": alignment_score,
            "counts": {
                "papers": len(papers),
                "gaps": len(gaps),
                "ideas": len(ideas),
            },
            "top_gaps": top_gaps,
            "top_ideas": top_ideas,
            "recommendation": (
                f"建议优先基于当前累计的 {len(papers)} 篇论文线索继续筛选高置信证据，"
                "再围绕稳定空白细化下一轮追问。"
            ),
            "aggregation_mode": "conversation_workspace",
            "conclusion_evolution": dict(conversation_synthesis or {}),
            "synthesis_source": str(
                (conversation_synthesis or {}).get("source", "deterministic")
            ),
            "analysis_paper_ids": list(analysis_paper_ids or []),
        }
    )
    current_recommendations = list(
        (conversation_synthesis or {}).get("current_recommendations", []) or []
    )
    if current_recommendations:
        payload["recommendation"] = "；".join(
            str(item.get("text", "") or "").strip()
            for item in current_recommendations[:2]
            if isinstance(item, dict) and str(item.get("text", "") or "").strip()
        )
    return payload


def _select_conversation_analysis_paper_ids(
    *,
    workspaces: list,
    papers: list,
    llm_recommended_paper_ids: list[str] | None = None,
) -> list[str]:
    if not workspaces:
        return []
    paper_by_id = {
        str(getattr(paper, "paper_id", "") or ""): paper
        for paper in papers
        if str(getattr(paper, "paper_id", "") or "")
    }
    round_ids = [
        [
            str(paper_id)
            for paper_id in list(
                (workspace.summary_payload or {}).get("analysis_paper_ids", []) or []
            )
            if str(paper_id) in paper_by_id
        ]
        for workspace in workspaces
    ]
    latest_ids = list(dict.fromkeys(round_ids[0]))
    candidate_ids = list(
        dict.fromkeys(paper_id for ids in round_ids for paper_id in ids)
    )
    if not candidate_ids:
        return list(paper_by_id)[:12]

    llm_ids = set(
        str(paper_id)
        for paper_id in list(llm_recommended_paper_ids or [])
        if str(paper_id) in paper_by_id
    )
    occurrence_count = {
        paper_id: sum(paper_id in ids for ids in round_ids)
        for paper_id in candidate_ids
    }

    def score(paper_id: str) -> tuple[float, int, int]:
        paper = paper_by_id[paper_id]
        tier_score = {
            "direct": 2.0,
            "adjacent": 1.0,
            "candidate": 0.4,
            "background": 0.0,
        }.get(str(getattr(paper, "relevance_tier", "") or "").casefold(), 0.4)
        citation_count = max(int(getattr(paper, "citation_count", 0) or 0), 0)
        citation_score = min(citation_count, 100) / 100
        total = (
            occurrence_count[paper_id] * 1.5
            + float(getattr(paper, "relevance_score", 0.0) or 0.0) * 2
            + tier_score
            + citation_score
            + (1.5 if paper_id in llm_ids else 0.0)
        )
        return total, occurrence_count[paper_id], citation_count

    target_count = min(12, len(candidate_ids))
    latest_quota = min(len(latest_ids), max(1, round(target_count * 0.67)))
    selected = sorted(latest_ids, key=score, reverse=True)[:latest_quota]
    selected_set = set(selected)
    historical_ids = [
        paper_id for paper_id in candidate_ids if paper_id not in selected_set
    ]
    selected.extend(
        sorted(historical_ids, key=score, reverse=True)[
            : max(target_count - len(selected), 0)
        ]
    )
    return selected[:target_count]


def _merge_workspace_papers(workspaces: list) -> list:
    merged: dict[str, object] = {}
    for workspace in reversed(workspaces):
        for paper in workspace.papers:
            existing = merged.get(paper.paper_id)
            if existing is None:
                merged[paper.paper_id] = deepcopy(paper)
                continue
            merged[paper.paper_id] = _merge_workspace_paper_record(existing, paper)
    return list(merged.values())


def _merge_workspace_paper_record(existing, candidate):
    """Merge a newer paper record without discarding richer historical metadata."""
    merged = deepcopy(existing)

    if candidate.title:
        merged.title = candidate.title
    if len(candidate.abstract or "") > len(merged.abstract or ""):
        merged.abstract = candidate.abstract
    if len(getattr(candidate, "review_text", "") or "") > len(getattr(merged, "review_text", "") or ""):
        merged.review_text = candidate.review_text
    merged.authors = _merge_string_ids(merged.authors, candidate.authors)
    merged.keywords = _merge_string_ids(merged.keywords, candidate.keywords)

    for field_name in (
        "publish_date",
        "source",
        "taxonomy_category",
        "url",
        "paper_pool_status",
        "document_id",
        "origin",
    ):
        value = str(getattr(candidate, field_name, "") or "").strip()
        if value:
            setattr(merged, field_name, value)

    existing_known = bool(getattr(merged, "citation_count_known", False))
    candidate_known = bool(getattr(candidate, "citation_count_known", False))
    existing_count = max(int(getattr(merged, "citation_count", 0) or 0), 0)
    candidate_count = max(int(getattr(candidate, "citation_count", 0) or 0), 0)
    if existing_known or candidate_known:
        merged.citation_count_known = True
        if candidate_known and candidate_count >= existing_count:
            merged.citation_count = candidate_count
            merged.citation_source = (
                str(getattr(candidate, "citation_source", "") or "")
                or str(getattr(merged, "citation_source", "") or "")
            )
        else:
            merged.citation_count = existing_count
    else:
        merged.citation_count = max(existing_count, candidate_count)

    merged.relevance_score = max(
        float(getattr(merged, "relevance_score", 0.0) or 0.0),
        float(getattr(candidate, "relevance_score", 0.0) or 0.0),
    )
    merged.relevance_tier = _stronger_relevance_tier(
        str(getattr(merged, "relevance_tier", "") or ""),
        str(getattr(candidate, "relevance_tier", "") or ""),
    )
    merged.relevance_reasons = _merge_string_ids(
        getattr(merged, "relevance_reasons", []),
        getattr(candidate, "relevance_reasons", []),
    )
    merged.is_new_this_round = bool(
        getattr(merged, "is_new_this_round", False)
        or getattr(candidate, "is_new_this_round", False)
    )
    return merged


def _inherit_workspace_paper_metadata(existing, candidate):
    """Reuse richer historical metadata without changing the current round marker."""
    merged = _merge_workspace_paper_record(existing, candidate)
    merged.is_new_this_round = bool(getattr(candidate, "is_new_this_round", False))
    return merged


def _stronger_relevance_tier(current: str, candidate: str) -> str:
    rank = {
        "background": 0,
        "candidate": 1,
        "adjacent": 2,
        "direct": 3,
    }
    current_key = current.strip().casefold() or "candidate"
    candidate_key = candidate.strip().casefold() or "candidate"
    return (
        candidate_key
        if rank.get(candidate_key, 1) > rank.get(current_key, 1)
        else current_key
    )


def _workspace_analysis_paper_ids(workspace) -> list[str]:
    all_ids = {
        str(getattr(paper, "paper_id", "") or "").strip()
        for paper in workspace.papers
        if str(getattr(paper, "paper_id", "") or "").strip()
    }
    payload_ids = [
        str(paper_id).strip()
        for paper_id in list((workspace.summary_payload or {}).get("analysis_paper_ids", []) or [])
        if str(paper_id).strip() in all_ids
    ]
    if payload_ids:
        return list(dict.fromkeys(payload_ids))

    inferred: list[str] = []
    for edge in workspace.graph_edges:
        for key in ("source", "target"):
            paper_id = str(edge.get(key, "") or "").strip()
            if paper_id in all_ids:
                inferred.append(paper_id)
    taxonomy = workspace.taxonomy if isinstance(workspace.taxonomy, dict) else {}
    coverage = taxonomy.get("coverage", {}) if isinstance(taxonomy.get("coverage"), dict) else {}
    for entry in coverage.values():
        if not isinstance(entry, dict):
            continue
        for paper_id in list(entry.get("matched_paper_ids", []) or []):
            normalized = str(paper_id).strip()
            if normalized in all_ids:
                inferred.append(normalized)
    return list(dict.fromkeys(inferred)) or list(all_ids)


def _merge_workspace_graph_edges(workspaces: list) -> list[dict]:
    merged: dict[tuple[str, str], dict] = {}
    for workspace in workspaces:
        for edge in workspace.graph_edges:
            key = (
                str(edge.get("source", "")),
                str(edge.get("target", "")),
            )
            existing = merged.get(key)
            if existing is None or _graph_edge_strength(edge) > _graph_edge_strength(existing):
                merged[key] = edge
    return list(merged.values())


def _visible_workspace_graph_edges(edges: list[dict]) -> list[dict]:
    """Expose only graph relations that have enough evidence for users."""

    visible: list[dict] = []
    related_count = 0
    for edge in sorted(
        edges,
        key=_graph_edge_strength,
        reverse=True,
    ):
        evidence_level = str(
            edge.get("evidence_level", "candidate") or "candidate"
        ).casefold()
        relationship = str(
            edge.get("relationship", "related") or "related"
        ).casefold()
        confidence = float(edge.get("confidence", 0.0) or 0.0)

        if evidence_level == "candidate":
            continue
        if evidence_level == "inferred" and confidence < 0.50:
            continue
        if relationship == "related":
            if confidence < 0.50 or related_count >= 2:
                continue
            related_count += 1
        visible.append(edge)
    return visible


def _graph_edge_strength(edge: dict) -> tuple[int, float]:
    relationship = str(edge.get("relationship", "") or "").strip().lower()
    evidence_level = str(edge.get("evidence_level", "") or "").strip().lower()
    relationship_rank = {
        "related": 1,
        "complements": 2,
        "scope_extension": 3,
        "addresses": 3,
        "comparison": 4,
        "citation": 5,
        "extension": 6,
        "improvement": 7,
    }
    evidence_rank = {
        "candidate": 1,
        "inferred": 2,
        "supported": 3,
        "confirmed": 4,
    }
    combined_rank = relationship_rank.get(relationship, 1) + evidence_rank.get(evidence_level, 0)
    return combined_rank, float(edge.get("confidence", 0.0) or 0.0)


def _merge_workspace_gaps(workspaces: list) -> list:
    merged: dict[tuple[str, str], object] = {}
    seen_summaries: set[str] = set()
    for workspace in workspaces:
        for gap in workspace.gaps:
            semantic_key = _normalized_merge_text(getattr(gap, "summary", ""))
            if semantic_key and semantic_key in seen_summaries:
                continue
            task_id = str(getattr(gap, "task_id", "") or getattr(workspace, "task_id", ""))
            gap_id = str(
                getattr(gap, "gap_id", "")
                or _stable_text_id(f"gap::{getattr(gap, 'summary', '')}")
            )
            merged[(task_id, gap_id)] = gap
            if semantic_key:
                seen_summaries.add(semantic_key)
    return list(merged.values())


def _merge_workspace_ideas(workspaces: list) -> list:
    merged: dict[tuple[str, str], object] = {}
    seen_titles: set[str] = set()
    for workspace in workspaces:
        for idea in workspace.ideas:
            semantic_key = _normalized_merge_text(getattr(idea, "title", ""))
            if semantic_key and semantic_key in seen_titles:
                continue
            task_id = str(getattr(idea, "task_id", "") or getattr(workspace, "task_id", ""))
            idea_id = str(
                getattr(idea, "idea_id", "")
                or _stable_text_id(f"idea::{getattr(idea, 'title', '')}")
            )
            merged[(task_id, idea_id)] = idea
            if semantic_key:
                seen_titles.add(semantic_key)
    return list(merged.values())


def _normalized_merge_text(value: str) -> str:
    return re.sub(r"\W+", "", str(value or "").casefold(), flags=re.UNICODE)


def _merge_workspace_taxonomy(workspaces: list) -> dict:
    branches_by_id: dict[str, dict] = {}
    coverage_accumulator: dict[str, dict] = defaultdict(
        lambda: {
            "paper_count_fallback": 0,
            "gap_count_fallback": 0,
            "paper_ids": set(),
            "gap_ids": set(),
            "coverage_score_sum": 0.0,
            "coverage_samples": 0.0,
            "evidence_tier": "",
        }
    )

    for workspace in workspaces:
        taxonomy = workspace.taxonomy or {}
        for branch in taxonomy.get("branches", []) or []:
            branch_id = str(branch.get("branch_id", "") or "")
            if not branch_id:
                continue
            existing = branches_by_id.get(branch_id)
            if existing is None:
                branches_by_id[branch_id] = dict(branch)
            else:
                matched_paper_ids = _merge_string_ids(
                    existing.get("matched_paper_ids", []),
                    branch.get("matched_paper_ids", []),
                )
                matched_gap_ids = _merge_string_ids(
                    existing.get("matched_gap_ids", []),
                    branch.get("matched_gap_ids", []),
                )
                existing["matched_paper_ids"] = matched_paper_ids
                existing["matched_gap_ids"] = matched_gap_ids
                existing["paper_count"] = (
                    len(matched_paper_ids)
                    if matched_paper_ids
                    else max(
                        int(existing.get("paper_count", 0) or 0),
                        int(branch.get("paper_count", 0) or 0),
                    )
                )

        coverage = taxonomy.get("coverage", {}) or {}
        for branch_id, entry in coverage.items():
            if not isinstance(entry, dict):
                continue
            accumulator = coverage_accumulator[str(branch_id)]
            accumulator["paper_count_fallback"] = max(
                accumulator["paper_count_fallback"],
                int(entry.get("paper_count", 0) or 0),
            )
            accumulator["gap_count_fallback"] = max(
                accumulator["gap_count_fallback"],
                int(entry.get("gap_count", 0) or 0),
            )
            accumulator["paper_ids"].update(
                _merge_string_ids(entry.get("matched_paper_ids", []))
            )
            accumulator["gap_ids"].update(
                _merge_string_ids(entry.get("matched_gap_ids", []))
            )
            accumulator["coverage_score_sum"] += float(entry.get("coverage_score", 0.0) or 0.0)
            accumulator["coverage_samples"] += 1.0
            accumulator["evidence_tier"] = _stronger_evidence_tier(
                accumulator["evidence_tier"],
                str(entry.get("evidence_tier", "") or ""),
            )

    merged_branches = sorted(
        branches_by_id.values(),
        key=lambda branch: (int(branch.get("paper_count", 0) or 0), str(branch.get("name", ""))),
        reverse=True,
    )

    merged_coverage: dict[str, dict] = {}
    for branch_id, accumulator in coverage_accumulator.items():
        samples = accumulator["coverage_samples"] or 1.0
        matched_paper_ids = sorted(accumulator["paper_ids"])
        matched_gap_ids = sorted(accumulator["gap_ids"])
        merged_coverage[branch_id] = {
            "paper_count": len(matched_paper_ids) or accumulator["paper_count_fallback"],
            "gap_count": len(matched_gap_ids) or accumulator["gap_count_fallback"],
            "coverage_score": round(accumulator["coverage_score_sum"] / samples, 3),
            "evidence_tier": accumulator["evidence_tier"] or "candidate",
            "matched_paper_ids": matched_paper_ids,
            "matched_gap_ids": matched_gap_ids,
        }

    for branch in merged_branches:
        branch_id = str(branch.get("branch_id", "") or "")
        coverage = merged_coverage.get(branch_id, {})
        matched_paper_ids = _merge_string_ids(
            branch.get("matched_paper_ids", []),
            coverage.get("matched_paper_ids", []),
        )
        matched_gap_ids = _merge_string_ids(
            branch.get("matched_gap_ids", []),
            coverage.get("matched_gap_ids", []),
        )
        branch["matched_paper_ids"] = matched_paper_ids
        branch["matched_gap_ids"] = matched_gap_ids
        if matched_paper_ids:
            branch["paper_count"] = len(matched_paper_ids)

    return {
        "branches": merged_branches,
        "coverage": merged_coverage,
        "tree": [],
        "raw": {
            "aggregation_mode": "conversation_workspace",
            "source_workspace_count": len(workspaces),
        },
    }


def _merge_string_ids(*groups) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for value in list(group or []):
            normalized = str(value).strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            merged.append(normalized)
    return merged


def _stronger_evidence_tier(current: str, candidate: str) -> str:
    rank = {"": 0, "candidate": 1, "weak": 2, "moderate": 3, "strong": 4}
    current_key = str(current or "").strip().lower()
    candidate_key = str(candidate or "").strip().lower()
    return candidate_key if rank.get(candidate_key, 0) > rank.get(current_key, 0) else current_key


def _merge_workspace_trace(workspaces: list, tasks: list) -> dict:
    action_history: list[dict] = []
    thought_trace: list[dict] = []
    context_inputs: list[dict] = [
        {
            "source": "conversation_workspace",
            "task_count": len(workspaces),
            "task_ids": [task.task_id for task in tasks],
        }
    ]
    for workspace in workspaces:
        trace = workspace.trace or {}
        action_history.extend(list(trace.get("action_history", [])))
        thought_trace.extend(list(trace.get("thought_trace", [])))
        context_inputs.extend(list(trace.get("context_inputs", [])))
    return {
        "thought_trace": thought_trace[:120],
        "action_history": action_history[:120],
        "context_inputs": context_inputs[:120],
    }


def _stable_text_id(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]


def _gap_hint_from_summary(summary: str) -> str:
    text = clean_internal_context_text(summary, max_length=120)
    if not text:
        return ""
    lower = text.lower()
    branch_match = re.search(r"[「\"]([^」\"]+)[」\"]", text)
    if "缺少关键概念" in text and branch_match:
        return f"{branch_match.group(1)} 关键概念"
    if "尚未覆盖研究方向" in text and branch_match:
        return branch_match.group(1)
    if lower.startswith("missing required concepts in "):
        return text.replace("缺少关键概念：", " ").replace("缺少关键概念", " ").strip()
    if lower.startswith("missing taxonomy branch:"):
        return text.split(":", 1)[-1].strip()
    return text


def _normalize_trace_entries(entries) -> list[dict]:
    normalized: list[dict] = []
    for index, entry in enumerate(entries or []):
        if isinstance(entry, dict):
            normalized.append(entry)
        else:
            normalized.append({"step": index + 1, "content": str(entry)})
    return normalized


def _latest_research_context_bundle(trace: dict) -> dict:
    context_inputs = list((trace or {}).get("context_inputs", []) or [])
    if context_inputs and isinstance(context_inputs[0], dict) and context_inputs[0].get("source") == "conversation_workspace":
        for entry in context_inputs:
            if isinstance(entry, dict) and entry.get("kind") == "research_context_bundle":
                return dict(entry)
        return {}
    for entry in reversed(context_inputs):
        if isinstance(entry, dict) and entry.get("kind") == "research_context_bundle":
            return dict(entry)
    return {}


def _build_source_trace_view(*, summary_payload: dict, trace: dict) -> WorkspaceSourceTraceView | None:
    grounding = summary_payload.get("context_grounding", {}) if isinstance(summary_payload, dict) else {}
    bundle = _latest_research_context_bundle(trace)
    retrieval_outcome = grounding.get("retrieval_outcome", {}) if isinstance(grounding, dict) else {}

    knowledge_hits_payload = grounding.get("knowledge_hits", []) if isinstance(grounding, dict) else []
    normalized_hits = [
        WorkspaceKnowledgeHitView(
            title=str(item.get("title", "")).strip(),
            snippet=clean_internal_context_text(str(item.get("snippet", "") or ""), max_length=1200),
            scope=str(item.get("scope", "")).strip() or "shared",
            source_type=str(item.get("source_type", "")).strip(),
            source_task_id=(str(item.get("source_task_id", "")).strip() or None),
            score=float(item.get("score", 0.0) or 0.0),
            evidence_level=str(item.get("evidence_level", "")).strip() or "candidate",
            matched_chunk_count=int(item.get("matched_chunk_count", 0) or 0),
            supporting_snippets=[
                clean_internal_context_text(str(snippet), max_length=1200)
                for snippet in list(item.get("supporting_snippets", []) or [])[:3]
                if clean_internal_context_text(str(snippet), max_length=1200)
            ],
        )
        for item in knowledge_hits_payload
        if isinstance(item, dict) and str(item.get("title", "")).strip()
    ]
    if not normalized_hits and bundle:
        normalized_hits = [
            WorkspaceKnowledgeHitView(title=title)
            for title in bundle.get("knowledge_titles", []) or []
            if str(title).strip()
        ]

    workspace_hints = grounding.get("workspace_hints", []) if isinstance(grounding, dict) else []
    if not workspace_hints:
        workspace_hints = bundle.get("workspace_hints", []) or []

    recent_user_turns = grounding.get("recent_user_turns", []) if isinstance(grounding, dict) else []
    if not recent_user_turns:
        recent_turns = bundle.get("recent_turns", []) or []
        recent_user_turns = [str(item).strip() for item in recent_turns if str(item).strip()]

    knowledge_scope = str(grounding.get("knowledge_scope", "")).strip() if isinstance(grounding, dict) else ""
    if not knowledge_scope:
        knowledge_scope = str(bundle.get("knowledge_scope", "")).strip() or "shared"
    research_mode = str(retrieval_outcome.get("research_mode", "") or "").strip()
    if not research_mode:
        research_mode = str(bundle.get("research_mode", "") or "").strip() or "hybrid"

    knowledge_hit_count = int(grounding.get("knowledge_hit_count", 0) or 0) if isinstance(grounding, dict) else 0
    if not knowledge_hit_count:
        knowledge_hit_count = int(bundle.get("knowledge_hit_count", 0) or len(normalized_hits))

    workspace_hint_count = int(grounding.get("workspace_hint_count", 0) or 0) if isinstance(grounding, dict) else 0
    if not workspace_hint_count:
        workspace_hint_count = len(workspace_hints)

    recent_turn_count = int(grounding.get("recent_turn_count", 0) or 0) if isinstance(grounding, dict) else 0
    if not recent_turn_count:
        recent_turn_count = len(recent_user_turns)

    if not normalized_hits and not workspace_hints and not recent_user_turns and not bundle and not grounding:
        return None

    return WorkspaceSourceTraceView(
        knowledge_scope=knowledge_scope if knowledge_scope in {"none", "conversation_only", "shared"} else "shared",
        research_mode=research_mode if research_mode in {"hybrid", "imported_only", "search_only"} else "hybrid",
        retrieval_plan=clean_internal_context_text(str(grounding.get("retrieval_plan", "") or ""), max_length=180),
        retrieval_status=clean_internal_context_text(str(retrieval_outcome.get("status", "") or ""), max_length=80),
        retrieval_message=clean_internal_context_text(str(retrieval_outcome.get("message", "") or ""), max_length=240),
        filtered_out_count=int(retrieval_outcome.get("filtered_out_count", 0) or 0),
        real_paper_count=int(retrieval_outcome.get("real_paper_count", 0) or 0),
        total_paper_count=int(retrieval_outcome.get("total_paper_count", 0) or 0),
        fallback_used=bool(retrieval_outcome.get("fallback_used", False)),
        external_search_skipped=bool(retrieval_outcome.get("external_search_skipped", False)),
        refresh_triggered=bool(retrieval_outcome.get("refresh_triggered", False)),
        novel_paper_count=int(retrieval_outcome.get("novel_paper_count", 0) or 0),
        reused_paper_count=int(retrieval_outcome.get("reused_paper_count", 0) or 0),
        direct_paper_count=int(retrieval_outcome.get("direct_paper_count", 0) or 0),
        adjacent_paper_count=int(retrieval_outcome.get("adjacent_paper_count", 0) or 0),
        low_relevance_filtered_count=int(
            retrieval_outcome.get("low_relevance_filtered_count", 0) or 0
        ),
        evidence_pool_count=int(retrieval_outcome.get("evidence_pool_count", 0) or 0),
        analysis_paper_count=int(retrieval_outcome.get("analysis_paper_count", 0) or 0),
        broad_search_triggered=bool(retrieval_outcome.get("broad_search_triggered", False)),
        recall_rescue_triggered=bool(retrieval_outcome.get("recall_rescue_triggered", False)),
        facet_rescue_triggered=bool(retrieval_outcome.get("facet_rescue_triggered", False)),
        knowledge_hit_count=knowledge_hit_count,
        knowledge_hits=normalized_hits,
        workspace_hint_count=workspace_hint_count,
        workspace_hints=[str(item).strip() for item in workspace_hints if str(item).strip()][:5],
        recent_turn_count=recent_turn_count,
        recent_user_turns=[str(item).strip() for item in recent_user_turns if str(item).strip()][:3],
    )


def _build_inherited_context_view(trace: dict) -> WorkspaceInheritedContextView | None:
    bundle = _latest_research_context_bundle(trace)
    if not bundle:
        return None

    workspace_summary = clean_internal_context_text(str(bundle.get("workspace_summary", "") or ""), max_length=320)
    conversation_topic = clean_internal_context_text(str(bundle.get("conversation_topic", "") or ""), max_length=180)
    workspace_hints = [
        clean_internal_context_text(str(item), max_length=120)
        for item in (bundle.get("workspace_hints", []) or [])
    ]
    recent_turns = [
        clean_internal_context_text(str(item), max_length=180)
        for item in (bundle.get("recent_turns", []) or [])
    ]

    return WorkspaceInheritedContextView(
        conversation_topic=conversation_topic,
        workspace_summary=workspace_summary,
        workspace_hints=[item for item in workspace_hints if item][:5],
        recent_turns=[item for item in recent_turns if item][:4],
    )


def _normalize_workspace_summary(*, topic: str, summary: str, summary_payload: dict) -> str:
    summary_payload = summary_payload or {}
    if _looks_like_legacy_report_excerpt(summary):
        payload_summary = _summary_from_payload(topic=topic, summary_payload=summary_payload)
        if payload_summary:
            return payload_summary
    return _strip_report_noise(summary)


def _looks_like_legacy_report_excerpt(summary: str) -> bool:
    text = (summary or "").lower()
    return "```json" in text or "domain_name" in text or "专家 taxonomy" in text


def _summary_from_payload(*, topic: str, summary_payload: dict) -> str:
    if not isinstance(summary_payload, dict) or not summary_payload:
        return ""

    headline = str(summary_payload.get("headline", "") or "").strip()
    score = summary_payload.get("score")
    counts = summary_payload.get("counts", {}) or {}
    recommendation = str(summary_payload.get("recommendation", "") or "").strip()
    top_gaps = summary_payload.get("top_gaps", []) or []

    lines: list[str] = [headline or f"科研演进审计报告：{topic}"]

    metrics: list[str] = []
    papers = counts.get("papers")
    gaps = counts.get("gaps")
    ideas = counts.get("ideas")
    if papers is not None:
        metrics.append(f"论文 {papers} 篇")
    if gaps is not None:
        metrics.append(f"研究空白 {gaps} 条")
    if ideas is not None:
        metrics.append(f"研究建议 {ideas} 条")
    if isinstance(score, (int, float)):
        metrics.append(f"对齐分数 {float(score):.3f}")
    if metrics:
        lines.append("本轮分析共得到 " + "，".join(metrics) + "。")

    gap_summaries: list[str] = []
    for gap in top_gaps[:2]:
        if isinstance(gap, dict):
            gap_summary = str(gap.get("summary", "") or "").strip()
        else:
            gap_summary = str(gap).strip()
        if gap_summary:
            gap_summaries.append(gap_summary)
    if gap_summaries:
        lines.append("优先关注：" + "；".join(gap_summaries) + "。")

    if recommendation:
        lines.append("建议：" + recommendation)

    return "\n".join(line for line in lines if line).strip()


def _strip_report_noise(summary: str) -> str:
    text = str(summary or "")
    text = re.sub(r"```json[\s\S]*?```", "", text, flags=re.IGNORECASE)
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(
        r"(?:^|\n)\s*\d+\.\s*专家\s*Taxonomy[\s\S]*?(?=(?:\n\s*\d+\.\s)|\Z)",
        "\n",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
