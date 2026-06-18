from __future__ import annotations

from datetime import datetime, timedelta, timezone

from product_agent.domain import (
    GapRecord,
    PaperRecord,
    ResearchIdeaRecord,
    ResearchTask,
    ResearchWorkspace,
)
from product_agent.services.workspace_service import (
    WorkspaceService,
    _merge_workspace_gaps,
    _merge_workspace_ideas,
    _merge_workspace_papers,
    _paper_brief_llm_slots,
    _workspace_paper_view,
    _select_conversation_analysis_paper_ids,
)


class _WorkspaceRepository:
    def __init__(self, workspaces):
        self.workspaces = workspaces

    def get_by_task(self, task_id):
        return self.workspaces.get(task_id)


class _TaskRepository:
    def __init__(self, tasks):
        self.tasks = {task.task_id: task for task in tasks}

    def get(self, task_id):
        return self.tasks.get(task_id)

    def list_all(self):
        return list(self.tasks.values())


def test_conversation_workspace_preserves_richer_paper_metadata() -> None:
    older = ResearchWorkspace(
        task_id="task-initial",
        topic="multimodal fusion",
        papers=[
            PaperRecord(
                paper_id="paper-a",
                title="Paper A",
                abstract="A detailed abstract from the initial research round.",
                authors=["Author One"],
                keywords=["multimodal fusion"],
                citation_count=70,
                citation_count_known=True,
                citation_source="semantic_scholar",
                url="https://example.test/paper-a",
                relevance_score=0.8,
                relevance_tier="direct",
                relevance_reasons=["topic_match"],
            )
        ],
    )
    newer = ResearchWorkspace(
        task_id="task-follow-up",
        topic="multimodal fusion follow-up",
        papers=[
            PaperRecord(
                paper_id="paper-a",
                title="Paper A",
                abstract="Short.",
                authors=["Author Two"],
                keywords=["alignment"],
                citation_count=0,
                citation_count_known=False,
                relevance_score=0.6,
                relevance_tier="adjacent",
                relevance_reasons=["follow_up_match"],
            )
        ],
    )

    merged = _merge_workspace_papers([newer, older])

    assert len(merged) == 1
    paper = merged[0]
    assert paper.citation_count == 70
    assert paper.citation_count_known is True
    assert paper.citation_source == "semantic_scholar"
    assert paper.abstract == "A detailed abstract from the initial research round."
    assert paper.url == "https://example.test/paper-a"
    assert paper.authors == ["Author One", "Author Two"]
    assert paper.keywords == ["multimodal fusion", "alignment"]
    assert paper.relevance_score == 0.8
    assert paper.relevance_tier == "direct"
    assert paper.relevance_reasons == ["topic_match", "follow_up_match"]


def test_conversation_workspace_accepts_newer_known_citation_count() -> None:
    older = ResearchWorkspace(
        task_id="task-initial",
        topic="topic",
        papers=[
            PaperRecord(
                paper_id="paper-a",
                title="Paper A",
                citation_count=70,
                citation_count_known=True,
                citation_source="semantic_scholar",
            )
        ],
    )
    newer = ResearchWorkspace(
        task_id="task-follow-up",
        topic="topic",
        papers=[
            PaperRecord(
                paper_id="paper-a",
                title="Paper A",
                citation_count=75,
                citation_count_known=True,
                citation_source="semantic_scholar",
            )
        ],
    )

    paper = _merge_workspace_papers([newer, older])[0]

    assert paper.citation_count == 75
    assert paper.citation_count_known is True


