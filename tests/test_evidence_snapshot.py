from __future__ import annotations

import unittest
from unittest.mock import patch

from product_agent.domain import ResearchIdea
from product_agent.models import EvolutionEdge, PaperNode
from product_agent.research_agent.nodes.synthesizer import synthesizer_node
from product_agent.services.evidence_snapshot_service import EvidenceSnapshotService
from product_agent.services.idea_generation_service import IdeaGenerationOutput
from product_agent.services.report_generation_service import ReportGenerationOutput
from product_agent.services.summary_generation_service import SummaryGenerationOutput
from product_agent.services.workspace_mapper import workspace_from_agent_state
from product_agent.services.workspace_service import WorkspaceService


class _WorkspaceRepository:
    def __init__(self, workspace) -> None:
        self.workspace = workspace

    def get_by_task(self, task_id: str):
        return self.workspace if self.workspace.task_id == task_id else None


class EvidenceSnapshotTests(unittest.TestCase):
    def test_workspace_exposes_full_evidence_pool_not_only_analysis_set(self) -> None:
        state = self._state()
        state["evidence_pool"] = {
            **state["paper_nodes"],
            "paper-c": PaperNode(
                paper_id="paper-c",
                title="Additional Qualified Evidence",
                abstract="A relevant neighboring study retained for user review.",
                source="arxiv",
                relevance_tier="adjacent",
                relevance_score=0.7,
            ),
        }

        workspace = workspace_from_agent_state(
            task_id="task-1",
            topic=state["topic"],
            state=state,
        )

        self.assertEqual(
            {paper.paper_id for paper in workspace.papers},
            {"paper-a", "paper-b", "paper-c"},
        )

    @patch(
        "product_agent.research_agent.nodes.synthesizer.SummaryGenerationService.run"
    )
    @patch(
        "product_agent.research_agent.nodes.synthesizer.ReportGenerationService.run"
    )
    @patch(
        "product_agent.research_agent.nodes.synthesizer.IdeaGenerationService.run"
    )
    def test_summary_distinguishes_retrieved_and_analyzed_papers(
        self,
        idea_run,
        report_run,
        summary_run,
    ) -> None:
        state = self._state()
        state["evidence_pool"] = {
            **state["paper_nodes"],
            "paper-c": PaperNode(
                paper_id="paper-c",
                title="Additional Qualified Evidence",
                source="arxiv",
            ),
        }
        idea_run.return_value = IdeaGenerationOutput([], "test")
        report_run.return_value = ReportGenerationOutput("report", "test", "report-1")
        summary_run.return_value = SummaryGenerationOutput({"counts": {}}, "test")

        updated = synthesizer_node(state)

        self.assertEqual(updated["final_report_summary"]["counts"]["papers"], 3)
        self.assertEqual(
            updated["final_report_summary"]["counts"]["papers_retrieved"],
            3,
        )
        self.assertEqual(
            updated["final_report_summary"]["counts"]["papers_analyzed"],
            2,
        )

    def _state(self) -> dict:
        return {
            "task_id": "task-1",
            "topic": "AI agent evaluation",
            "paper_nodes": {
                "paper-a": PaperNode(
                    paper_id="paper-a",
                    title="Agent Evaluation Benchmark",
                    abstract="A benchmark for tool-using agents.",
                    source="arxiv",
                    publish_date="2025",
                    expert_taxonomy_branches=["Evaluation"],
                    is_new_this_round=True,
                ),
                "paper-b": PaperNode(
                    paper_id="paper-b",
                    title="Fallback Survey",
                    abstract="Fallback evidence.",
                    source="seed",
                    publish_date="2024",
                    expert_taxonomy_branches=["Evaluation"],
                ),
            },
            "expert_taxonomy": {
                "taxonomy": {
                    "Evaluation": {
                        "description": "Evaluation methods",
                        "required_concepts": ["benchmark"],
                    }
                }
            },
            "evolution_graph": [
                EvolutionEdge(
                    source="paper-b",
                    target="paper-a",
                    relationship="citation",
                    provenance="explicit_reference",
                    confidence=1.0,
                    evidence_level="confirmed",
                    evidence="paper-a references paper-b",
                )
            ],
            "detected_gaps": [
                {
                    "id": "gap-1",
                    "description": "Missing reliability evaluation",
                    "severity": "high",
                    "evidence": ["Only one benchmark covers reliability."],
                }
            ],
            "audit_reports": [{"status": "warning"}],
            "retrieval_plan": {"strict_queries": ["agent evaluation benchmark"]},
            "retrieval_outcome": {"status": "success", "novel_paper_count": 1},
            "alignment_score": 0.8,
            "logs": [],
        }

    def test_snapshot_id_is_stable_and_stats_are_auditable(self) -> None:
        state = self._state()
        service = EvidenceSnapshotService()

        first = service.build(
            topic=state["topic"],
            papers=state["paper_nodes"],
            taxonomy=state["expert_taxonomy"],
            edges=state["evolution_graph"],
            gaps=state["detected_gaps"],
            retrieval_plan=state["retrieval_plan"],
            retrieval_outcome=state["retrieval_outcome"],
            alignment_score=state["alignment_score"],
            audit_reports=state["audit_reports"],
        )
        second = service.build(
            topic=state["topic"],
            papers=state["paper_nodes"],
            taxonomy=state["expert_taxonomy"],
            edges=state["evolution_graph"],
            gaps=state["detected_gaps"],
            retrieval_plan=state["retrieval_plan"],
            retrieval_outcome=state["retrieval_outcome"],
            alignment_score=state["alignment_score"],
            audit_reports=state["audit_reports"],
        )

        self.assertEqual(first["snapshot_id"], second["snapshot_id"])
        self.assertEqual(first["stats"]["paper_count"], 2)
        self.assertEqual(first["stats"]["real_paper_count"], 1)
        self.assertEqual(first["stats"]["fallback_paper_count"], 1)
        self.assertEqual(first["stats"]["evidence_level_counts"]["confirmed"], 1)
        self.assertEqual(first["stats"]["evidence_backed_gap_count"], 1)

    @patch("product_agent.research_agent.nodes.synthesizer.SummaryGenerationService.run")
    @patch("product_agent.research_agent.nodes.synthesizer.ReportGenerationService.run")
    @patch("product_agent.research_agent.nodes.synthesizer.IdeaGenerationService.run")
    def test_all_generators_and_workspace_share_one_snapshot(
        self,
        idea_run,
        report_run,
        summary_run,
    ) -> None:
        idea = ResearchIdea(
            idea_id="idea-1",
            title="Evaluate reliability",
            motivation="Evidence gap",
            approach="Build a benchmark",
            feasibility="Existing data",
            contribution="Reliable evaluation",
            related_papers=["paper-a"],
            derived_from_gaps=["gap-1"],
            confidence=0.8,
            tags=["evaluation"],
            raw_text="",
        )
        idea_run.return_value = IdeaGenerationOutput([idea], "test")
        report_run.return_value = ReportGenerationOutput("report", "test", "report-1")
        summary_run.return_value = SummaryGenerationOutput(
            {"headline": "summary", "counts": {"papers": 2, "gaps": 1, "ideas": 1}},
            "test",
        )

        updated = synthesizer_node(self._state())

        idea_snapshot = idea_run.call_args.args[0].evidence_snapshot
        report_snapshot = report_run.call_args.args[0].evidence_snapshot
        summary_snapshot = summary_run.call_args.args[0].evidence_snapshot
        snapshot_id = updated["evidence_snapshot"]["snapshot_id"]
        self.assertEqual(idea_snapshot["snapshot_id"], snapshot_id)
        self.assertEqual(report_snapshot["snapshot_id"], snapshot_id)
        self.assertEqual(summary_snapshot["snapshot_id"], snapshot_id)
        self.assertEqual(
            idea_run.call_args.args[0].papers,
            updated["evidence_snapshot"]["papers"],
        )
        self.assertEqual(
            report_run.call_args.args[0].audit_reports,
            updated["evidence_snapshot"]["audit_reports"],
        )
        self.assertEqual(
            summary_run.call_args.args[0].detected_gaps,
            updated["evidence_snapshot"]["gaps"],
        )

        workspace = workspace_from_agent_state(
            task_id="task-1",
            topic=updated["topic"],
            state=updated,
        )
        self.assertEqual(
            workspace.summary_payload["evidence_snapshot_id"],
            snapshot_id,
        )

        response = WorkspaceService(_WorkspaceRepository(workspace)).get_workspace_snapshot("task-1")
        self.assertIsNotNone(response)
        self.assertIsNotNone(response.evidence_snapshot)
        self.assertEqual(response.evidence_snapshot.snapshot_id, snapshot_id)
        self.assertEqual(response.evidence_snapshot.stats["paper_count"], 2)


if __name__ == "__main__":
    unittest.main()
