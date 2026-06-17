from __future__ import annotations

from product_agent.domain import GapRecord, ResearchIdeaRecord
from product_agent.models import PaperNode
from product_agent.repositories.sqlite_store import SQLiteWorkspaceRepository
from product_agent.services.workspace_mapper import workspace_from_agent_state
from product_agent.services.workspace_service import WorkspaceService


class _WorkspaceRepository:
    def __init__(self, workspace) -> None:
        self.workspace = workspace

    def get_by_task(self, task_id: str):
        return self.workspace if self.workspace.task_id == task_id else None


def _state() -> dict:
    paper = PaperNode(
        paper_id="paper-core",
        title="Grounded Multimodal Fusion",
        abstract="A directly relevant multimodal fusion paper.",
        relevance_tier="direct",
    )
    return {
        "topic": "multimodal fusion",
        "paper_nodes": {paper.paper_id: paper},
        "evidence_pool": {paper.paper_id: paper},
        "detected_gaps": [
            {
                "id": "gap-1",
                "description": "Missing robustness evaluation.",
                "related_papers": ["paper-core", "shared-knowledge-document"],
                "evidence": ["The current paper set does not evaluate missing modalities."],
            }
        ],
        "generated_ideas": [
            {
                "id": "idea-1",
                "title": "Robust fusion under missing modalities",
                "motivation": "The gap remains open.",
                "related_papers": ["paper-core", "paper-outside-analysis"],
                "derived_from_gaps": ["gap-1"],
            }
        ],
        "expert_taxonomy": {},
        "evolution_graph": [],
        "alignment_score": 0.7,
    }


def test_workspace_contract_only_accepts_current_analysis_papers() -> None:
    workspace = workspace_from_agent_state(
        task_id="task-1",
        topic="multimodal fusion",
        state=_state(),
    )

    assert workspace.gaps[0].supporting_paper_ids == ["paper-core"]
    assert workspace.gaps[0].evidence_level == "indirect"
    assert "full-text" in workspace.gaps[0].evidence_reason
    assert workspace.evidence_status["total_papers"] == 1

    assert workspace.ideas[0].supporting_paper_ids == ["paper-core"]
    assert workspace.ideas[0].related_papers == ["paper-core"]
    assert workspace.ideas[0].evidence_level == "indirect"


def test_workspace_api_exposes_conclusion_evidence_contract() -> None:
    workspace = workspace_from_agent_state(
        task_id="task-1",
        topic="multimodal fusion",
        state=_state(),
    )

    response = WorkspaceService(_WorkspaceRepository(workspace)).get_workspace_snapshot("task-1")

    assert response.gaps[0].supporting_paper_ids == ["paper-core"]
    assert response.gaps[0].evidence_level == "indirect"
    assert response.ideas[0].supporting_paper_ids == ["paper-core"]
    assert response.ideas[0].evidence_reason


def test_persistence_and_legacy_records_keep_contract_defaults() -> None:
    legacy_gap = GapRecord(
        **{
            "gap_id": "gap-old",
            "task_id": "task-old",
            "summary": "Legacy gap",
        }
    )
    legacy_idea = ResearchIdeaRecord(
        **{
            "idea_id": "idea-old",
            "task_id": "task-old",
            "title": "Legacy idea",
            "motivation": "",
            "approach": "",
            "feasibility": "",
            "contribution": "",
        }
    )

    assert legacy_gap.supporting_paper_ids == []
    assert legacy_gap.evidence_level == "exploratory"
    assert legacy_idea.supporting_paper_ids == []
    assert legacy_idea.evidence_level == "exploratory"

    persisted_gap = SQLiteWorkspaceRepository._gap_to_dict(
        GapRecord(
            gap_id="gap-new",
            task_id="task-new",
            summary="Grounded gap",
            supporting_paper_ids=["paper-core"],
            evidence_level="direct",
            evidence_reason="Verified against paper text.",
        )
    )
    persisted_idea = SQLiteWorkspaceRepository._idea_to_dict(
        ResearchIdeaRecord(
            idea_id="idea-new",
            task_id="task-new",
            title="Grounded idea",
            motivation="",
            approach="",
            feasibility="",
            contribution="",
            supporting_paper_ids=["paper-core"],
            evidence_level="direct",
            evidence_reason="Verified against paper text.",
        )
    )

    assert persisted_gap["supporting_paper_ids"] == ["paper-core"]
    assert persisted_gap["evidence_level"] == "direct"
    assert persisted_idea["supporting_paper_ids"] == ["paper-core"]
    assert persisted_idea["evidence_reason"] == "Verified against paper text."