def test_existing_follow_up_snapshot_recovers_historical_citation_metadata() -> None:
    base_time = datetime(2026, 6, 14, tzinfo=timezone.utc)
    initial_task = ResearchTask(
        task_id="task-initial",
        conversation_id="conversation-1",
        topic="topic",
        status="completed",
        created_at=base_time,
        updated_at=base_time,
    )
    follow_up_task = ResearchTask(
        task_id="task-follow-up",
        conversation_id="conversation-1",
        topic="topic follow-up",
        status="degraded",
        created_at=base_time + timedelta(minutes=1),
        updated_at=base_time + timedelta(minutes=1),
    )
    initial_workspace = ResearchWorkspace(
        task_id=initial_task.task_id,
        topic=initial_task.topic,
        papers=[
            PaperRecord(
                paper_id="paper-a",
                title="Paper A",
                citation_count=70,
                citation_count_known=True,
                citation_source="semantic_scholar",
            )
        ],
    )
    follow_up_workspace = ResearchWorkspace(
        task_id=follow_up_task.task_id,
        topic=follow_up_task.topic,
        papers=[
            PaperRecord(
                paper_id="paper-a",
                title="Paper A",
                citation_count=0,
                citation_count_known=False,
            )
        ],
    )
    service = WorkspaceService(
        _WorkspaceRepository(
            {
                initial_task.task_id: initial_workspace,
                follow_up_task.task_id: follow_up_workspace,
            }
        ),
        task_repository=_TaskRepository([initial_task, follow_up_task]),
    )

    snapshot = service.get_workspace_snapshot(follow_up_task.task_id)

    assert snapshot is not None
    assert snapshot.papers[0].citation_count == 70
    assert snapshot.papers[0].citation_count_known is True
    assert snapshot.papers[0].is_new_this_round is False


def test_historical_metadata_inheritance_does_not_pollute_current_round_marker() -> None:
    base_time = datetime(2026, 6, 14, tzinfo=timezone.utc)
    historical_task = ResearchTask(
        task_id="task-historical",
        conversation_id="conversation-old",
        topic="topic",
        status="completed",
        created_at=base_time,
        updated_at=base_time,
    )
    current_task = ResearchTask(
        task_id="task-current",
        conversation_id="conversation-new",
        topic="topic follow-up",
        status="completed",
        created_at=base_time + timedelta(minutes=1),
        updated_at=base_time + timedelta(minutes=1),
    )
    historical_workspace = ResearchWorkspace(
        task_id=historical_task.task_id,
        topic=historical_task.topic,
        papers=[
            PaperRecord(
                paper_id="paper-a",
                title="Paper A",
                citation_count=88,
                citation_count_known=True,
                is_new_this_round=True,
            )
        ],
    )
    current_workspace = ResearchWorkspace(
        task_id=current_task.task_id,
        topic=current_task.topic,
        papers=[
            PaperRecord(
                paper_id="paper-a",
                title="Paper A",
                citation_count=0,
                citation_count_known=False,
                is_new_this_round=False,
            )
        ],
    )
    service = WorkspaceService(
        _WorkspaceRepository(
            {
                historical_task.task_id: historical_workspace,
                current_task.task_id: current_workspace,
            }
        ),
        task_repository=_TaskRepository([historical_task, current_task]),
    )

    snapshot = service.get_workspace_snapshot(current_task.task_id)

    assert snapshot is not None
    assert snapshot.papers[0].citation_count == 88
    assert snapshot.papers[0].citation_count_known is True
    assert snapshot.papers[0].is_new_this_round is False


def test_paper_brief_filters_internal_relevance_signals() -> None:
    paper = PaperRecord(
        paper_id="paper-a",
        title="QCaption: Video Captioning and Q&A through Fusion of Large Multimodal Models",
        source="arxiv",
        relevance_reasons=["focus:multimodal:title:multimodal", "user_selected:candidate"],
    )

    view = _workspace_paper_view(paper, topic="面向大模型的多模态融合")

    assert "focus:" not in view.paper_brief.contribution
    assert "user_selected:" not in view.paper_brief.contribution
    assert "focus:" not in view.paper_brief.relation_to_topic
    assert "user_selected:" not in view.paper_brief.relation_to_topic


def test_paper_brief_ignores_generic_label_only_relevance_reason() -> None:
    paper = PaperRecord(
        paper_id="paper-a",
        title="Evaluation Protocols for Multimodal Retrieval",
        source="arxiv",
        relevance_reasons=["evaluation"],
    )

    view = _workspace_paper_view(paper, topic="基于大模型的跨模态检索")

    assert "evaluation" not in view.paper_brief.contribution.casefold()
    assert "evaluation" not in view.paper_brief.relation_to_topic.casefold()
    assert all(check.claim.casefold() != "evaluation" for check in view.paper_brief.claim_checks)


