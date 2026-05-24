from __future__ import annotations

import hashlib
import re
from collections import OrderedDict, defaultdict

from product_agent.repositories import ConversationRepository, ResearchTaskRepository, WorkspaceRepository
from product_agent.schemas import (
    WorkspaceEvidenceStatusView,
    WorkspaceGapView,
    WorkspaceGraphEdgeView,
    WorkspaceIdeaView,
    WorkspacePaperView,
    WorkspaceSnapshotResponse,
    WorkspaceTraceView,
)


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
    ) -> None:
        self.repository = repository
        self.conversation_repository = conversation_repository
        self.task_repository = task_repository
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

        merged_summary = _merge_workspace_summaries(topic=topic, workspaces=valid_workspaces)
        merged_papers = _merge_workspace_papers(valid_workspaces)
        merged_graph_edges = _merge_workspace_graph_edges(valid_workspaces)
        merged_gaps = _merge_workspace_gaps(valid_workspaces)
        merged_ideas = _merge_workspace_ideas(valid_workspaces)
        merged_taxonomy = _merge_workspace_taxonomy(valid_workspaces)
        merged_trace = _merge_workspace_trace(valid_workspaces, tasks)
        merged_alignment = round(
            sum(workspace.alignment_score for workspace in valid_workspaces) / len(valid_workspaces), 3
        )

        synthetic_workspace = type("ConversationWorkspaceProjection", (), {})()
        synthetic_workspace.task_id = f"conversation::{conversation_id}"
        synthetic_workspace.topic = topic
        synthetic_workspace.summary = merged_summary
        synthetic_workspace.summary_payload = {}
        synthetic_workspace.papers = merged_papers
        synthetic_workspace.taxonomy = merged_taxonomy
        synthetic_workspace.graph_edges = merged_graph_edges
        synthetic_workspace.gaps = merged_gaps
        synthetic_workspace.ideas = merged_ideas
        synthetic_workspace.alignment_score = merged_alignment
        synthetic_workspace.trace = merged_trace

        trace = synthetic_workspace.trace or {}
        evidence_status = _build_evidence_status(synthetic_workspace)
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


def _build_evidence_status(workspace) -> dict:
    papers = list(workspace.papers or [])
    total_papers = len(papers)
    fallback_papers = [paper for paper in papers if (paper.source or "").lower() == "fallback"]
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


def _merge_workspace_summaries(*, topic: str, workspaces: list) -> str:
    latest_summary = next((workspace.summary for workspace in workspaces if workspace.summary), "")
    paper_count = len(_merge_workspace_papers(workspaces))
    gap_count = len(_merge_workspace_gaps(workspaces))
    idea_count = len(_merge_workspace_ideas(workspaces))
    task_count = len(workspaces)

    lines = [
        f"{topic} 的会话级研究工作台",
        f"当前累计 {task_count} 轮有效研究，汇总论文 {paper_count} 篇、研究空白 {gap_count} 条、研究建议 {idea_count} 条。",
    ]
    if latest_summary:
        lines.append(f"最近一轮摘要：{_strip_report_noise(latest_summary)[:220]}")
    return "\n".join(lines)


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


def _normalize_trace_entries(entries) -> list[dict]:
    normalized: list[dict] = []
    for index, entry in enumerate(entries or []):
        if isinstance(entry, dict):
            normalized.append(entry)
        else:
            normalized.append({"step": index + 1, "content": str(entry)})
    return normalized


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
