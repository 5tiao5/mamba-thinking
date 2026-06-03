from __future__ import annotations

import hashlib
import re
from collections import OrderedDict, defaultdict

from product_agent.repositories import ConversationRepository, ResearchTaskRepository, WorkspaceRepository
from product_agent.schemas import (
    WorkspaceEvidenceStatusView,
    WorkspaceGapView,
    WorkspaceGraphEdgeView,
    WorkspaceInheritedContextView,
    WorkspaceIdeaView,
    WorkspaceKnowledgeHitView,
    WorkspacePaperView,
    WorkspaceSnapshotResponse,
    WorkspaceSourceTraceView,
    WorkspaceTraceView,
    WorkspaceWorkingMemoryView,
)
from product_agent.services.text_cleaning import clean_internal_context_items, clean_internal_context_text


_CONV_CACHE_MAX_SIZE = 128


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
        return WorkspaceSnapshotResponse(
            task_id=workspace.task_id,
            topic=workspace.topic,
            summary=summary,
            papers=[
                WorkspacePaperView(
                    paper_id=paper.paper_id,
                    title=paper.title,
                    publish_date=paper.publish_date,
                    source=paper.source,
                    taxonomy_category=paper.taxonomy_category,
                    citation_count=paper.citation_count,
                    url=paper.url,
                    is_new_this_round=bool(getattr(paper, "is_new_this_round", False)),
                )
                for paper in workspace.papers
            ],
            taxonomy=workspace.taxonomy,
            graph_edges=[
                WorkspaceGraphEdgeView(
                    source=str(edge.get("source", "")),
                    target=str(edge.get("target", "")),
                    relationship=str(edge.get("relationship", "")),
                    reasoning=str(edge.get("reasoning", "")),
                )
                for edge in workspace.graph_edges
            ],
            gaps=[
                WorkspaceGapView(
                    summary=gap.summary,
                    severity=gap.severity,
                    evidence=list(gap.evidence),
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
                    raw_text="",
                )
                for idea in workspace.ideas
            ],
            alignment_score=workspace.alignment_score,
            evidence_status=WorkspaceEvidenceStatusView(**evidence_status),
            source_trace=source_trace,
            inherited_context=inherited_context,
            working_memory=working_memory,
            trace=WorkspaceTraceView(
                thought_trace=_normalize_trace_entries(trace.get("thought_trace", [])),
                action_history=_normalize_trace_entries(trace.get("action_history", [])),
                context_inputs=_normalize_trace_entries(trace.get("context_inputs", [])),
            ),
        )

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
            if task.conversation_id == conversation_id and task.status == "completed"
        ]
        if not tasks:
            return None

        tasks.sort(key=lambda item: item.updated_at, reverse=True)
        workspaces = [self.repository.get_by_task(task.task_id) for task in tasks]
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
        merged_summary_payload = _build_conversation_summary_payload(
            topic=topic,
            workspaces=valid_workspaces,
            papers=merged_papers,
            gaps=merged_gaps,
            ideas=merged_ideas,
            alignment_score=merged_alignment,
        )
        merged_summary = _merge_workspace_summaries(
            topic=topic,
            workspaces=valid_workspaces,
            paper_count=len(merged_papers),
            gap_count=len(merged_gaps),
            idea_count=len(merged_ideas),
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
        result = WorkspaceSnapshotResponse(
            task_id=synthetic_workspace.task_id,
            topic=synthetic_workspace.topic,
            summary=synthetic_workspace.summary,
            papers=[
                WorkspacePaperView(
                    paper_id=paper.paper_id,
                    title=paper.title,
                    publish_date=paper.publish_date,
                    source=paper.source,
                    taxonomy_category=paper.taxonomy_category,
                    citation_count=paper.citation_count,
                    url=paper.url,
                    is_new_this_round=False,
                )
                for paper in synthetic_workspace.papers
            ],
            taxonomy=synthetic_workspace.taxonomy,
            graph_edges=[
                WorkspaceGraphEdgeView(
                    source=str(edge.get("source", "")),
                    target=str(edge.get("target", "")),
                    relationship=str(edge.get("relationship", "")),
                    reasoning=str(edge.get("reasoning", "")),
                )
                for edge in synthetic_workspace.graph_edges
            ],
            gaps=[
                WorkspaceGapView(
                    summary=gap.summary,
                    severity=gap.severity,
                    evidence=list(gap.evidence),
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
                    raw_text="",
                )
                for idea in synthetic_workspace.ideas
            ],
            alignment_score=synthetic_workspace.alignment_score,
            evidence_status=WorkspaceEvidenceStatusView(**evidence_status),
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


def _merge_workspace_summaries(
    *,
    topic: str,
    workspaces: list,
    paper_count: int | None = None,
    gap_count: int | None = None,
    idea_count: int | None = None,
) -> str:
    paper_count = len(_merge_workspace_papers(workspaces)) if paper_count is None else paper_count
    gap_count = len(_merge_workspace_gaps(workspaces)) if gap_count is None else gap_count
    idea_count = len(_merge_workspace_ideas(workspaces)) if idea_count is None else idea_count
    task_count = len(workspaces)

    lines = [
        f"{topic} 的会话级研究工作台",
        f"当前累计 {task_count} 轮有效研究，汇总论文 {paper_count} 篇、研究空白 {gap_count} 条、研究建议 {idea_count} 条。",
    ]
    return "\n".join(lines)


def _build_conversation_summary_payload(
    *,
    topic: str,
    workspaces: list,
    papers: list,
    gaps: list,
    ideas: list,
    alignment_score: float,
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
        }
    )
    return payload


def _merge_workspace_papers(workspaces: list) -> list:
    merged: dict[str, object] = {}
    for workspace in reversed(workspaces):
        for paper in workspace.papers:
            merged[paper.paper_id] = paper
    return list(merged.values())


def _merge_workspace_graph_edges(workspaces: list) -> list[dict]:
    merged: dict[tuple[str, str, str], dict] = {}
    for workspace in workspaces:
        for edge in workspace.graph_edges:
            key = (
                str(edge.get("source", "")),
                str(edge.get("target", "")),
                str(edge.get("relationship", "")),
            )
            merged[key] = edge
    return list(merged.values())


def _merge_workspace_gaps(workspaces: list) -> list:
    merged: dict[str, object] = {}
    for workspace in workspaces:
        for gap in workspace.gaps:
            key = getattr(gap, "gap_id", "") or _stable_text_id(f"gap::{gap.summary}")
            merged[key] = gap
    return list(merged.values())


def _merge_workspace_ideas(workspaces: list) -> list:
    merged: dict[str, object] = {}
    for workspace in workspaces:
        for idea in workspace.ideas:
            key = getattr(idea, "idea_id", "") or _stable_text_id(f"idea::{idea.title}")
            merged[key] = idea
    return list(merged.values())


def _merge_workspace_taxonomy(workspaces: list) -> dict:
    branches_by_id: dict[str, dict] = {}
    coverage_accumulator: dict[str, dict[str, float]] = defaultdict(
        lambda: {"paper_count": 0.0, "gap_count": 0.0, "coverage_score_sum": 0.0, "coverage_samples": 0.0}
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
                existing["paper_count"] = max(int(existing.get("paper_count", 0) or 0), int(branch.get("paper_count", 0) or 0))

        coverage = taxonomy.get("coverage", {}) or {}
        for branch_id, entry in coverage.items():
            if not isinstance(entry, dict):
                continue
            accumulator = coverage_accumulator[str(branch_id)]
            accumulator["paper_count"] += float(entry.get("paper_count", 0) or 0)
            accumulator["gap_count"] += float(entry.get("gap_count", 0) or 0)
            accumulator["coverage_score_sum"] += float(entry.get("coverage_score", 0.0) or 0.0)
            accumulator["coverage_samples"] += 1.0

    merged_branches = sorted(
        branches_by_id.values(),
        key=lambda branch: (int(branch.get("paper_count", 0) or 0), str(branch.get("name", ""))),
        reverse=True,
    )

    merged_coverage: dict[str, dict] = {}
    for branch_id, accumulator in coverage_accumulator.items():
        samples = accumulator["coverage_samples"] or 1.0
        merged_coverage[branch_id] = {
            "paper_count": int(round(accumulator["paper_count"])),
            "gap_count": int(round(accumulator["gap_count"])),
            "coverage_score": round(accumulator["coverage_score_sum"] / samples, 3),
        }

    return {
        "branches": merged_branches,
        "coverage": merged_coverage,
        "tree": [],
        "raw": {
            "aggregation_mode": "conversation_workspace",
            "source_workspace_count": len(workspaces),
        },
    }


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
        retrieval_plan=clean_internal_context_text(str(grounding.get("retrieval_plan", "") or ""), max_length=180),
        retrieval_status=clean_internal_context_text(str(retrieval_outcome.get("status", "") or ""), max_length=80),
        retrieval_message=clean_internal_context_text(str(retrieval_outcome.get("message", "") or ""), max_length=240),
        filtered_out_count=int(retrieval_outcome.get("filtered_out_count", 0) or 0),
        fallback_used=bool(retrieval_outcome.get("fallback_used", False)),
        refresh_triggered=bool(retrieval_outcome.get("refresh_triggered", False)),
        novel_paper_count=int(retrieval_outcome.get("novel_paper_count", 0) or 0),
        reused_paper_count=int(retrieval_outcome.get("reused_paper_count", 0) or 0),
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