def test_paper_brief_hides_snake_case_internal_relevance_reason() -> None:
    paper = PaperRecord(
        paper_id="paper-a",
        title="Orchestrating Multimodal DNN Workloads in Wireless Neural Processing",
        source="arxiv",
        taxonomy_category="Wireless Neural Processing",
        relevance_reasons=["team_process"],
    )

    view = _workspace_paper_view(paper, topic="通信计算 overlap 自动编排框架")
    brief_text = " ".join(
        [
            view.paper_brief.contribution,
            view.paper_brief.relation_to_topic,
            view.paper_brief.why_selected,
            view.paper_brief.read_focus,
            " ".join(check.claim for check in view.paper_brief.claim_checks),
        ]
    ).casefold()

    assert "team_process" not in brief_text
    assert "编排" in view.paper_brief.method
    assert "资源" in view.paper_brief.read_focus or "调度" in view.paper_brief.read_focus


def test_paper_brief_exposes_claim_checks_with_verification_boundary() -> None:
    paper = PaperRecord(
        paper_id="paper-a",
        title="Lightweight Multimodal Fusion for Robot Vision",
        abstract=(
            "This paper proposes a lightweight multimodal fusion architecture for robot vision. "
            "The method aligns visual and language features under missing-modality conditions."
        ),
        source="arxiv",
        taxonomy_category="Robot Vision Fusion",
        citation_count=0,
        citation_count_known=False,
    )

    view = _workspace_paper_view(paper, topic="面向机器人视觉的轻量级多模态融合")

    assert view.paper_brief.claim_checks
    assert view.paper_brief.claim_checks[0].status == "partial"
    assert view.paper_brief.claim_checks[0].source_level == "abstract"
    assert "lightweight multimodal fusion" in view.paper_brief.claim_checks[0].evidence.lower()
    assert "候选证据" in view.paper_brief.why_selected or "直接相关" in view.paper_brief.why_selected
    assert "重点看" in view.paper_brief.read_focus or "先看" in view.paper_brief.read_focus
    assert "摘要" in view.paper_brief.evidence_basis
    assert "摘要级核查" in view.paper_brief.verification_boundary
    assert any(check.claim_type == "method_claim" for check in view.paper_brief.claim_checks)
    assert any(check.claim_type == "impact" and check.status == "unknown" for check in view.paper_brief.claim_checks)


def test_paper_brief_uses_full_text_claim_evidence_only_after_verification() -> None:
    paper = PaperRecord(
        paper_id="paper-full-text",
        title="Lightweight Multimodal Fusion for Robot Vision",
        abstract="A short abstract.",
        review_text=(
            "[Page 1]\n"
            "Introduction\n"
            "Introduction. Robot vision systems require lightweight multimodal fusion.\n"
            "[Page 2]\n"
            "Method\n"
            "Method. We propose a compact fusion architecture that aligns camera and language features.\n"
            "[Page 3]\n"
            "Experiments\n"
            "Experiments evaluate robustness under missing modalities."
        ),
        source="user_upload",
        origin="user_upload",
        document_id="doc-1",
        citation_count_known=True,
    )

    view = _workspace_paper_view(paper, topic="面向机器人视觉的轻量级多模态融合")
    verified_view = _workspace_paper_view(
        paper,
        topic="面向机器人视觉的轻量级多模态融合",
        verification_mode="full",
    )

    assert view.paper_brief.source == "full_text"
    assert view.paper_brief.claim_checks
    assert all(check.source_level != "full_text" for check in view.paper_brief.claim_checks)
    assert "正文片段" in view.paper_brief.evidence_basis
    assert "正文片段级核查" in view.paper_brief.verification_boundary
    assert verified_view.paper_brief.source == "full_text_verified"
    assert "robot vision systems require" in " ".join(
        check.evidence.lower() for check in verified_view.paper_brief.claim_checks
    )
    assert "全文片段级核查" in verified_view.paper_brief.claim_checks[0].caveat
    assert any(check.claim_type == "evaluation_claim" for check in verified_view.paper_brief.claim_checks)
    assert any(check.source_level == "full_text" and check.page > 0 for check in verified_view.paper_brief.claim_checks)
    assert all(check.confidence >= 0 for check in verified_view.paper_brief.claim_checks)


