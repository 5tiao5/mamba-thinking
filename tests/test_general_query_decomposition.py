from __future__ import annotations

import unittest
from unittest.mock import patch

from product_agent.research_agent.nodes.planner import planner_node
from product_agent.research_agent.nodes.searcher import searcher_node
from product_agent.models import PaperNode
from product_agent.research_agent.query_coverage import (
    audit_evidence_coverage,
    audit_query_coverage,
    facet_rescue_queries,
)
from product_agent.research_agent.query_expansion import expand_focus_facets
from product_agent.research_agent.retrieval_plan import build_retrieval_plan
from product_agent.services.query_intent import derive_query_intent


class GeneralQueryDecompositionTests(unittest.TestCase):
    def test_extracts_arbitrary_chinese_focus_facets(self) -> None:
        intent = derive_query_intent(
            raw_user_request=(
                "补充近三年的新论文，重点关注融合架构、跨模态对齐"
                "和缺失模态鲁棒性"
            ),
            task_topic="大模型多模态融合 - 补充近三年的新论文",
            conversation_topic="大模型多模态融合",
            knowledge_scope="conversation",
            reference_year=2026,
        )

        labels = [facet["label"] for facet in intent.focus_facets]
        self.assertEqual(
            labels,
            ["融合架构", "跨模态对齐", "缺失模态鲁棒性"],
        )
        self.assertEqual(intent.time_range["start_year"], 2023)
        self.assertTrue(all(facet["required"] for facet in intent.focus_facets))

    def test_extracts_mixed_language_focus_facets(self) -> None:
        intent = derive_query_intent(
            raw_user_request=(
                "Focus on cross-modal alignment, missing modality robustness "
                "and 轻量化部署"
            ),
            task_topic="multimodal large language models",
            conversation_topic="multimodal large language models",
            knowledge_scope="shared",
        )

        labels = [facet["label"] for facet in intent.focus_facets]
        self.assertEqual(
            labels,
            [
                "cross-modal alignment",
                "missing modality robustness",
                "轻量化部署",
            ],
        )

    def test_generic_reference_is_not_treated_as_a_facet(self) -> None:
        intent = derive_query_intent(
            raw_user_request="继续展开这个方向，并补充新论文",
            task_topic="AI Agent 工具使用评测",
            conversation_topic="AI Agent 工具使用评测",
            knowledge_scope="shared",
        )

        self.assertEqual(intent.focus_facets, [])

    def test_retrieval_plan_preserves_structured_facets(self) -> None:
        intent = derive_query_intent(
            raw_user_request="重点关注跨模态对齐和缺失模态鲁棒性",
            task_topic="大模型多模态融合",
            conversation_topic="大模型多模态融合",
            knowledge_scope="conversation",
        )

        plan = build_retrieval_plan(
            topic=intent.core_topic,
            query_intent=intent.to_dict(),
            mode="balanced",
        )

        self.assertEqual(plan.focus_facets, intent.focus_facets)
        self.assertIn("跨模态对齐", plan.rerank_signals)
        self.assertIn("缺失模态鲁棒性", plan.rerank_signals)

    @patch(
        "product_agent.research_agent.query_expansion.call_openai_json",
        return_value={
            "facets": [
                {
                    "label": "跨模态对齐",
                    "academic_terms": [
                        "cross-modal alignment",
                        "vision-language alignment",
                    ],
                    "queries": [
                        "multimodal large language models cross-modal alignment"
                    ],
                },
                {
                    "label": "缺失模态鲁棒性",
                    "academic_terms": [
                        "missing modality robustness",
                        "incomplete multimodal learning",
                    ],
                    "queries": [
                        "multimodal learning missing modality robustness"
                    ],
                },
            ]
        },
    )
    @patch(
        "product_agent.research_agent.query_expansion.has_openai_key",
        return_value=True,
    )
    def test_expands_chinese_facets_into_academic_queries(
        self,
        _has_key,
        call_llm,
    ) -> None:
        intent = derive_query_intent(
            raw_user_request="重点关注跨模态对齐和缺失模态鲁棒性",
            task_topic="大模型多模态融合",
            conversation_topic="大模型多模态融合",
            knowledge_scope="conversation",
        )

        expanded, outcome = expand_focus_facets(
            query_intent=intent.to_dict(),
            topic=intent.core_topic,
            mode="balanced",
        )
        plan = build_retrieval_plan(
            topic=intent.core_topic,
            query_intent=expanded,
            mode="balanced",
        )

        self.assertEqual(outcome["status"], "expanded")
        self.assertEqual(call_llm.call_count, 1)
        self.assertEqual(
            plan.strict_queries[:2],
            [
                "multimodal large language models cross-modal alignment",
                "multimodal learning missing modality robustness",
            ],
        )
        self.assertIn("cross-modal alignment", plan.rerank_signals)
        self.assertIn("missing modality robustness", plan.rerank_signals)

    @patch(
        "product_agent.research_agent.query_expansion.has_openai_key",
        return_value=False,
    )
    def test_missing_llm_key_keeps_original_facets(self, _has_key) -> None:
        intent = derive_query_intent(
            raw_user_request="重点关注跨模态对齐",
            task_topic="大模型多模态融合",
            conversation_topic="大模型多模态融合",
            knowledge_scope="conversation",
        )

        expanded, outcome = expand_focus_facets(
            query_intent=intent.to_dict(),
            topic=intent.core_topic,
            mode="balanced",
        )

        self.assertEqual(outcome["status"], "no_llm_key")
        self.assertEqual(expanded["focus_facets"], intent.focus_facets)

    @patch(
        "product_agent.research_agent.query_expansion.call_openai_json",
        return_value={
            "topic_anchor": "large language models causal reasoning",
            "topic_alias_queries": [
                "large language models causal reasoning",
                "LLM causal discovery",
            ],
            "broad_queries": ["counterfactual reasoning language models"],
            "recall_queries": ["causal discovery LLM"],
            "facets": [],
        },
    )
    @patch(
        "product_agent.research_agent.query_expansion.has_openai_key",
        return_value=True,
    )
    def test_llm_expands_chinese_topic_anchor_without_required_facets(
        self,
        _has_key,
        _call_llm,
    ) -> None:
        topic = "\u5927\u6a21\u578b\u56e0\u679c\u63a8\u7406"
        expanded, outcome = expand_focus_facets(
            query_intent={"core_topic": topic, "focus_facets": []},
            topic=topic,
            mode="balanced",
        )
        plan = build_retrieval_plan(
            topic=topic,
            query_intent=expanded,
            mode="balanced",
        )

        self.assertEqual(outcome["status"], "expanded")
        self.assertEqual(plan.topic_anchor, "large language models causal reasoning")
        self.assertIn("LLM causal discovery", plan.strict_queries)
        self.assertIn("counterfactual reasoning language models", plan.broad_queries)
        self.assertIn("causal discovery LLM", plan.recall_queries)

    @patch(
        "product_agent.research_agent.query_expansion.has_openai_key",
        return_value=False,
    )
    def test_planner_marks_untranslated_required_facet_as_uncovered(
        self,
        _has_key,
    ) -> None:
        intent = derive_query_intent(
            raw_user_request="重点关注跨模态对齐",
            task_topic="大模型多模态融合",
            conversation_topic="大模型多模态融合",
            knowledge_scope="conversation",
        )

        planned = planner_node(
            {
                "topic": intent.core_topic,
                "mode": "balanced",
                "query_intent": intent.to_dict(),
                "logs": [],
                "decisions": [],
                "tool_events": [],
                "error_events": [],
            }
        )

        self.assertEqual(planned["query_coverage"]["status"], "uncovered")
        self.assertEqual(
            planned["query_coverage"]["uncovered_facets"],
            ["跨模态对齐"],
        )

    @patch(
        "product_agent.research_agent.query_expansion.call_openai_json",
        return_value={
            "facets": [
                {
                    "label": "跨模态对齐",
                    "academic_terms": ["cross-modal alignment"],
                    "queries": [
                        "multimodal large language models cross-modal alignment"
                    ],
                }
            ]
        },
    )
    @patch(
        "product_agent.research_agent.query_expansion.has_openai_key",
        return_value=True,
    )
    def test_planner_executes_expanded_facet_query_in_balanced_mode(
        self,
        _has_key,
        _call_llm,
    ) -> None:
        intent = derive_query_intent(
            raw_user_request="重点关注跨模态对齐",
            task_topic="大模型多模态融合",
            conversation_topic="大模型多模态融合",
            knowledge_scope="conversation",
        )

        planned = planner_node(
            {
                "topic": intent.core_topic,
                "mode": "balanced",
                "query_intent": intent.to_dict(),
                "logs": [],
                "decisions": [],
                "tool_events": [],
                "error_events": [],
            }
        )

        self.assertEqual(
            planned["search_queries"][0],
            "multimodal large language models cross-modal alignment",
        )
        self.assertEqual(
            planned["query_intent"]["focus_facets"][0]["expansion_source"],
            "llm",
        )
        self.assertEqual(planned["query_coverage"]["status"], "covered")

    def test_query_coverage_reports_partial_mapping(self) -> None:
        coverage = audit_query_coverage(
            focus_facets=[
                {
                    "label": "跨模态对齐",
                    "required": True,
                    "search_terms": ["cross-modal alignment"],
                    "query_candidates": [
                        "multimodal large language models cross-modal alignment"
                    ],
                },
                {
                    "label": "缺失模态鲁棒性",
                    "required": True,
                },
            ],
            scheduled_queries=[
                "multimodal large language models cross-modal alignment",
                "multimodal large language model fusion",
            ],
        )

        self.assertEqual(coverage["status"], "partial")
        self.assertEqual(coverage["covered_count"], 1)
        self.assertEqual(coverage["uncovered_facets"], ["缺失模态鲁棒性"])

    def test_evidence_coverage_distinguishes_direct_and_adjacent_support(self) -> None:
        coverage = audit_evidence_coverage(
            focus_facets=[
                {
                    "label": "跨模态对齐",
                    "required": True,
                    "search_terms": [
                        "cross-modal alignment",
                        "vision-language alignment",
                    ],
                },
                {
                    "label": "缺失模态鲁棒性",
                    "required": True,
                    "search_terms": ["missing modality robustness"],
                },
            ],
            papers={
                "alignment-direct": PaperNode(
                    paper_id="alignment-direct",
                    title="Cross-Modal Alignment for Multimodal Language Models",
                    abstract="We align visual and language representations.",
                    source="arxiv",
                    relevance_tier="direct",
                ),
                "missing-adjacent": PaperNode(
                    paper_id="missing-adjacent",
                    title="Robust Multimodal Representation Learning",
                    abstract=(
                        "The method studies missing modality robustness under "
                        "incomplete sensor observations."
                    ),
                    source="arxiv",
                    relevance_tier="adjacent",
                ),
            },
        )

        self.assertEqual(coverage["status"], "partial")
        self.assertEqual(coverage["supported_count"], 1)
        self.assertEqual(coverage["weak_facets"], ["缺失模态鲁棒性"])
        self.assertEqual(
            coverage["facets"][0]["matched_papers"][0]["paper_id"],
            "alignment-direct",
        )

    def test_evidence_coverage_reports_missing_and_unevaluable_facets(self) -> None:
        coverage = audit_evidence_coverage(
            focus_facets=[
                {
                    "label": "缺失模态鲁棒性",
                    "required": True,
                    "search_terms": ["missing modality robustness"],
                },
                {
                    "label": "融合架构",
                    "required": True,
                },
            ],
            papers={
                "unrelated": PaperNode(
                    paper_id="unrelated",
                    title="Efficient Video Captioning",
                    abstract="A visual question answering system.",
                    source="arxiv",
                    relevance_tier="candidate",
                ),
            },
        )

        self.assertEqual(coverage["status"], "uncovered")
        self.assertEqual(coverage["missing_facets"], ["缺失模态鲁棒性"])
        self.assertEqual(coverage["unevaluable_facets"], ["融合架构"])

    def test_searcher_attaches_facet_evidence_coverage_to_outcome(self) -> None:
        result = searcher_node(
            {
                "topic": "multimodal large language models",
                "mode": "balanced",
                "research_mode": "imported_only",
                "max_results": 4,
                "retrieval_plan": {
                    "topic": "multimodal large language models",
                    "strict_queries": [
                        "multimodal large language models cross-modal alignment"
                    ],
                    "broad_queries": [],
                    "filters": {},
                    "rerank_signals": ["cross-modal alignment"],
                    "focus_facets": [
                        {
                            "label": "跨模态对齐",
                            "required": True,
                            "search_terms": ["cross-modal alignment"],
                            "query_candidates": [
                                "multimodal large language models cross-modal alignment"
                            ],
                        }
                    ],
                },
                "evidence_pool": {
                    "uploaded-alignment": PaperNode(
                        paper_id="uploaded-alignment",
                        title=(
                            "Cross-Modal Alignment for Multimodal "
                            "Large Language Models"
                        ),
                        abstract="Alignment of visual and language representations.",
                        source="user_upload",
                        paper_pool_status="core",
                        relevance_tier="direct",
                    )
                },
                "logs": [],
                "decisions": [],
                "tool_events": [],
                "error_events": [],
            }
        )

        coverage = result["retrieval_outcome"]["facet_evidence_coverage"]
        self.assertEqual(coverage["status"], "covered")
        self.assertEqual(coverage["supported_count"], 1)
        self.assertEqual(
            coverage["facets"][0]["matched_papers"][0]["paper_id"],
            "uploaded-alignment",
        )
        self.assertEqual(result["evidence_coverage"], coverage)

    def test_adjacent_topic_paper_cannot_create_strong_facet_coverage(self) -> None:
        coverage = audit_evidence_coverage(
            focus_facets=[
                {
                    "label": "early fusion",
                    "required": True,
                    "search_terms": ["early fusion"],
                }
            ],
            papers={
                "traditional-fusion-1": PaperNode(
                    paper_id="traditional-fusion-1",
                    title="Early Fusion for Multimodal Image Segmentation",
                    abstract="An RGB and thermal image segmentation model.",
                    source="arxiv",
                    relevance_tier="adjacent",
                ),
                "traditional-fusion-2": PaperNode(
                    paper_id="traditional-fusion-2",
                    title="Comparing Early Fusion in Clinical Multimodal Data",
                    abstract="A clinical prediction study.",
                    source="arxiv",
                    relevance_tier="adjacent",
                ),
            },
        )

        facet = coverage["facets"][0]
        self.assertEqual(coverage["status"], "partial")
        self.assertEqual(facet["evidence_level"], "adjacent_only")
        self.assertEqual(facet["direct_paper_count"], 0)
        self.assertEqual(facet["adjacent_paper_count"], 2)
        self.assertEqual(
            facet["matched_papers"][0]["paper_relevance_tier"],
            "adjacent",
        )

    def test_direct_topic_paper_with_title_match_supports_facet(self) -> None:
        coverage = audit_evidence_coverage(
            focus_facets=[
                {
                    "label": "early fusion",
                    "required": True,
                    "search_terms": ["early fusion"],
                }
            ],
            papers={
                "mllm-fusion": PaperNode(
                    paper_id="mllm-fusion",
                    title=(
                        "Early Fusion in Multimodal Large Language Models"
                    ),
                    abstract="A benchmark for vision-language reasoning.",
                    source="arxiv",
                    relevance_tier="direct",
                )
            },
        )

        facet = coverage["facets"][0]
        self.assertEqual(coverage["status"], "covered")
        self.assertEqual(facet["evidence_level"], "supported")
        self.assertEqual(facet["direct_paper_count"], 1)
        self.assertEqual(
            facet["matched_papers"][0]["facet_match_location"],
            "title",
        )

    def test_facet_rescue_uses_an_untried_synonym(self) -> None:
        rescue = facet_rescue_queries(
            focus_facets=[
                {
                    "label": "缺失模态鲁棒性",
                    "required": True,
                    "search_terms": [
                        "missing modality robustness",
                        "incomplete multimodal learning",
                    ],
                    "query_candidates": [
                        "multimodal learning missing modality robustness"
                    ],
                }
            ],
            evidence_coverage={
                "missing_facets": ["缺失模态鲁棒性"],
                "weak_facets": [],
            },
            attempted_queries=[
                "multimodal learning missing modality robustness"
            ],
            topic_anchor="multimodal learning",
        )
        self.assertEqual(
            rescue,
            [
                {
                    "facet": "缺失模态鲁棒性",
                    "query": "incomplete multimodal learning",
                }
            ],
        )

    def test_facet_rescue_does_not_run_for_covered_facet(self) -> None:
        rescue = facet_rescue_queries(
            focus_facets=[
                {
                    "label": "跨模态对齐",
                    "required": True,
                    "search_terms": [
                        "cross-modal alignment",
                        "vision-language alignment",
                    ],
                    "query_candidates": [
                        "multimodal models cross-modal alignment"
                    ],
                }
            ],
            evidence_coverage={
                "missing_facets": [],
                "weak_facets": [],
            },
            attempted_queries=["multimodal models cross-modal alignment"],
            topic_anchor="multimodal models",
        )

        self.assertEqual(rescue, [])

    def test_facet_rescue_keeps_the_stable_topic_anchor(self) -> None:
        rescue = facet_rescue_queries(
            focus_facets=[
                {
                    "label": "public datasets",
                    "required": True,
                    "search_terms": ["public datasets"],
                    "query_candidates": [
                        "multimodal large language model fusion public datasets"
                    ],
                }
            ],
            evidence_coverage={
                "missing_facets": ["public datasets"],
                "weak_facets": [],
            },
            attempted_queries=[
                "multimodal large language model fusion benchmark datasets"
            ],
            topic_anchor="multimodal large language model fusion",
        )

        self.assertEqual(
            rescue,
            [
                {
                    "facet": "public datasets",
                    "query": (
                        "multimodal large language model fusion public datasets"
                    ),
                }
            ],
        )

    @patch.dict(
        "product_agent.research_agent.nodes.searcher.os.environ",
        {"CITATION_ENRICHMENT": "0"},
    )
    @patch("product_agent.research_agent.nodes.searcher.search_papers")
    def test_searcher_rescues_weak_facet_with_targeted_query(
        self,
        search_arxiv,
    ) -> None:
        def results_for(query: str, max_results: int = 10):
            if query == "incomplete multimodal learning":
                return [
                    PaperNode(
                        paper_id="direct-missing-modality",
                        title=(
                            "Incomplete Multimodal Learning for Missing "
                            "Modality Robustness"
                        ),
                        abstract="A robust method for incomplete observations.",
                        source="arxiv",
                    )
                ]
            return [
                PaperNode(
                    paper_id="adjacent-missing-modality",
                    title="Robust Multimodal Representation Learning",
                    abstract=(
                        "We discuss missing modality robustness as a secondary "
                        "evaluation setting."
                    ),
                    source="arxiv",
                )
            ]

        search_arxiv.side_effect = results_for
        result = searcher_node(
            {
                "topic": "multimodal learning",
                "mode": "balanced",
                "max_results": 4,
                "retrieval_plan": {
                    "topic": "multimodal learning",
                    "user_goal": "follow_up",
                    "strict_queries": [
                        "multimodal learning missing modality robustness"
                    ],
                    "broad_queries": [],
                    "recall_queries": [],
                    "filters": {},
                    "rerank_signals": [
                        "missing modality robustness",
                        "incomplete multimodal learning",
                    ],
                    "focus_facets": [
                        {
                            "label": "缺失模态鲁棒性",
                            "required": True,
                            "search_terms": [
                                "missing modality robustness",
                                "incomplete multimodal learning",
                            ],
                            "query_candidates": [
                                "multimodal learning missing modality robustness"
                            ],
                        }
                    ],
                },
                "evidence_pool": {},
                "paper_nodes": {},
                "logs": [],
                "decisions": [],
                "tool_events": [],
                "error_events": [],
            }
        )

        outcome = result["retrieval_outcome"]
        self.assertTrue(outcome["facet_rescue_triggered"])
        self.assertEqual(
            outcome["facet_rescue_queries"],
            [
                {
                    "facet": "缺失模态鲁棒性",
                    "query": "incomplete multimodal learning",
                }
            ],
        )
        self.assertEqual(
            outcome["facet_evidence_coverage"]["status"],
            "covered",
        )
        self.assertIn("direct-missing-modality", result["evidence_pool"])

    @patch.dict(
        "product_agent.research_agent.nodes.searcher.os.environ",
        {"CITATION_ENRICHMENT": "0"},
    )
    @patch(
        "product_agent.research_agent.nodes.searcher.search_papers",
        return_value=[],
    )
    def test_failed_facet_rescue_remains_explicitly_missing(
        self,
        search_arxiv,
    ) -> None:
        result = searcher_node(
            {
                "topic": "multimodal learning",
                "mode": "balanced",
                "max_results": 4,
                "retrieval_plan": {
                    "topic": "multimodal learning",
                    "strict_queries": [
                        "multimodal learning missing modality robustness"
                    ],
                    "broad_queries": [],
                    "recall_queries": [],
                    "filters": {"year_range": {"start_year": 2023, "end_year": 2026}},
                    "rerank_signals": ["missing modality robustness"],
                    "focus_facets": [
                        {
                            "label": "缺失模态鲁棒性",
                            "required": True,
                            "search_terms": [
                                "missing modality robustness",
                                "incomplete multimodal learning",
                            ],
                            "query_candidates": [
                                "multimodal learning missing modality robustness"
                            ],
                        }
                    ],
                },
                "evidence_pool": {},
                "paper_nodes": {},
                "logs": [],
                "decisions": [],
                "tool_events": [],
                "error_events": [],
            }
        )

        outcome = result["retrieval_outcome"]
        self.assertTrue(outcome["facet_rescue_triggered"])
        self.assertEqual(
            outcome["facet_evidence_coverage"]["missing_facets"],
            ["缺失模态鲁棒性"],
        )
        self.assertGreaterEqual(search_arxiv.call_count, 2)

    @patch(
        "product_agent.research_agent.query_expansion.call_openai_json",
        return_value={
            "facets": [
                {
                    "label": "融合架构",
                    "academic_terms": ["multimodal fusion architecture"],
                    "queries": ["multimodal large models fusion architecture"],
                },
                {
                    "label": "跨模态对齐",
                    "academic_terms": ["cross-modal alignment"],
                    "queries": ["multimodal large models cross-modal alignment"],
                },
                {
                    "label": "缺失模态鲁棒性",
                    "academic_terms": ["missing modality robustness"],
                    "queries": ["multimodal learning missing modality robustness"],
                },
            ]
        },
    )
    @patch(
        "product_agent.research_agent.query_expansion.has_openai_key",
        return_value=True,
    )
    def test_balanced_mode_schedules_every_required_facet(
        self,
        _has_key,
        _call_llm,
    ) -> None:
        intent = derive_query_intent(
            raw_user_request="重点关注融合架构、跨模态对齐和缺失模态鲁棒性",
            task_topic="大模型多模态融合",
            conversation_topic="大模型多模态融合",
            knowledge_scope="conversation",
        )

        planned = planner_node(
            {
                "topic": intent.core_topic,
                "mode": "balanced",
                "query_intent": intent.to_dict(),
                "logs": [],
                "decisions": [],
                "tool_events": [],
                "error_events": [],
            }
        )

        self.assertEqual(planned["query_coverage"]["status"], "covered")
        self.assertEqual(planned["query_coverage"]["covered_count"], 3)
        self.assertEqual(
            planned["search_queries"][:3],
            [
                "multimodal large models fusion architecture",
                "multimodal large models cross-modal alignment",
                "multimodal learning missing modality robustness",
            ],
        )


if __name__ == "__main__":
    unittest.main()
