from __future__ import annotations

import unittest

from product_agent.models import EvolutionEdge, PaperNode
from product_agent.research_agent.nodes.evolution import evolution_node
from product_agent.services.graph_audit_service import GraphAuditService
from product_agent.services.relationship_evidence_service import RelationshipEvidenceService
from product_agent.services.workspace_mapper import _map_graph_edge


def paper(
    paper_id: str,
    *,
    title: str,
    year: str,
    keywords: list[str],
    category: str = "",
    references: list[str] | None = None,
    abstract: str = "",
) -> PaperNode:
    return PaperNode(
        paper_id=paper_id,
        title=title,
        publish_date=year,
        keywords=keywords,
        taxonomy_category=category,
        references=references or [],
        abstract=abstract,
    )


class EvolutionGraphTests(unittest.TestCase):
    def test_explicit_reference_is_a_confirmed_citation(self) -> None:
        predecessor = paper(
            "paper-a",
            title="Early Agent Benchmark",
            year="2023",
            keywords=["agent", "benchmark"],
        )
        successor = paper(
            "paper-b",
            title="Later Unrelated Title",
            year="2025",
            keywords=["memory"],
            references=["paper-a"],
        )

        result = evolution_node(
            {
                "topic": "AI agents",
                "mode": "full",
                "paper_nodes": {
                    predecessor.paper_id: predecessor,
                    successor.paper_id: successor,
                },
            }
        )

        edge = result["evolution_graph"][0]
        self.assertEqual((edge.source, edge.target), ("paper-a", "paper-b"))
        self.assertEqual(edge.relationship, "citation")
        self.assertEqual(edge.provenance, "explicit_reference")
        self.assertEqual(edge.evidence_level, "confirmed")
        self.assertEqual(edge.confidence, 1.0)

    def test_similarity_never_claims_improvement_or_extension(self) -> None:
        earlier = paper(
            "paper-a",
            title="Agent Tool Use Benchmark",
            year="2023",
            keywords=["agent", "tool", "benchmark", "evaluation"],
            category="Agent Evaluation",
        )
        later = paper(
            "paper-b",
            title="Agent Tool Use Evaluation",
            year="2025",
            keywords=["agent", "tool", "benchmark", "evaluation"],
            category="Agent Evaluation",
        )

        result = evolution_node(
            {
                "topic": "AI agent tool use evaluation",
                "mode": "full",
                "paper_nodes": {
                    earlier.paper_id: earlier,
                    later.paper_id: later,
                },
            }
        )

        edge = result["evolution_graph"][0]
        self.assertEqual(edge.relationship, "related")
        self.assertEqual(edge.provenance, "taxonomy_similarity")
        self.assertEqual(edge.evidence_level, "inferred")
        self.assertLess(edge.confidence, 0.7)

    def test_balanced_fallback_is_marked_as_candidate(self) -> None:
        earlier = paper(
            "paper-a",
            title="Agent Planning",
            year="2023",
            keywords=["planning"],
        )
        later = paper(
            "paper-b",
            title="Agent Memory",
            year="2025",
            keywords=["memory"],
        )

        result = evolution_node(
            {
                "topic": "AI agents",
                "mode": "balanced",
                "paper_nodes": {
                    earlier.paper_id: earlier,
                    later.paper_id: later,
                },
            }
        )

        edge = result["evolution_graph"][0]
        self.assertEqual(edge.relationship, "related")
        self.assertEqual(edge.provenance, "balanced_fallback")
        self.assertEqual(edge.evidence_level, "candidate")
        self.assertLess(edge.confidence, 0.4)

    def test_similarity_graph_is_sparse_instead_of_all_to_all(self) -> None:
        papers = {
            f"paper-{index}": paper(
                f"paper-{index}",
                title=f"Agent Tool Benchmark {index}",
                year=str(2020 + index),
                keywords=["agent", "tool", "benchmark"],
                category="Agent Evaluation",
            )
            for index in range(8)
        }

        result = evolution_node(
            {
                "topic": "agent tool evaluation",
                "mode": "balanced",
                "paper_nodes": papers,
            }
        )

        self.assertLessEqual(len(result["evolution_graph"]), len(papers))

    def test_failure_analysis_to_recovery_method_is_marked_as_addresses(self) -> None:
        analysis = paper(
            "paper-a",
            title="Failure Analysis for Tool-Using Agents",
            year="2025",
            keywords=["agent", "tool use", "failure"],
            abstract=(
                "We investigate how LLM agents fail during tool use and "
                "characterize recurrent failure modes."
            ),
        )
        response = paper(
            "paper-b",
            title="Recovery Diagnostics for Tool-Using Agents",
            year="2026",
            keywords=["agent", "tool use", "recovery"],
            abstract=(
                "We propose structured diagnostics and a recovery policy to "
                "improve reliability after tool calling failures."
            ),
        )

        result = evolution_node(
            {
                "topic": "agent tool use failure recovery",
                "mode": "balanced",
                "paper_nodes": {
                    analysis.paper_id: analysis,
                    response.paper_id: response,
                },
            }
        )

        edge = result["evolution_graph"][0]
        self.assertEqual(edge.relationship, "addresses")
        self.assertEqual(edge.provenance, "landscape_profile")
        self.assertEqual(edge.evidence_level, "inferred")

    def test_later_benchmark_with_new_dimension_is_scope_extension(self) -> None:
        earlier = paper(
            "paper-a",
            title="Tool Agent Benchmark",
            year="2024",
            keywords=["agent", "tool use", "benchmark"],
            abstract="We introduce a benchmark for evaluating tool-using LLM agents.",
        )
        later = paper(
            "paper-b",
            title="Trajectory Tool Agent Benchmark",
            year="2025",
            keywords=["agent", "tool use", "benchmark", "trajectory"],
            abstract=(
                "We introduce a trajectory-level benchmark for evaluating tool-using "
                "LLM agents with execution traces."
            ),
        )

        result = evolution_node(
            {
                "topic": "agent tool use evaluation",
                "mode": "balanced",
                "paper_nodes": {
                    earlier.paper_id: earlier,
                    later.paper_id: later,
                },
            }
        )

        edge = result["evolution_graph"][0]
        self.assertEqual(edge.relationship, "scope_extension")
        self.assertIn("target_added_dimensions", edge.evidence_snippets[-1])

    def test_evidence_contract_survives_workspace_mapping(self) -> None:
        result = evolution_node(
            {
                "topic": "AI agents",
                "mode": "full",
                "paper_nodes": {
                    "paper-a": paper(
                        "paper-a",
                        title="Early Work",
                        year="2023",
                        keywords=["agent"],
                    ),
                    "paper-b": paper(
                        "paper-b",
                        title="Later Work",
                        year="2025",
                        keywords=["memory"],
                        references=["paper-a"],
                    ),
                },
            }
        )

        mapped = _map_graph_edge(result["evolution_graph"][0], set())
        self.assertEqual(mapped["relationship"], "citation")
        self.assertEqual(mapped["provenance"], "explicit_reference")
        self.assertEqual(mapped["evidence_level"], "confirmed")
        self.assertEqual(mapped["confidence"], 1.0)
        self.assertTrue(mapped["evidence_snippets"])

    def test_explicit_citation_is_not_rejected_for_low_keyword_overlap(self) -> None:
        predecessor = paper(
            "paper-a",
            title="Symbolic Planning",
            year="2023",
            keywords=["planning"],
        )
        successor = paper(
            "paper-b",
            title="Neural Memory",
            year="2025",
            keywords=["memory"],
            references=["paper-a"],
        )
        state = evolution_node(
            {
                "topic": "AI agents",
                "mode": "full",
                "paper_nodes": {
                    predecessor.paper_id: predecessor,
                    successor.paper_id: successor,
                },
            }
        )

        audit = GraphAuditService().audit(
            state["paper_nodes"],
            state["evolution_graph"],
        )
        self.assertEqual(audit.gaps, [])
        self.assertEqual(audit.score, 1.0)

    def test_explicit_citation_upgrades_to_supported_improvement(self) -> None:
        predecessor = paper(
            "paper-a",
            title="Toolformer",
            year="2023",
            keywords=["tool use"],
        )
        successor = paper(
            "paper-b",
            title="Reliable Tool Learning",
            year="2025",
            keywords=["tool use"],
            references=["paper-a"],
            abstract=(
                "Building on Toolformer, our method improves benchmark accuracy "
                "and achieves better performance across three datasets."
            ),
        )

        state = evolution_node(
            {
                "topic": "agent tool use",
                "mode": "full",
                "paper_nodes": {
                    predecessor.paper_id: predecessor,
                    successor.paper_id: successor,
                },
            }
        )

        edge = state["evolution_graph"][0]
        self.assertEqual(edge.relationship, "improvement")
        self.assertEqual(edge.provenance, "explicit_reference+abstract_claim")
        self.assertEqual(edge.evidence_level, "confirmed")
        self.assertIn("Toolformer", edge.evidence_snippets[0])

    def test_similarity_upgrades_only_with_direct_comparison_claim(self) -> None:
        predecessor = paper(
            "paper-a",
            title="AgentBench",
            year="2023",
            keywords=["agent", "benchmark"],
            category="Agent Evaluation",
        )
        successor = paper(
            "paper-b",
            title="A New Agent Evaluation",
            year="2025",
            keywords=["agent", "benchmark"],
            category="Agent Evaluation",
            abstract="We compare our evaluation protocol against AgentBench on the same tasks.",
        )

        state = evolution_node(
            {
                "topic": "agent evaluation",
                "mode": "full",
                "paper_nodes": {
                    predecessor.paper_id: predecessor,
                    successor.paper_id: successor,
                },
            }
        )

        edge = state["evolution_graph"][0]
        self.assertEqual(edge.relationship, "comparison")
        self.assertEqual(edge.provenance, "abstract_claim")
        self.assertEqual(edge.evidence_level, "supported")

    def test_supported_extension_does_not_require_performance_results(self) -> None:
        predecessor = paper(
            "paper-a",
            title="AgentBench",
            year="2023",
            keywords=["agent", "benchmark"],
        )
        successor = paper(
            "paper-b",
            title="AgentBench for Multimodal Tasks",
            year="2025",
            keywords=["agent", "benchmark"],
            references=["paper-a"],
            abstract="Building on AgentBench, we extend the task suite to multimodal agents.",
        )
        state = evolution_node(
            {
                "topic": "agent evaluation",
                "mode": "full",
                "paper_nodes": {
                    predecessor.paper_id: predecessor,
                    successor.paper_id: successor,
                },
            }
        )

        edge = state["evolution_graph"][0]
        audit = GraphAuditService().audit(state["paper_nodes"], [edge])
        self.assertEqual(edge.relationship, "extension")
        self.assertEqual(audit.gaps, [])
        self.assertEqual(audit.score, 1.0)

    def test_unsupported_legacy_strong_relation_is_downgraded(self) -> None:
        predecessor = paper(
            "paper-a",
            title="Agent Planning",
            year="2023",
            keywords=["agent", "planning"],
        )
        successor = paper(
            "paper-b",
            title="Agent Memory",
            year="2025",
            keywords=["agent", "memory"],
            abstract="We improve memory performance on a new benchmark.",
        )
        legacy_edge = EvolutionEdge(
            source="paper-a",
            target="paper-b",
            relationship="improves",
            provenance="keyword_similarity",
            confidence=0.8,
            weight=0.8,
        )

        verified = RelationshipEvidenceService().verify(
            {"paper-a": predecessor, "paper-b": successor},
            [legacy_edge],
        )[0]

        self.assertEqual(verified.relationship, "related")
        self.assertEqual(verified.evidence_level, "inferred")
        self.assertLessEqual(verified.confidence, 0.49)
        self.assertIn("Downgraded from improves", verified.evidence_snippets[-1])


if __name__ == "__main__":
    unittest.main()