def test_new_conversation_recovers_known_citations_from_historical_workspace() -> None:
    base_time = datetime(2026, 6, 14, tzinfo=timezone.utc)
    historical_task = ResearchTask(
        task_id="task-historical",
        conversation_id="conversation-old",
        topic="topic",
        status="completed",
        created_at=base_time,
        updated_at=base_time,
    )
    current_task = ResearchTask(
        task_id="task-current",
        conversation_id="conversation-new",
        topic="topic",
        status="completed",
        created_at=base_time + timedelta(minutes=1),
        updated_at=base_time + timedelta(minutes=1),
    )
    historical_workspace = ResearchWorkspace(
        task_id=historical_task.task_id,
        topic=historical_task.topic,
        papers=[
            PaperRecord(
                paper_id="paper-a",
                title="Paper A",
                citation_count=70,
                citation_count_known=True,
                citation_source="semantic_scholar",
            )
        ],
    )
    current_workspace = ResearchWorkspace(
        task_id=current_task.task_id,
        topic=current_task.topic,
        papers=[
            PaperRecord(
                paper_id="paper-a",
                title="Paper A",
                citation_count=0,
                citation_count_known=False,
            )
        ],
    )
    service = WorkspaceService(
        _WorkspaceRepository(
            {
                historical_task.task_id: historical_workspace,
                current_task.task_id: current_workspace,
            }
        ),
        task_repository=_TaskRepository([historical_task, current_task]),
    )

    snapshot = service.get_workspace_snapshot(current_task.task_id)

    assert snapshot is not None
    assert snapshot.papers[0].citation_count == 70
    assert snapshot.papers[0].citation_count_known is True


def test_conversation_workspace_keeps_same_local_idea_ids_across_rounds() -> None:
    newer = ResearchWorkspace(
        task_id="task-follow-up",
        topic="topic follow-up",
        ideas=[
            ResearchIdeaRecord(
                idea_id="idea_1",
                task_id="task-follow-up",
                title="Follow-up recommendation",
                motivation="new evidence",
                approach="new approach",
                feasibility="medium",
                contribution="new contribution",
            )
        ],
    )
    older = ResearchWorkspace(
        task_id="task-initial",
        topic="topic",
        ideas=[
            ResearchIdeaRecord(
                idea_id="idea_1",
                task_id="task-initial",
                title="Initial recommendation",
                motivation="initial evidence",
                approach="initial approach",
                feasibility="medium",
                contribution="initial contribution",
            )
        ],
    )

    merged = _merge_workspace_ideas([newer, older])

    assert [idea.title for idea in merged] == [
        "Follow-up recommendation",
        "Initial recommendation",
    ]


def test_conversation_workspace_keeps_same_local_gap_ids_across_rounds() -> None:
    newer = ResearchWorkspace(
        task_id="task-follow-up",
        topic="topic follow-up",
        gaps=[
            GapRecord(
                gap_id="gap_1",
                task_id="task-follow-up",
                summary="Follow-up gap",
            )
        ],
    )
    older = ResearchWorkspace(
        task_id="task-initial",
        topic="topic",
        gaps=[
            GapRecord(
                gap_id="gap_1",
                task_id="task-initial",
                summary="Initial gap",
            )
        ],
    )

    merged = _merge_workspace_gaps([newer, older])

    assert [gap.summary for gap in merged] == ["Follow-up gap", "Initial gap"]


