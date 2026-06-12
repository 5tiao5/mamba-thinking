from __future__ import annotations

import unittest
import urllib.parse
import urllib.error
from unittest.mock import patch

from product_agent.models import PaperNode
from product_agent.research_agent.nodes.searcher import searcher_node
from product_agent.research_agent.retrieval_plan import build_retrieval_plan
from product_agent.services.query_intent import derive_query_intent
from product_agent.tools import (
    _build_arxiv_recall_query,
    _build_arxiv_search_query,
    search_papers,
    search_semantic_scholar,
)


class RetrievalQueryFamilyTests(unittest.TestCase):
    def test_failure_recovery_follow_up_prioritizes_delta_queries(self) -> None:
        intent = derive_query_intent(
            raw_user_request="缩小到近三年的论文，重点分析工具调用失败后的恢复能力，并补充新的相关论文",
            task_topic="AI Agent 工具使用评测 - 缩小到近三年的论文",
            conversation_topic="AI Agent 工具使用的评测方法，重点关注工具选择、函数调用和失败恢复",
            knowledge_scope="shared",
            reference_year=2026,
        )

        plan = build_retrieval_plan(
            topic=intent.core_topic,
            query_intent=intent.to_dict(),
            mode="balanced",
        )

        self.assertIn("failure recovery", intent.request_focus_terms)
        self.assertEqual(
            plan.strict_queries[:2],
            [
                "LLM agent tool use failure recovery evaluation",
                "tool calling error recovery robustness benchmark",
            ],
        )
        self.assertEqual(plan.filters["year_range"]["start_year"], 2023)

    def test_cost_latency_follow_up_prioritizes_comparison_queries(self) -> None:
        intent = derive_query_intent(
            raw_user_request="继续展开成本和延迟评测方向，比较它与任务成功率评测的区别",
            task_topic="AI Agent 工具使用评测 - 成本和延迟评测",
            conversation_topic="AI Agent 工具使用的评测方法，重点关注工具选择、函数调用和失败恢复",
            knowledge_scope="shared",
        )

        plan = build_retrieval_plan(
            topic=intent.core_topic,
            query_intent=intent.to_dict(),
            mode="balanced",
        )

        self.assertEqual(intent.user_goal, "compare")
        self.assertIn("cost efficiency", intent.request_focus_terms)
        self.assertIn("latency", intent.request_focus_terms)
        self.assertIn("task success rate", intent.request_focus_terms)
        self.assertEqual(
            plan.strict_queries[:2],
            [
                "LLM agent tool use cost latency task success rate evaluation",
                "tool calling efficiency versus task success benchmark",
            ],
        )

    def test_arxiv_query_does_not_wrap_the_entire_request_as_one_phrase(self) -> None:
        compiled = _build_arxiv_search_query(
            "AI Agent tool-use reliability evaluation benchmarks"
        )

        self.assertIn("all:ai", compiled)
        self.assertIn("all:agent", compiled)
        self.assertIn('all:"tool use"', compiled)
        self.assertIn(" AND ", compiled)
        self.assertNotIn(
            'all:"AI Agent tool-use reliability evaluation benchmarks"',
            compiled,
        )

    def test_recall_query_combines_short_phrases_with_or(self) -> None:
        compiled = _build_arxiv_recall_query(
            [
                "scientific research assistant",
                "literature review agent",
                "paper reading assistant",
            ]
        )

        self.assertEqual(
            compiled,
            'all:"scientific research assistant" OR '
            'all:"literature review agent" OR '
            'all:"paper reading assistant"',
        )

    @patch.dict("product_agent.tools.os.environ", {"S2_API_KEY": "test-key"})
    @patch("product_agent.tools.urllib.request.urlopen")
    def test_semantic_scholar_uses_api_key(self, urlopen) -> None:
        response = urlopen.return_value.__enter__.return_value
        response.read.return_value = b'{"data": []}'

        search_semantic_scholar("research assistant", max_results=3)

        request = urlopen.call_args.args[0]
        self.assertEqual(request.headers["X-api-key"], "test-key")

    @patch("product_agent.tools.urllib.request.urlopen")
    def test_semantic_scholar_rate_limit_is_observable(self, urlopen) -> None:
        urlopen.side_effect = urllib.error.HTTPError(
            url="https://api.semanticscholar.org",
            code=429,
            msg="Too Many Requests",
            hdrs=None,
            fp=None,
        )

        with self.assertRaisesRegex(RuntimeError, "rate limit"):
            search_semantic_scholar("research assistant", max_results=3)

    @patch("product_agent.tools.urllib.request.urlopen")
    def test_arxiv_search_sends_compiled_boolean_query(self, urlopen) -> None:
        response = urlopen.return_value.__enter__.return_value
        response.read.return_value = (
            b'<?xml version="1.0" encoding="UTF-8"?>'
            b'<feed xmlns="http://www.w3.org/2005/Atom"></feed>'
        )

        search_papers("function calling robustness benchmark", max_results=3)

        requested_url = urlopen.call_args.args[0].full_url
        search_query = urllib.parse.parse_qs(
            urllib.parse.urlparse(requested_url).query
        )["search_query"][0]
        self.assertIn('all:"function calling"', search_query)
        self.assertIn("all:robustness", search_query)
        self.assertIn("all:benchmark", search_query)

    @patch("product_agent.tools.urllib.request.urlopen")
    def test_arxiv_rate_limit_is_observable(self, urlopen) -> None:
        urlopen.side_effect = urllib.error.HTTPError(
            url="https://export.arxiv.org/api/query",
            code=429,
            msg="Too Many Requests",
            hdrs=None,
            fp=None,
        )

        with self.assertRaisesRegex(RuntimeError, "arXiv rate limit"):
            search_papers("function calling robustness", max_results=3)

    def test_tool_use_intent_builds_complementary_query_family(self) -> None:
        plan = build_retrieval_plan(
            topic="AI Agent 工具使用可靠性评测",
            query_intent={
                "core_topic": "AI Agent 工具使用可靠性评测",
                "user_goal": "benchmark_evaluation",
                "focus_terms": ["tool use", "benchmark evaluation"],
                "paper_scope": ["benchmark evaluation"],
            },
            mode="default",
        )

        all_queries = plan.all_queries()
        self.assertIn("LLM agent tool use evaluation", all_queries)
        self.assertIn("tool-using language agents benchmark", all_queries)
        self.assertIn("function calling robustness benchmark", all_queries)
        self.assertGreaterEqual(len(plan.broad_queries), 3)

    def test_methodology_intent_uses_academic_synonym_family(self) -> None:
        plan = build_retrieval_plan(
            topic="Agent-Centric Software Development Methodologies",
            query_intent={
                "core_topic": "agent-centric software development methodologies",
                "user_goal": "extend_context",
                "focus_terms": ["agent-centric methodology", "AI agent teams"],
                "paper_scope": ["software development process"],
            },
            mode="balanced",
        )

        self.assertEqual(
            plan.strict_queries[:3],
            [
                "agentic software engineering methodology",
                "AI agent software development lifecycle",
                "multi-agent software development process",
            ],
        )
        self.assertIn("agent-oriented software engineering", plan.broad_queries)

    def test_research_assistant_rag_uses_literature_and_citation_queries(self) -> None:
        plan = build_retrieval_plan(
            topic="RAG-based scientific research assistant with evidence citation",
            query_intent={
                "core_topic": "retrieval augmented scientific research assistant",
                "user_goal": "survey",
                "focus_terms": ["scientific literature", "evidence citation"],
                "paper_scope": ["retrieval augmented generation"],
            },
            mode="balanced",
        )

        self.assertEqual(
            plan.strict_queries[:3],
            [
                "scientific literature synthesis retrieval augmented",
                "research assistant evidence citation RAG",
                "automated literature review retrieval augmented",
            ],
        )
        self.assertIn("literature review agent retrieval evidence", plan.broad_queries)
        self.assertEqual(
            plan.recall_queries[:3],
            [
                "scholarly research assistant citation",
                "literature review agent",
                "scientific literature source attribution",
            ],
        )

    def test_paper_reading_agent_without_rag_still_gets_research_query_family(self) -> None:
        plan = build_retrieval_plan(
            topic="能自动阅读论文并给出可核验引用的 research agent",
            query_intent={
                "core_topic": "research agent for scientific literature with verifiable citations",
                "user_goal": "survey",
                "focus_terms": ["scientific literature", "verifiable citations"],
                "paper_scope": ["research assistant"],
            },
            mode="balanced",
        )

        self.assertEqual(
            plan.strict_queries[:3],
            [
                "scientific literature synthesis retrieval augmented",
                "research assistant scholarly papers verifiable citations",
                "automated paper reading literature synthesis agent",
            ],
        )
        self.assertEqual(
            plan.recall_queries[:3],
            [
                "scholarly research assistant citation",
                "literature review agent",
                "paper reading assistant",
            ],
        )

    @patch(
        "product_agent.research_agent.nodes.searcher.search_semantic_scholar",
        return_value=[],
    )
    @patch("product_agent.research_agent.nodes.searcher.search_papers_recall")
    @patch("product_agent.research_agent.nodes.searcher.search_papers")
    def test_balanced_mode_uses_recall_rescue_when_direct_evidence_is_missing(
        self,
        search_arxiv,
        search_recall,
        _search_s2,
    ) -> None:
        search_arxiv.return_value = [
            PaperNode(
                paper_id="adjacent",
                title="Scientific Question Answering with Language Models",
                abstract="Answers scientific questions from retrieved documents.",
                source="arxiv",
            )
        ]
        search_recall.return_value = [
            PaperNode(
                paper_id="direct",
                title="An Agentic System for Performing Scientific Literature Review",
                abstract=(
                    "A research assistant that reads scientific literature and "
                    "provides verifiable citations with source attribution."
                ),
                source="arxiv",
            )
        ]
        plan = build_retrieval_plan(
            topic="research agent for scientific literature with verifiable citations",
            query_intent={
                "core_topic": "research agent for scientific literature with verifiable citations",
                "user_goal": "survey",
                "focus_terms": ["scientific literature", "verifiable citations"],
                "paper_scope": ["research assistant"],
            },
            mode="balanced",
        )

        result = searcher_node(
            {
                "topic": plan.topic,
                "mode": "balanced",
                "max_results": 6,
                "retrieval_plan": plan.to_dict(),
                "paper_nodes": {},
                "logs": [],
                "decisions": [],
                "tool_events": [],
                "error_events": [],
            }
        )

        self.assertTrue(result["retrieval_outcome"]["recall_rescue_triggered"])
        self.assertIn("direct", result["paper_nodes"])
        search_recall.assert_called_once_with(
            plan.recall_queries[:3],
            max_results=12,
        )

    @patch("product_agent.research_agent.nodes.searcher.search_papers")
    def test_broad_queries_continue_to_expand_the_evidence_pool(
        self,
        search_arxiv,
    ) -> None:
        def results_for(query: str, max_results: int = 10):
            if "primary" in query:
                return [
                    PaperNode(
                        paper_id="primary-1",
                        title="MCP Reliability Benchmark for Tool-Using AI Agents",
                        abstract="Evaluation benchmark for reliable tool-using AI agents.",
                        source="arxiv",
                    ),
                    PaperNode(
                        paper_id="primary-2",
                        title="Failure Taxonomy of Tool Calling Language Agents",
                        abstract="Evaluation of failures in tool-using language agents.",
                        source="arxiv",
                    ),
                ]
            return [
                PaperNode(
                    paper_id="secondary-1",
                    title="Evaluating API Orchestration in Autonomous Agents",
                    abstract="A tool use benchmark for reliable autonomous agents.",
                    source="arxiv",
                ),
                PaperNode(
                    paper_id="secondary-2",
                    title="Robust Function Calling Metrics for LLM Agents",
                    abstract="Benchmark metrics for robust tool calling by LLM agents.",
                    source="arxiv",
                ),
            ]

        search_arxiv.side_effect = results_for
        result = searcher_node(
            {
                "topic": "AI agent tool use benchmark",
                "mode": "balanced",
                "max_results": 4,
                "retrieval_plan": {
                    "topic": "AI agent tool use benchmark",
                    "strict_queries": ["primary strict", "secondary strict"],
                    "broad_queries": ["broad expansion"],
                    "filters": {},
                    "rerank_signals": ["tool use", "benchmark"],
                },
                "paper_nodes": {},
                "logs": [],
                "decisions": [],
                "tool_events": [],
                "error_events": [],
            }
        )

        attempted = result["retrieval_outcome"]["queries_attempted"]
        self.assertEqual(
            [item["query"] for item in attempted],
            ["primary strict", "secondary strict", "broad expansion"],
        )
        self.assertTrue(result["retrieval_outcome"]["broad_search_triggered"])
        self.assertIn("broad expansion", [call.args[0] for call in search_arxiv.call_args_list])
        self.assertEqual(len(result["evidence_pool"]), 4)
        self.assertEqual(len(result["paper_nodes"]), 4)

    @patch("product_agent.research_agent.nodes.searcher.search_papers")
    def test_evidence_pool_keeps_all_qualified_papers_beyond_analysis_limit(
        self,
        search_arxiv,
    ) -> None:
        titles = [
            "MCP Agent Tool Use Reliability Benchmark",
            "Robust Function Calling Evaluation for Language Agents",
            "Failure Modes of API-Using Autonomous Agents",
            "Benchmarking External Tool Selection in LLM Agents",
            "Reliable Tool Invocation Metrics for AI Agents",
            "Evaluating Multi-Step Tool Calls by Language Agents",
        ]
        search_arxiv.return_value = [
            PaperNode(
                paper_id=f"paper-{index}",
                title=title,
                abstract="Evaluation of tool calling reliability and failure modes.",
                source="arxiv",
            )
            for index, title in enumerate(titles)
        ]

        result = searcher_node(
            {
                "topic": "AI agent tool use benchmark",
                "mode": "balanced",
                "max_results": 3,
                "retrieval_plan": {
                    "topic": "AI agent tool use benchmark",
                    "strict_queries": ["agent tool calling evaluation"],
                    "broad_queries": ["function calling robustness"],
                    "recall_queries": [],
                    "filters": {},
                    "rerank_signals": ["tool use", "benchmark"],
                },
                "evidence_pool": {},
                "paper_nodes": {},
                "logs": [],
                "decisions": [],
                "tool_events": [],
                "error_events": [],
            }
        )

        self.assertEqual(len(result["evidence_pool"]), 6)
        self.assertEqual(len(result["paper_nodes"]), 3)
        self.assertEqual(result["retrieval_outcome"]["evidence_pool_count"], 6)
        self.assertEqual(result["retrieval_outcome"]["analysis_paper_count"], 3)


if __name__ == "__main__":
    unittest.main()
