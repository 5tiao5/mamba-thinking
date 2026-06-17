from __future__ import annotations

import unittest
from unittest.mock import patch

from product_agent.models import PaperNode
from product_agent.research_agent.nodes.searcher import searcher_node
from product_agent.research_agent.relevance import evaluate_paper_relevance


RETRIEVAL_PLAN = {
    "topic": "AI agent tool use reliability evaluation",
    "topic_anchor": "LLM agent tool use evaluation",
    "strict_queries": ["LLM agent tool use evaluation"],
    "broad_queries": ["function calling robustness benchmark"],
    "filters": {},
    "rerank_signals": ["tool use", "benchmark evaluation", "reliability"],
}


class PaperRelevanceTests(unittest.TestCase):
    def test_topic_gate_rejects_facet_match_without_multimodal_topic(self) -> None:
        paper = PaperNode(
            paper_id="public-datasets",
            title=(
                "Accessibility Barriers in Multi-Terabyte Public Datasets: "
                "The Gap Between Promise and Practice"
            ),
            abstract="A study of processing costs for public scientific datasets.",
            source="arxiv",
        )

        relevance = evaluate_paper_relevance(
            paper,
            topic="大模型多模态融合",
            query="multimodal large language model fusion public datasets",
            retrieval_plan={
                "topic": "大模型多模态融合",
                "topic_anchor": "multimodal large language model fusion",
                "rerank_signals": ["public datasets"],
            },
        )

        self.assertEqual(relevance.topic_tier, "candidate")
        self.assertEqual(relevance.tier, "candidate")
        self.assertIn("topic_gate:candidate", relevance.reasons)

    def test_topic_gate_rejects_ambiguous_fusion_and_ablation_terms(self) -> None:
        cases = [
            (
                PaperNode(
                    paper_id="fusion-energy",
                    title="Potential Early Markets for Fusion Energy",
                    abstract="An economic analysis of future fusion power plants.",
                    source="arxiv",
                ),
                "early fusion",
            ),
            (
                PaperNode(
                    paper_id="laser-ablation",
                    title="Laser Ablation of Compound Semiconductors",
                    abstract="A physical study of pulsed laser ablation.",
                    source="arxiv",
                ),
                "ablation studies",
            ),
        ]

        for paper, facet in cases:
            with self.subTest(paper=paper.paper_id):
                relevance = evaluate_paper_relevance(
                    paper,
                    topic="大模型多模态融合",
                    query=f"multimodal large language model fusion {facet}",
                    retrieval_plan={
                        "topic": "大模型多模态融合",
                        "topic_anchor": "multimodal large language model fusion",
                        "rerank_signals": [facet],
                    },
                )
                self.assertEqual(relevance.topic_tier, "candidate")
                self.assertEqual(relevance.tier, "candidate")

    def test_topic_gate_keeps_traditional_multimodal_fusion_adjacent(self) -> None:
        paper = PaperNode(
            paper_id="traditional-fusion",
            title="Rethinking Early Fusion for Multimodal Image Segmentation",
            abstract="We compare feature fusion strategies for RGB and thermal images.",
            source="arxiv",
        )

        relevance = evaluate_paper_relevance(
            paper,
            topic="大模型多模态融合",
            query="multimodal large language model fusion early fusion",
            retrieval_plan={
                "topic": "大模型多模态融合",
                "topic_anchor": "multimodal large language model fusion",
                "rerank_signals": ["early fusion"],
            },
        )

        self.assertEqual(relevance.topic_tier, "adjacent")
        self.assertEqual(relevance.tier, "adjacent")

    def test_topic_gate_accepts_multimodal_llm_fusion_as_direct(self) -> None:
        paper = PaperNode(
            paper_id="mllm-fusion",
            title="Efficient Fusion in Multimodal Large Language Models",
            abstract="We evaluate early and intermediate fusion for vision and text.",
            source="arxiv",
        )

        relevance = evaluate_paper_relevance(
            paper,
            topic="大模型多模态融合",
            query="multimodal large language model fusion early fusion",
            retrieval_plan={
                "topic": "大模型多模态融合",
                "topic_anchor": "multimodal large language model fusion",
                "rerank_signals": ["early fusion"],
            },
        )

        self.assertEqual(relevance.topic_tier, "direct")
        self.assertEqual(relevance.tier, "direct")

    def test_workflow_mention_does_not_make_tokenomics_direct_collaboration_evidence(
        self,
    ) -> None:
        paper = PaperNode(
            paper_id="tokenomics",
            title="Tokenomics: Quantifying Where Tokens Are Used in Agentic Software Engineering",
            abstract=(
                "We measure token consumption across agentic software engineering "
                "workflows and discuss collaboration between automated components."
            ),
            source="arxiv",
        )

        relevance = evaluate_paper_relevance(
            paper,
            topic="multi-agent collaboration workflow for software engineering",
            query="multi-agent collaboration workflow software engineering",
            retrieval_plan={
                "rerank_signals": [
                    "multi-agent collaboration",
                    "workflow",
                    "software engineering",
                ]
            },
        )

        self.assertEqual(relevance.tier, "adjacent")

    def test_research_assistant_citation_system_is_direct_evidence(self) -> None:
        paper = PaperNode(
            paper_id="asta",
            title="Unraveling the Asta Scholarly Research Assistant Citation System",
            abstract=(
                "We study a scholarly research assistant that retrieves scientific "
                "literature and produces citations that users can verify."
            ),
            source="arxiv",
        )

        relevance = evaluate_paper_relevance(
            paper,
            topic="research agent for scientific literature with verifiable citations",
            query="scholarly research assistant citation",
            retrieval_plan={
                "rerank_signals": ["scientific literature", "verifiable citations"]
            },
        )

        self.assertEqual(relevance.tier, "direct")

    def test_direct_evidence_covers_multiple_independent_concepts(self) -> None:
        paper = PaperNode(
            paper_id="direct",
            title="MCPAgentBench: Benchmarking Tool-Using Language Agents",
            abstract=(
                "We evaluate the reliability and failure modes of LLM agents "
                "that call external tools."
            ),
            source="arxiv",
        )

        relevance = evaluate_paper_relevance(
            paper,
            topic=RETRIEVAL_PLAN["topic"],
            query=RETRIEVAL_PLAN["strict_queries"][0],
            retrieval_plan=RETRIEVAL_PLAN,
        )

        self.assertEqual(relevance.tier, "direct")
        self.assertIn("agent", relevance.matched_groups)
        self.assertIn("tool_use", relevance.matched_groups)
        self.assertIn("evaluation", relevance.matched_groups)

    def test_fuzzy_phrase_matching_keeps_inflected_evaluation_terms(self) -> None:
        paper = PaperNode(
            paper_id="inflected-benchmark",
            title="MCPAgentBench: Benchmarking Tool-Augmented LLM Agents",
            abstract=(
                "We study function-calling failures and tool selection behavior "
                "in large language model agents."
            ),
            source="arxiv",
        )

        relevance = evaluate_paper_relevance(
            paper,
            topic=RETRIEVAL_PLAN["topic"],
            query=RETRIEVAL_PLAN["strict_queries"][0],
            retrieval_plan=RETRIEVAL_PLAN,
        )

        self.assertEqual(relevance.tier, "direct")
        self.assertIn("evaluation", relevance.matched_groups)

    def test_neighboring_benchmark_is_not_promoted_to_direct_evidence(self) -> None:
        paper = PaperNode(
            paper_id="adjacent",
            title="TravelPlanner: A Benchmark for Language Agents",
            abstract="A benchmark for evaluating planning ability in language agents.",
            source="arxiv",
        )

        relevance = evaluate_paper_relevance(
            paper,
            topic=RETRIEVAL_PLAN["topic"],
            query=RETRIEVAL_PLAN["strict_queries"][0],
            retrieval_plan=RETRIEVAL_PLAN,
        )

        self.assertEqual(relevance.tier, "adjacent")

    def test_off_topic_paper_is_rejected(self) -> None:
        paper = PaperNode(
            paper_id="off-topic",
            title="Dense Monocular Non-Rigid 3D Reconstruction",
            abstract="A computer vision method for reconstructing deformable scenes.",
            source="arxiv",
        )

        relevance = evaluate_paper_relevance(
            paper,
            topic=RETRIEVAL_PLAN["topic"],
            query=RETRIEVAL_PLAN["strict_queries"][0],
            retrieval_plan=RETRIEVAL_PLAN,
        )

        self.assertEqual(relevance.tier, "candidate")
        self.assertEqual(relevance.score, 0.0)

    def test_domain_rag_qa_is_not_direct_research_assistant_evidence(self) -> None:
        plan = {
            "topic": "retrieval augmented scientific research assistant",
            "rerank_signals": [
                "scientific literature",
                "evidence citation",
                "retrieval augmented generation",
            ],
        }
        paper = PaperNode(
            paper_id="domain-rag",
            title="Retrieval-Augmented Question Answering for Electron-Ion Collider Data",
            abstract="A domain question answering system for collider experiments.",
            source="arxiv",
        )

        relevance = evaluate_paper_relevance(
            paper,
            topic=plan["topic"],
            query="scientific literature synthesis retrieval augmented",
            retrieval_plan=plan,
        )

        self.assertNotEqual(relevance.tier, "direct")
        self.assertNotIn("scientific_research", relevance.matched_groups)

    def test_scientific_domain_agent_without_citation_grounding_is_not_direct(self) -> None:
        plan = {
            "topic": "research agent for scientific literature with verifiable citations",
            "rerank_signals": [
                "scientific literature",
                "verifiable citations",
                "research assistant",
            ],
        }
        paper = PaperNode(
            paper_id="education-agent",
            title="Agentic AI for Substance Use Education",
            abstract=(
                "The system integrates regulatory and scientific literature "
                "for education and produces verifiable learning materials."
            ),
            source="arxiv",
        )

        relevance = evaluate_paper_relevance(
            paper,
            topic=plan["topic"],
            query="scientific literature review agent citation verification",
            retrieval_plan=plan,
        )

        self.assertNotEqual(relevance.tier, "direct")

    def test_methodology_paper_needs_agent_and_development_process_context(self) -> None:
        plan = {
            "topic": "agent-centric software development methodologies",
            "rerank_signals": [
                "agent-centric methodology",
                "AI agent teams",
                "software development process",
            ],
        }
        paper = PaperNode(
            paper_id="agentsway",
            title="Agentsway: Software Development Methodology for AI Agents-based Teams",
            abstract="A lifecycle and collaborative workflow for agent teams building software.",
            source="arxiv",
        )

        relevance = evaluate_paper_relevance(
            paper,
            topic=plan["topic"],
            query="agentic software engineering methodology",
            retrieval_plan=plan,
        )

        self.assertEqual(relevance.tier, "direct")
        self.assertIn("methodology", relevance.matched_groups)
        self.assertIn("team_process", relevance.matched_groups)

    def test_generic_agentic_software_paper_is_only_adjacent_to_methodology(self) -> None:
        plan = {
            "topic": "agent-centric software development methodologies",
            "rerank_signals": [
                "agent-centric methodology",
                "AI agent teams",
                "software development process",
            ],
        }
        paper = PaperNode(
            paper_id="tokenomics",
            title="Tokenomics: Quantifying Token Use in Agentic Software Engineering",
            abstract="An empirical analysis of agent workflows and team collaboration.",
            source="arxiv",
        )

        relevance = evaluate_paper_relevance(
            paper,
            topic=plan["topic"],
            query="agentic software engineering methodology",
            retrieval_plan=plan,
        )

        self.assertEqual(relevance.tier, "adjacent")

    @patch("product_agent.research_agent.nodes.searcher.search_papers")
    def test_searcher_expands_when_strict_results_are_low_relevance(self, search_arxiv) -> None:
        def results_for(query: str, max_results: int = 10):
            if "function calling" in query:
                return [
                    PaperNode(
                        paper_id="direct",
                        title="Reliable Function Calling for LLM Agents",
                        abstract="A benchmark evaluating robust tool calling by AI agents.",
                        source="arxiv",
                    )
                ]
            return [
                PaperNode(
                    paper_id="off-topic",
                    title="Dense Monocular Non-Rigid 3D Reconstruction",
                    abstract="A computer vision reconstruction method.",
                    source="arxiv",
                )
            ]

        search_arxiv.side_effect = results_for
        result = searcher_node(
            {
                "topic": RETRIEVAL_PLAN["topic"],
                "mode": "balanced",
                "max_results": 3,
                "retrieval_plan": RETRIEVAL_PLAN,
                "paper_nodes": {},
                "logs": [],
                "decisions": [],
                "tool_events": [],
                "error_events": [],
            }
        )

        outcome = result["retrieval_outcome"]
        self.assertTrue(outcome["broad_search_triggered"])
        self.assertGreaterEqual(outcome["low_relevance_filtered_count"], 1)
        self.assertEqual(outcome["direct_paper_count"], 1)
        self.assertNotIn("off-topic", result["paper_nodes"])


if __name__ == "__main__":
    unittest.main()