def test_conversation_core_papers_keep_recent_majority_and_historical_value() -> None:
    papers = [
        PaperRecord(
            paper_id=f"paper-{index}",
            title=f"Paper {index}",
            citation_count=100 if index == 10 else index,
            citation_count_known=True,
            relevance_score=0.9,
            relevance_tier="direct",
        )
        for index in range(14)
    ]
    latest = ResearchWorkspace(
        task_id="latest",
        topic="topic follow-up",
        summary_payload={"analysis_paper_ids": [f"paper-{index}" for index in range(8)]},
    )
    older = ResearchWorkspace(
        task_id="older",
        topic="topic",
        summary_payload={"analysis_paper_ids": [f"paper-{index}" for index in range(4, 14)]},
    )

    selected = _select_conversation_analysis_paper_ids(
        workspaces=[latest, older],
        papers=papers,
        llm_recommended_paper_ids=["paper-10"],
    )

    assert len(selected) == 12
    assert len(set(selected) & {f"paper-{index}" for index in range(8)}) == 8
    assert "paper-10" in selected


def test_paper_brief_llm_slots_prioritize_important_papers(monkeypatch) -> None:
    monkeypatch.setenv("ENABLE_PAPER_BRIEF_LLM", "1")
    monkeypatch.setenv("PAPER_BRIEF_LLM_MAX_PER_WORKSPACE", "2")
    monkeypatch.setattr(
        "product_agent.services.workspace_service.paper_brief_llm_enabled",
        lambda: True,
    )
    candidate = PaperRecord(
        paper_id="candidate",
        title="Candidate Paper",
        abstract="A candidate paper with some abstract.",
        relevance_score=0.5,
        relevance_tier="candidate",
    )
    core = PaperRecord(
        paper_id="core",
        title="Core Paper",
        abstract="A core paper with direct evidence.",
        relevance_score=0.7,
        relevance_tier="direct",
        paper_pool_status="core",
    )
    uploaded = PaperRecord(
        paper_id="uploaded",
        title="Uploaded Paper",
        abstract="A user uploaded paper.",
        review_text="[Page 1] Method. The paper introduces a method.",
        origin="user_upload",
    )
    new_direct = PaperRecord(
        paper_id="new",
        title="New Direct Paper",
        abstract="A new direct paper.",
        relevance_score=0.9,
        relevance_tier="direct",
        is_new_this_round=True,
    )

    slots = _paper_brief_llm_slots([candidate, core, uploaded, new_direct])

    assert set(slots.keys()) == {id(uploaded), id(core)}
    assert slots[id(uploaded)] == 1
    assert slots[id(core)] == 2


def test_workspace_paper_verification_is_on_demand() -> None:
    paper = PaperRecord(
        paper_id="paper-fulltext",
        title="FusionBench: A Benchmark for Multimodal Fusion Robustness",
        abstract=(
            "FusionBench proposes a multimodal fusion benchmark and evaluates "
            "robustness under missing modality settings."
        ),
        review_text=(
            "[Page 1]\nAbstract\n"
            "FusionBench proposes a benchmark for multimodal fusion robustness and "
            "addresses missing modality failures in real systems. "
            "[Page 2]\nMethod\n"
            "The method introduces a fusion framework with alignment modules and "
            "robust missing modality handling. "
            "[Page 3]\nEvaluation\n"
            "Experiments evaluate performance on benchmark tasks and show improved "
            "robustness against missing modalities."
        ),
        origin="user_upload",
        source="user_upload",
        relevance_tier="direct",
        paper_pool_status="core",
    )
    workspace = ResearchWorkspace(
        task_id="task-paper-verify",
        topic="multimodal fusion robustness",
        papers=[paper],
    )
    service = WorkspaceService(_WorkspaceRepository({workspace.task_id: workspace}))

    standard_snapshot = service.get_workspace_snapshot(workspace.task_id)
    verified_paper = service.verify_workspace_paper(workspace.task_id, paper.paper_id)

    assert standard_snapshot is not None
    assert standard_snapshot.papers[0].paper_brief.source == "full_text"
    assert all(
        check.source_level != "full_text"
        for check in standard_snapshot.papers[0].paper_brief.claim_checks
    )
    assert verified_paper is not None
    assert verified_paper.paper_brief.source == "full_text_verified"
    assert any(check.source_level == "full_text" for check in verified_paper.paper_brief.claim_checks)
