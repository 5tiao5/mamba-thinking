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
    assert any(check.claim_type == "impact" and check.status == "unknown" for check in view.paper_brief.claim_checks)


def test_paper_brief_prefers_uploaded_full_text_claim_evidence() -> None:
    paper = PaperRecord(
        paper_id="paper-full-text",
        title="Lightweight Multimodal Fusion for Robot Vision",
        abstract="A short abstract.",
        review_text=(
            "Introduction. Robot vision systems require lightweight multimodal fusion. "
            "Method. We propose a compact fusion architecture that aligns camera and language features. "
            "Experiments evaluate robustness under missing modalities."
        ),
        source="user_upload",
        origin="user_upload",
        document_id="doc-1",
        citation_count_known=True,
    )

    view = _workspace_paper_view(paper, topic="面向机器人视觉的轻量级多模态融合")

    assert view.paper_brief.source == "full_text"
    assert view.paper_brief.claim_checks
    assert view.paper_brief.claim_checks[0].source_level == "full_text"
    assert "robot vision systems require" in " ".join(
        check.evidence.lower() for check in view.paper_brief.claim_checks
    )
    assert "正文片段级核查" in view.paper_brief.claim_checks[0].caveat


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
