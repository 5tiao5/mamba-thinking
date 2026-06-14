from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from product_agent.domain import PaperRecord, ResearchIdea
from product_agent.models import EvolutionEdge, PaperNode
from product_agent.repositories.sqlite_store import SQLiteWorkspaceRepository
from product_agent.research_agent.nodes.synthesizer import synthesizer_node
from product_agent.services.evidence_snapshot_service import EvidenceSnapshotService
from product_agent.services.idea_generation_service import IdeaGenerationOutput
from product_agent.services.report_generation_service import ReportGenerationOutput
from product_agent.services.summary_generation_service import SummaryGenerationOutput
from product_agent.services.workspace_mapper import workspace_from_agent_state
from product_agent.services.workspace_service import (
    WorkspaceService,
    _merge_workspace_graph_edges,
    _merge_workspace_taxonomy,
    _visible_workspace_graph_edges,
)


class _WorkspaceRepository:
    def __init__(self, workspace) -> None:
        self.workspace = workspace

    def get_by_task(self, task_id: str):
        return self.workspace if self.workspace.task_id == task_id else None


class EvidenceSnapshotTests(unittest.TestCase):
    def test_workspace_persistence_keeps_relevance_metadata(self) -> None:
        paper = PaperRecord(
            paper_id="paper-a",
            title="Relevant Paper",
            relevance_score=0.91,
            relevance_tier="direct",
            relevance_reasons=["tool_use:title:tool use"],
        )

        payload = SQLiteWorkspaceRepository._paper_to_dict(paper)

        self.assertEqual(payload["relevance_score"], 0.91)
        self.assertEqual(payload["relevance_tier"], "direct")
        self.assertEqual(
            payload["relevance_reasons"],
            ["tool_use:title:tool use"],
        )

    def test_conversation_graph_prefers_confirmed_relation_for_same_pair(self) -> None:
        weak = SimpleNamespace(
            graph_edges=[
                {
                    "source": "paper-a",
                    "target": "paper-b",
                    "relationship": "related",
                    "evidence_level": "inferred",
                    "confidence": 0.62,
                }
            ]
        )
        strong = SimpleNamespace(
            graph_edges=[
                {
                    "source": "paper-a",
                    "target": "paper-b",
                    "relationship": "citation",
                    "evidence_level": "confirmed",
                    "confidence": 1.0,
                }
            ]
        )

        merged = _merge_workspace_graph_edges([weak, strong])

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["relationship"], "citation")

    def test_workspace_graph_hides_weak_candidate_edges(self) -> None:
        visible = _visible_workspace_graph_edges(
            [
                {
                    "source": "paper-a",
                    "target": "paper-b",
                    "relationship": "related",
                    "evidence_level": "candidate",
                    "confidence": 0.39,
                },
                {
                    "source": "paper-a",
                    "target": "paper-c",
                    "relationship": "scope_extension",
                    "evidence_level": "inferred",
                    "confidence": 0.58,
                },
                {
                    "source": "paper-b",
                    "target": "paper-c",
                    "relationship": "citation",
                    "evidence_level": "confirmed",
                    "confidence": 1.0,
                },
            ]
        )

        self.assertEqual(
            {
                (edge["source"], edge["target"])
                for edge in visible
            },
            {
                ("paper-a", "paper-c"),
                ("paper-b", "paper-c"),
            },
        )

    def test_conversation_taxonomy_preserves_deduplicated_matched_paper_ids(self) -> None:
        first = SimpleNamespace(
            taxonomy={
                "branches": [
                    {
                        "branch_id": "benchmark-design",
                        "name": "Benchmark Design",
                        "paper_count": 2,
                        "matched_paper_ids": ["paper-a", "paper-b"],
                    }
                ],
                "coverage": {
                    "benchmark-design": {
                        "paper_count": 2,
                        "gap_count": 1,
                        "coverage_score": 0.75,
                        "evidence_tier": "moderate",
                        "matched_paper_ids": ["paper-a", "paper-b"],
                        "matched_gap_ids": ["gap-a"],
                    }
                },
            }
        )
        second = SimpleNamespace(
            taxonomy={
                "branches": [
                    {
                        "branch_id": "benchmark-design",
                        "name": "Benchmark Design",
                        "paper_count": 2,
                        "matched_paper_ids": ["paper-b", "paper-c"],
                    }
                ],
                "coverage": {
                    "benchmark-design": {
                        "paper_count": 2,
                        "gap_count": 1,
                        "coverage_score": 0.85,
                        "evidence_tier": "strong",
                        "matched_paper_ids": ["paper-b", "paper-c"],
                        "matched_gap_ids": ["gap-b"],
                    }
                },
            }
        )

        merged = _merge_workspace_taxonomy([first, second])
        branch = merged["branches"][0]
        coverage = merged["coverage"]["benchmark-design"]

        self.assertEqual(
            set(branch["matched_paper_ids"]),
            {"paper-a", "paper-b", "paper-c"},
        )
        self.assertEqual(branch["paper_count"], 3)
        self.assertEqual(
            set(coverage["matched_paper_ids"]),
            {"paper-a", "paper-b", "paper-c"},
        )
        self.assertEqual(set(coverage["matched_gap_ids"]), {"gap-a", "gap-b"})
        self.assertEqual(coverage["paper_count"], 3)
        self.assertEqual(coverage["gap_count"], 2)
        self.assertEqual(coverage["evidence_tier"], "strong")

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
                    relevance_tier="direct",
                    relevance_score=0.9,
                ),
                "paper-b": PaperNode(
                    paper_id="paper-b",
                    title="Fallback Survey",
                    abstract="Fallback evidence.",
                    source="seed",
                    publish_date="2024",
                    expert_taxonomy_branches=["Evaluation"],
                    relevance_tier="candidate",
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
        self.assertEqual(first["stats"]["direct_paper_count"], 1)
        self.assertEqual(
            first["conclusion_contract"]["claimable_paper_ids"],
            ["paper-a"],
        )
        self.assertTrue(
            first["conclusion_contract"]["recommendations_allowed"]
        )
        branch = first["taxonomy"]["branches"][0]
        self.assertEqual(branch["evidence_status"], "grounded")
        self.assertEqual(branch["direct_paper_ids"], ["paper-a"])
        self.assertEqual(first["stats"]["evidence_level_counts"]["confirmed"], 1)
        self.assertEqual(first["stats"]["evidence_backed_gap_count"], 1)

    def test_adjacent_only_taxonomy_branch_is_exploratory(self) -> None:
        state = self._state()
        state["paper_nodes"] = {
            "paper-adjacent": PaperNode(
                paper_id="paper-adjacent",
                title="Early Fusion for Multimodal Image Segmentation",
                abstract="A traditional RGB-T segmentation study.",
                source="arxiv",
                expert_taxonomy_branches=["Fusion Strategies"],
                relevance_tier="adjacent",
                relevance_score=0.7,
            )
        }
        state["expert_taxonomy"] = {
            "taxonomy": {
                "Fusion Strategies": {
                    "description": "Multimodal fusion methods",
                    "required_concepts": ["early fusion"],
                }
            }
        }

        snapshot = EvidenceSnapshotService().build(
            topic=state["topic"],
            papers=state["paper_nodes"],
            taxonomy=state["expert_taxonomy"],
            edges=[],
            gaps=[],
            retrieval_plan=state["retrieval_plan"],
            retrieval_outcome=state["retrieval_outcome"],
            alignment_score=state["alignment_score"],
            audit_reports=[],
        )

        branch = snapshot["taxonomy"]["branches"][0]
        self.assertEqual(branch["evidence_status"], "exploratory")
        self.assertEqual(branch["direct_paper_ids"], [])
        self.assertEqual(branch["adjacent_paper_ids"], ["paper-adjacent"])
        self.assertFalse(
            snapshot["conclusion_contract"]["recommendations_allowed"]
        )

    def test_snapshot_uses_grounded_taxonomy_matched_paper_ids(self) -> None:
        state = self._state()
        state["paper_nodes"]["paper-a"].expert_taxonomy_branches = []
        state["expert_taxonomy"] = {
            "branches": [
                {
                    "branch_id": "evaluation",
                    "name": "Evaluation",
                    "description": "Evaluation methods",
                    "required_concepts": ["benchmark"],
                    "matched_paper_ids": ["paper-a"],
                    "matched_gap_ids": ["gap-1"],
                }
            ],
            "coverage": {
                "evaluation": {
                    "matched_paper_ids": ["paper-a"],
                    "matched_gap_ids": ["gap-1"],
                }
            },
        }

        snapshot = EvidenceSnapshotService().build(
            topic=state["topic"],
            papers=state["paper_nodes"],
            taxonomy=state["expert_taxonomy"],
            edges=[],
            gaps=state["detected_gaps"],
            retrieval_plan=state["retrieval_plan"],
            retrieval_outcome=state["retrieval_outcome"],
            alignment_score=state["alignment_score"],
            audit_reports=[],
        )

        branch = next(
            item
            for item in snapshot["taxonomy"]["branches"]
            if item["name"] == "Evaluation"
        )
        self.assertEqual(branch["direct_paper_ids"], ["paper-a"])
        self.assertEqual(branch["matched_gap_ids"], ["gap-1"])

    @patch("product_agent.research_agent.nodes.synthesizer.SummaryGenerationService.run")
    @patch("product_agent.research_agent.nodes.synthesizer.ReportGenerationService.run")
    @patch("product_agent.research_agent.nodes.synthesizer.IdeaGenerationService.run")
    def test_ungrounded_idea_is_rejected_after_generation(
        self,
        idea_run,
        report_run,
        summary_run,
    ) -> None:
        idea_run.return_value = IdeaGenerationOutput(
            [
                ResearchIdea(
                    idea_id="idea-weak",
                    title="Unsupported recommendation",
                    motivation="Adjacent observation",
                    approach="Build a benchmark",
                    feasibility="Unknown",
                    contribution="Unknown",
                    related_papers=["paper-b"],
                    derived_from_gaps=["gap-1"],
                    confidence=0.8,
                    tags=["benchmark"],
                    raw_text="",
                )
            ],
            "test",
        )
        report_run.return_value = ReportGenerationOutput(
            "report",
            "test",
            "report-1",
        )
        summary_run.return_value = SummaryGenerationOutput(
            {"counts": {}},
            "test",
        )

        updated = synthesizer_node(self._state())

        self.assertEqual(updated["generated_ideas"], [])
        self.assertFalse(
            report_run.call_args.args[0].allow_research_ideas
        )
        self.assertFalse(
            summary_run.call_args.args[0].allow_recommendation
        )
        self.assertIn(
            "could not be bound",
            updated["degraded_reason"],
        )

    @patch("product_agent.research_agent.nodes.synthesizer.SummaryGenerationService.run")
    @patch("product_agent.research_agent.nodes.synthesizer.ReportGenerationService.run")
    @patch("product_agent.research_agent.nodes.synthesizer.IdeaGenerationService.run")
    def test_unsupported_taxonomy_branch_downgrades_idea_to_exploratory(
        self,
        idea_run,
        report_run,
        summary_run,
    ) -> None:
        state = self._state()
        state["expert_taxonomy"] = {
            "branches": [
                {
                    "branch_id": "missing-modality",
                    "name": "Robustness to Missing Modalities",
                    "description": "Robust fusion when modalities are absent.",
                    "required_concepts": ["modality dropout"],
                    "matched_paper_ids": [],
                    "matched_gap_ids": ["gap-missing"],
                },
                {
                    "branch_id": "alignment",
                    "name": "Cross-Modal Alignment",
                    "description": "Alignment methods.",
                    "required_concepts": ["mutual information"],
                    "matched_paper_ids": ["paper-a"],
                    "matched_gap_ids": [],
                },
            ],
            "coverage": {
                "missing-modality": {
                    "matched_paper_ids": [],
                    "matched_gap_ids": ["gap-missing"],
                },
                "alignment": {
                    "matched_paper_ids": ["paper-a"],
                    "matched_gap_ids": [],
                },
            },
        }
        state["detected_gaps"] = [
            {
                "id": "gap-missing",
                "description": "Missing taxonomy branch: Robustness to Missing Modalities",
                "severity": "high",
                "evidence": [],
            }
        ]
        idea_run.return_value = IdeaGenerationOutput(
            [
                ResearchIdea(
                    idea_id="idea-missing",
                    title="Improve missing-modality robustness",
                    motivation="Handle absent modalities.",
                    approach="Add modality dropout.",
                    feasibility="Existing model.",
                    contribution="Robust fusion.",
                    related_papers=["paper-a"],
                    derived_from_gaps=["gap-missing"],
                    confidence=0.9,
                    tags=["robustness"],
                    raw_text="",
                )
            ],
            "test",
        )
        report_run.return_value = ReportGenerationOutput(
            "report",
            "test",
            "report-1",
        )
        summary_run.return_value = SummaryGenerationOutput(
            {"counts": {}},
            "test",
        )

        updated = synthesizer_node(state)

        self.assertEqual(len(updated["generated_ideas"]), 1)
        idea = updated["generated_ideas"][0]
        self.assertTrue(idea.title.startswith("探索性方向："))
        self.assertLessEqual(idea.confidence, 0.45)
        self.assertIn("缺少分支级直接论文证据", idea.motivation)
        self.assertTrue(report_run.call_args.args[0].allow_research_ideas)
        self.assertFalse(summary_run.call_args.args[0].allow_recommendation)
        self.assertEqual(summary_run.call_args.args[0].ideas, [])
        self.assertEqual(
            updated["final_report_summary"]["idea_admission"]["exploratory_count"],
            1,
        )

    @patch("product_agent.research_agent.nodes.synthesizer.SummaryGenerationService.run")
    @patch("product_agent.research_agent.nodes.synthesizer.ReportGenerationService.run")
    @patch("product_agent.research_agent.nodes.synthesizer.IdeaGenerationService.run")
    def test_adjacent_only_evidence_skips_idea_generation(
        self,
        idea_run,
        report_run,
        summary_run,
    ) -> None:
        state = self._state()
        state["paper_nodes"]["paper-a"].relevance_tier = "adjacent"
        state["retrieval_outcome"] = {
            "real_paper_count": 1,
            "direct_paper_count": 0,
        }
        report_run.return_value = ReportGenerationOutput(
            "report",
            "test",
            "report-1",
        )
        summary_run.return_value = SummaryGenerationOutput(
            {"counts": {}},
            "test",
        )

        updated = synthesizer_node(state)

        idea_run.assert_not_called()
        self.assertEqual(updated["generated_ideas"], [])
        self.assertFalse(
            report_run.call_args.args[0].allow_research_ideas
        )
        self.assertFalse(
            summary_run.call_args.args[0].allow_recommendation
        )

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
            [
                paper
                for paper in updated["evidence_snapshot"]["papers"]
                if paper["relevance_tier"] == "direct"
            ],
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

    def test_required_facet_adjacent_only_overrides_global_direct_relevance(
        self,
    ) -> None:
        state = self._state()
        state["expert_taxonomy"] = {
            "branches": [
                {
                    "branch_id": "missing-modality",
                    "name": "Robustness to Missing Modalities",
                    "description": "Robustness when one modality is absent.",
                    "required_concepts": ["missing modality robustness"],
                    "matched_paper_ids": ["paper-a"],
                }
            ]
        }
        state["retrieval_outcome"] = {
            "facet_evidence_coverage": {
                "facets": [
                    {
                        "label": "missing modality robustness",
                        "required": True,
                        "evidence_level": "adjacent_only",
                        "search_terms": ["missing modality robustness"],
                        "matched_papers": [
                            {
                                "paper_id": "paper-a",
                                "match_type": "adjacent",
                            }
                        ],
                    }
                ]
            }
        }

        snapshot = EvidenceSnapshotService().build(
            topic=state["topic"],
            papers=state["paper_nodes"],
            taxonomy=state["expert_taxonomy"],
            edges=[],
            gaps=[],
            retrieval_plan=state["retrieval_plan"],
            retrieval_outcome=state["retrieval_outcome"],
            alignment_score=state["alignment_score"],
            audit_reports=[],
        )

        branch = next(
            item
            for item in snapshot["taxonomy"]["branches"]
            if item["name"] == "Robustness to Missing Modalities"
        )
        self.assertEqual(branch["direct_paper_ids"], ["paper-a"])
        self.assertEqual(branch["claimable_paper_ids"], [])
        self.assertEqual(branch["evidence_status"], "exploratory")
        self.assertEqual(
            branch["required_facet_evidence_level"],
            "adjacent_only",
        )

    @patch("product_agent.research_agent.nodes.synthesizer.SummaryGenerationService.run")
    @patch("product_agent.research_agent.nodes.synthesizer.ReportGenerationService.run")
    @patch("product_agent.research_agent.nodes.synthesizer.IdeaGenerationService.run")
    def test_adjacent_only_required_facet_downgrades_linked_idea(
        self,
        idea_run,
        report_run,
        summary_run,
    ) -> None:
        state = self._state()
        state["expert_taxonomy"] = {
            "branches": [
                {
                    "branch_id": "missing-modality",
                    "name": "Robustness to Missing Modalities",
                    "description": "Robustness when modalities are absent.",
                    "required_concepts": ["missing modality robustness"],
                    "matched_paper_ids": ["paper-a"],
                }
            ]
        }
        state["detected_gaps"] = [
            {
                "id": "gap-missing",
                "description": (
                    "Direction Robustness to Missing Modalities lacks "
                    "direct evidence."
                ),
                "severity": "warning",
                "evidence": ["paper-a"],
            }
        ]
        state["retrieval_outcome"] = {
            "real_paper_count": 1,
            "direct_paper_count": 1,
            "facet_evidence_coverage": {
                "facets": [
                    {
                        "label": "missing modality robustness",
                        "required": True,
                        "evidence_level": "adjacent_only",
                        "search_terms": ["missing modality robustness"],
                        "matched_papers": [
                            {
                                "paper_id": "paper-a",
                                "match_type": "adjacent",
                            }
                        ],
                    }
                ]
            },
        }
        idea_run.return_value = IdeaGenerationOutput(
            [
                ResearchIdea(
                    idea_id="idea-missing",
                    title="Improve missing-modality robustness",
                    motivation="Handle absent modalities.",
                    approach="Add modality dropout.",
                    feasibility="Existing model.",
                    contribution="Robust fusion.",
                    related_papers=["paper-a"],
                    derived_from_gaps=["gap-missing"],
                    confidence=0.9,
                    tags=["robustness"],
                    raw_text="",
                )
            ],
            "test",
        )
        report_run.return_value = ReportGenerationOutput(
            "report",
            "test",
            "report-1",
        )
        summary_run.return_value = SummaryGenerationOutput(
            {"counts": {}},
            "test",
        )

        updated = synthesizer_node(state)

        self.assertEqual(len(updated["generated_ideas"]), 1)
        self.assertTrue(
            updated["generated_ideas"][0].title.startswith("探索性方向：")
        )
        self.assertEqual(
            updated["final_report_summary"]["idea_admission"][
                "exploratory_count"
            ],
            1,
        )
        self.assertEqual(summary_run.call_args.args[0].ideas, [])


if __name__ == "__main__":
    unittest.main()
