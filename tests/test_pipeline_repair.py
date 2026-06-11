from __future__ import annotations

import unittest
from unittest.mock import patch

from product_agent.models import PaperNode
from product_agent.research_agent.nodes.corrector import corrector_node
from product_agent.research_agent.nodes.evolution import evolution_node
from product_agent.research_agent.nodes.searcher import (
    _count_novel_papers,
    _mark_round_novelty,
)
from product_agent.research_agent.nodes.taxonomy import taxonomy_node
from product_agent.research_agent.runtime import execute_agent_loop


class PipelineRepairTests(unittest.TestCase):
    def test_fallback_papers_are_not_reported_as_new_evidence(self) -> None:
        papers = {
            "fallback-a": PaperNode(
                paper_id="fallback-a",
                source="fallback",
            ),
            "real-a": PaperNode(
                paper_id="real-a",
                source="arxiv",
            ),
        }

        _mark_round_novelty(papers, {"old-paper"})

        self.assertFalse(papers["fallback-a"].is_new_this_round)
        self.assertTrue(papers["real-a"].is_new_this_round)
        self.assertEqual(_count_novel_papers(papers, {"old-paper"}), 1)

    def test_corrector_promotes_gap_query_into_strict_retrieval_plan(self) -> None:
        state = {
            "topic": "AI agents",
            "mode": "full",
            "alignment_score": 0.3,
            "retry_count": 0,
            "detected_gaps": [
                {"description": "Missing benchmark reliability evidence"}
            ],
            "search_queries": ["AI agents"],
            "retrieval_plan": {
                "topic": "AI agents",
                "strict_queries": ["AI agents"],
                "broad_queries": ["AI agents survey"],
                "filters": {},
                "rerank_signals": [],
                "strategy_note": "",
            },
        }

        updated = corrector_node(state)

        strict_queries = updated["retrieval_plan"]["strict_queries"]
        self.assertIn("benchmark", strict_queries[0].lower())
        self.assertEqual(updated["search_queries"][0], strict_queries[0])
        self.assertIn("gap_driven_retry", updated["retrieval_plan"]["strategy_note"])
        self.assertTrue(updated["retry_requested"])
        self.assertTrue(updated["needs_taxonomy_refresh"])

    def test_corrector_allows_another_round_when_previous_repair_added_evidence(self) -> None:
        state = {
            "topic": "AI agents",
            "mode": "full",
            "alignment_score": 0.35,
            "retry_count": 1,
            "max_repair_rounds": 2,
            "detected_gaps": [{"description": "Missing reliability benchmark"}],
            "paper_nodes": {"paper-a": PaperNode(paper_id="paper-a")},
            "retrieval_outcome": {"search_added_paper_count": 1},
            "repair_baseline": {
                "retry_round": 1,
                "alignment_score": 0.3,
                "gap_count": 1,
                "paper_ids": [],
            },
            "retrieval_plan": {"strict_queries": ["AI agents"]},
            "search_queries": ["AI agents"],
        }

        updated = corrector_node(state)

        self.assertTrue(updated["retry_requested"])
        self.assertEqual(updated["retry_count"], 2)
        self.assertTrue(updated["repair_history"][0]["has_gain"])

    def test_corrector_stops_when_repair_has_no_gain(self) -> None:
        state = {
            "topic": "AI agents",
            "mode": "full",
            "alignment_score": 0.3,
            "retry_count": 1,
            "max_repair_rounds": 2,
            "detected_gaps": [{"description": "Missing reliability benchmark"}],
            "retrieval_outcome": {"search_added_paper_count": 0},
            "repair_baseline": {
                "retry_round": 1,
                "alignment_score": 0.3,
                "gap_count": 1,
                "paper_ids": ["paper-a"],
            },
        }

        updated = corrector_node(state)

        self.assertFalse(updated["retry_requested"])
        self.assertEqual(updated["repair_stop_reason"], "no_gain")
        self.assertTrue(updated["degraded_reason"])
        self.assertFalse(updated["repair_history"][0]["has_gain"])

    def test_corrector_stops_when_repair_budget_is_exhausted(self) -> None:
        state = {
            "topic": "AI agents",
            "mode": "full",
            "alignment_score": 0.4,
            "retry_count": 2,
            "max_repair_rounds": 2,
            "detected_gaps": [{"description": "Missing reliability benchmark"}],
            "repair_baseline": {},
        }

        updated = corrector_node(state)

        self.assertEqual(updated["repair_stop_reason"], "budget_exhausted")
        self.assertEqual(updated["retry_count"], 2)
        self.assertFalse(updated["retry_requested"])

    @patch("product_agent.research_agent.nodes.taxonomy.build_taxonomy")
    def test_taxonomy_refresh_rebuilds_existing_taxonomy(self, build_taxonomy) -> None:
        build_taxonomy.return_value = {
            "taxonomy": {
                "New Branch": {
                    "description": "new evidence",
                    "required_concepts": ["benchmark"],
                }
            }
        }
        state = {
            "topic": "AI agents",
            "paper_nodes": {
                "paper-a": PaperNode(
                    paper_id="paper-a",
                    title="Agent Benchmark",
                    abstract="A benchmark for agent evaluation.",
                    keywords=["benchmark"],
                )
            },
            "review_texts": [],
            "expert_taxonomy": {
                "taxonomy": {
                    "Old Branch": {
                        "description": "stale",
                        "required_concepts": [],
                    }
                }
            },
            "needs_taxonomy_refresh": True,
        }

        updated = taxonomy_node(state)

        build_taxonomy.assert_called_once()
        self.assertIn("New Branch", updated["expert_taxonomy"]["taxonomy"])
        self.assertIn(
            "New Branch",
            updated["paper_nodes"]["paper-a"].expert_taxonomy_branches,
        )

    def test_evolution_uses_grounded_expert_taxonomy_before_source_category(self) -> None:
        earlier = PaperNode(
            paper_id="paper-a",
            title="Repository Agent Evaluation",
            abstract="Benchmark evaluation for repository agents.",
            publish_date="2023",
            taxonomy_category="cs.SE",
            expert_taxonomy_branches=["Agent Evaluation"],
        )
        later = PaperNode(
            paper_id="paper-b",
            title="Interactive Agent Assessment",
            abstract="Evaluation protocol for interactive agents.",
            publish_date="2025",
            taxonomy_category="cs.HC",
            expert_taxonomy_branches=["Agent Evaluation"],
        )

        result = evolution_node(
            {
                "topic": "agent evaluation",
                "mode": "full",
                "paper_nodes": {
                    earlier.paper_id: earlier,
                    later.paper_id: later,
                },
            }
        )

        self.assertEqual(len(result["evolution_graph"]), 1)
        edge = result["evolution_graph"][0]
        self.assertEqual(edge.relationship, "related")
        self.assertEqual(edge.provenance, "taxonomy_similarity")
        self.assertTrue(
            any(
                "Agent Evaluation" in snippet
                for snippet in edge.evidence_snippets
            )
        )

    def test_controller_completes_one_repair_loop_within_step_budget(self) -> None:
        calls: list[str] = []
        audit_runs = 0

        def planner(state):
            calls.append("planner")
            state["search_queries"] = ["AI agents"]
            state["retrieval_plan"] = {
                "topic": "AI agents",
                "strict_queries": ["AI agents"],
                "broad_queries": [],
                "filters": {},
                "rerank_signals": [],
            }
            return state

        def searcher(state):
            calls.append("searcher")
            state["paper_nodes"] = {
                "paper-a": PaperNode(
                    paper_id="paper-a",
                    title="Agent Benchmark",
                    abstract="Benchmark evaluation for agents.",
                    keywords=["benchmark"],
                )
            }
            return state

        def taxonomy(state):
            calls.append("taxonomy")
            state["expert_taxonomy"] = {
                "taxonomy": {
                    "Agent Evaluation": {
                        "description": "benchmark evaluation",
                        "required_concepts": ["benchmark"],
                    }
                }
            }
            return state

        def evolution(state):
            calls.append("evolution")
            state["evolution_graph"] = []
            return state

        def auditor(state):
            nonlocal audit_runs
            calls.append("auditor")
            audit_runs += 1
            if audit_runs == 1:
                state["alignment_score"] = 0.2
                state["detected_gaps"] = [
                    {"description": "Missing benchmark reliability evidence"}
                ]
            else:
                state["alignment_score"] = 0.9
                state["detected_gaps"] = []
            return state

        def synthesizer(state):
            calls.append("synthesizer")
            state["final_report"] = "complete"
            return state

        initial_state = {
            "topic": "AI agents",
            "mode": "full",
            "search_queries": [],
            "paper_nodes": {},
            "expert_taxonomy": {},
            "evolution_graph": [],
            "alignment_score": 0.0,
            "detected_gaps": [],
            "retry_count": 0,
            "retry_requested": False,
            "correction_checked": False,
            "needs_taxonomy_refresh": False,
            "needs_graph_refresh": False,
            "needs_audit_refresh": False,
            "taxonomy_built": False,
            "graph_built": False,
            "audit_completed": False,
            "synthesis_completed": False,
            "logs": [],
            "decisions": [],
            "thought_trace": [],
            "audit_events": [],
        }
        action_map = {
            "planner": ("Planner", "", planner),
            "searcher": ("Searcher", "", searcher),
            "taxonomy": ("Taxonomy", "", taxonomy),
            "evolution": ("Evolution", "", evolution),
            "auditor": ("Auditor", "", auditor),
            "corrector": ("Corrector", "", corrector_node),
            "synthesizer": ("Synthesizer", "", synthesizer),
        }

        result = execute_agent_loop(
            state=initial_state,
            action_map=action_map,
            show_progress=False,
            max_controller_steps=12,
        )

        self.assertEqual(calls.count("searcher"), 2)
        self.assertEqual(calls.count("taxonomy"), 2)
        self.assertEqual(calls.count("evolution"), 2)
        self.assertEqual(calls.count("auditor"), 2)
        self.assertEqual(calls[-1], "synthesizer")
        self.assertEqual(result["run_status"], "completed")
        self.assertEqual(result["final_report"], "complete")

    def test_controller_reports_step_limit_instead_of_false_completion(self) -> None:
        def planner(state):
            state["search_queries"] = ["AI agents"]
            return state

        result = execute_agent_loop(
            state={
                "topic": "AI agents",
                "search_queries": [],
                "paper_nodes": {},
                "logs": [],
                "decisions": [],
                "thought_trace": [],
                "synthesis_completed": False,
            },
            action_map={"planner": ("Planner", "", planner)},
            show_progress=False,
            max_controller_steps=1,
        )

        self.assertEqual(result["run_status"], "step_limit_reached")
        self.assertEqual(
            result["termination_reason"],
            "controller_step_limit_reached",
        )

    def test_controller_synthesizes_degraded_result_after_no_gain(self) -> None:
        search_runs = 0

        def planner(state):
            state["search_queries"] = ["AI agents"]
            state["retrieval_plan"] = {"strict_queries": ["AI agents"]}
            return state

        def searcher(state):
            nonlocal search_runs
            search_runs += 1
            state["paper_nodes"] = {"paper-a": PaperNode(paper_id="paper-a")}
            state["retrieval_outcome"] = {
                "search_added_paper_count": 1 if search_runs == 1 else 0
            }
            return state

        def taxonomy(state):
            state["expert_taxonomy"] = {"taxonomy": {}}
            return state

        def evolution(state):
            state["evolution_graph"] = []
            return state

        def auditor(state):
            state["alignment_score"] = 0.2
            state["detected_gaps"] = [{"description": "Missing benchmark evidence"}]
            return state

        def synthesizer(state):
            state["final_report"] = "limited"
            return state

        result = execute_agent_loop(
            state={
                "topic": "AI agents",
                "mode": "full",
                "max_repair_rounds": 2,
                "search_queries": [],
                "paper_nodes": {},
                "retry_count": 0,
                "retry_requested": False,
                "correction_checked": False,
                "taxonomy_built": False,
                "graph_built": False,
                "audit_completed": False,
                "synthesis_completed": False,
                "logs": [],
                "decisions": [],
                "thought_trace": [],
                "audit_events": [],
            },
            action_map={
                "planner": ("Planner", "", planner),
                "searcher": ("Searcher", "", searcher),
                "taxonomy": ("Taxonomy", "", taxonomy),
                "evolution": ("Evolution", "", evolution),
                "auditor": ("Auditor", "", auditor),
                "corrector": ("Corrector", "", corrector_node),
                "synthesizer": ("Synthesizer", "", synthesizer),
            },
            show_progress=False,
            max_controller_steps=17,
        )

        self.assertEqual(search_runs, 2)
        self.assertEqual(result["run_status"], "degraded")
        self.assertEqual(result["termination_reason"], "no_gain")
        self.assertEqual(result["final_report"], "limited")


if __name__ == "__main__":
    unittest.main()
