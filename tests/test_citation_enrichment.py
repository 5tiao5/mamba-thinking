from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from product_agent.models import PaperNode
from product_agent.research_agent.nodes.searcher import (
    _select_papers_for_analysis,
    searcher_node,
)
from product_agent.tools import (
    _semantic_scholar_identifiers,
    enrich_paper_metadata,
    enrich_paper_references,
)


class CitationEnrichmentTests(unittest.TestCase):
    def test_arxiv_and_doi_identifiers_use_semantic_scholar_prefixes(self) -> None:
        arxiv = PaperNode(
            paper_id="2401.01234",
            source="arxiv",
            doi="https://doi.org/10.1000/example",
        )

        identifiers = _semantic_scholar_identifiers(arxiv)

        self.assertEqual(
            identifiers,
            ["DOI:10.1000/example", "ARXIV:2401.01234"],
        )

    def test_arxiv_version_suffix_is_removed_for_semantic_scholar(self) -> None:
        paper = PaperNode(
            paper_id="2512.24565v3",
            source="arxiv",
        )

        self.assertEqual(
            _semantic_scholar_identifiers(paper),
            ["ARXIV:2512.24565"],
        )

    @patch("product_agent.tools._fetch_s2_metadata_batch")
    def test_cross_source_reference_maps_to_local_canonical_id(self, fetch_metadata) -> None:
        predecessor = PaperNode(
            paper_id="2401.01234",
            title="Earlier arXiv Paper",
            source="arxiv",
            url="https://arxiv.org/abs/2401.01234",
        )
        successor = PaperNode(
            paper_id="s2-paper-b",
            title="Later Semantic Scholar Paper",
            source="semantic_scholar",
        )
        fetch_metadata.return_value = [
            {"citationCount": 12, "references": []},
            {
                "citationCount": 3,
                "references": [
                    {
                        "paperId": "other-s2-id",
                        "externalIds": {"ArXiv": "2401.01234"},
                    }
                ],
            },
        ]

        enriched, linked = enrich_paper_references(
            {
                predecessor.paper_id: predecessor,
                successor.paper_id: successor,
            }
        )

        self.assertEqual(enriched, 2)
        self.assertEqual(linked, 1)
        self.assertEqual(successor.references, ["2401.01234"])
        self.assertTrue(successor.citation_count_known)
        self.assertEqual(successor.citation_count, 3)

    @patch("product_agent.research_agent.nodes.searcher.enrich_paper_metadata")
    @patch("product_agent.research_agent.nodes.searcher.search_survey_papers", return_value=[])
    @patch("product_agent.research_agent.nodes.searcher.search_semantic_scholar", return_value=[])
    @patch("product_agent.research_agent.nodes.searcher.search_papers", return_value=[])
    def test_full_mode_enables_enrichment_by_default(
        self,
        _search_arxiv,
        _search_s2,
        _search_surveys,
        enrich_references,
    ) -> None:
        enrich_references.return_value = (1, 0, 1)
        state = {
            "topic": "AI agents",
            "mode": "full",
            "max_results": 3,
            "retrieval_plan": {
                "topic": "AI agents",
                "strict_queries": ["AI agents"],
                "broad_queries": [],
                "filters": {},
                "rerank_signals": [],
            },
            "paper_nodes": {
                "paper-a": PaperNode(
                    paper_id="paper-a",
                    title="A Real Paper",
                    source="semantic_scholar",
                )
            },
        }

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CITATION_ENRICHMENT", None)
            result = searcher_node(state)

        enrich_references.assert_called_once()
        event = next(
            item
            for item in result["tool_events"]
            if item["tool_name"] == "Semantic Scholar citation enrichment"
        )
        self.assertEqual(event["status"], "success")

    @patch("product_agent.research_agent.nodes.searcher.enrich_paper_metadata")
    @patch("product_agent.research_agent.nodes.searcher.search_survey_papers", return_value=[])
    @patch("product_agent.research_agent.nodes.searcher.search_semantic_scholar", return_value=[])
    @patch("product_agent.research_agent.nodes.searcher.search_papers", return_value=[])
    def test_enrichment_can_be_explicitly_disabled(
        self,
        _search_arxiv,
        _search_s2,
        _search_surveys,
        enrich_references,
    ) -> None:
        state = {
            "topic": "AI agents",
            "mode": "full",
            "max_results": 3,
            "retrieval_plan": {
                "topic": "AI agents",
                "strict_queries": ["AI agents"],
                "broad_queries": [],
                "filters": {},
                "rerank_signals": [],
            },
            "paper_nodes": {
                "paper-a": PaperNode(
                    paper_id="paper-a",
                    title="A Real Paper",
                    source="semantic_scholar",
                )
            },
        }

        with patch.dict(os.environ, {"CITATION_ENRICHMENT": "0"}):
            result = searcher_node(state)

        enrich_references.assert_not_called()
        event = next(
            item
            for item in result["tool_events"]
            if item["tool_name"] == "Semantic Scholar citation enrichment"
        )
        self.assertEqual(event["status"], "skipped")

    @patch("product_agent.tools._fetch_s2_metadata_batch", return_value=[None])
    def test_missing_metadata_keeps_citation_count_unknown(self, _fetch_metadata) -> None:
        paper = PaperNode(
            paper_id="2601.00001",
            title="Recent arXiv Paper",
            source="arxiv",
        )

        enriched, linked, citation_counts = enrich_paper_metadata(
            {paper.paper_id: paper}
        )

        self.assertEqual((enriched, linked, citation_counts), (0, 0, 0))
        self.assertFalse(paper.citation_count_known)
        self.assertEqual(paper.citation_count, 0)

    @patch("product_agent.research_agent.nodes.searcher.enrich_paper_metadata")
    @patch("product_agent.research_agent.nodes.searcher.search_papers", return_value=[])
    def test_balanced_mode_uses_one_bounded_metadata_enrichment(
        self,
        _search_arxiv,
        enrich_metadata,
    ) -> None:
        enrich_metadata.return_value = (1, 0, 1)
        state = {
            "topic": "AI agents",
            "mode": "balanced",
            "max_results": 3,
            "retrieval_plan": {
                "topic": "AI agents",
                "strict_queries": ["AI agents"],
                "broad_queries": [],
                "filters": {},
                "rerank_signals": [],
            },
            "paper_nodes": {
                "paper-a": PaperNode(
                    paper_id="paper-a",
                    title="A Real Paper",
                    source="arxiv",
                )
            },
        }

        result = searcher_node(state)

        enrich_metadata.assert_called_once()
        event = next(
            item
            for item in result["tool_events"]
            if item["tool_name"] == "Semantic Scholar citation enrichment"
        )
        self.assertIn("mode=balanced", event["note"])

    def test_analysis_selection_reserves_impact_and_recent_slots(self) -> None:
        papers = {}
        for index in range(10):
            paper = PaperNode(
                paper_id=f"paper-{index}",
                title=f"Tool Use Evaluation {index}",
                publish_date=str(2018 + index),
                source="arxiv",
                relevance_tier="direct",
                relevance_score=1.0 - index * 0.02,
                citation_count_known=True,
                citation_count=0,
            )
            papers[paper.paper_id] = paper
        papers["paper-8"].citation_count = 500

        selected = _select_papers_for_analysis(
            papers,
            state={"mode": "balanced"},
            max_results=8,
        )

        self.assertEqual(len(selected), 8)
        self.assertIn("paper-8", selected)
        self.assertIn("paper-9", selected)

    @patch("product_agent.research_agent.nodes.searcher.enrich_paper_metadata")
    @patch("product_agent.research_agent.nodes.searcher.search_papers")
    def test_citations_are_enriched_before_core_selection(
        self,
        search_arxiv,
        enrich_metadata,
    ) -> None:
        distinct_topics = [
            "Tool Selection Accuracy",
            "Function Calling Reliability",
            "Failure Recovery Protocols",
            "Trajectory Evaluation",
            "API Misuse Detection",
            "Runtime Mitigation",
            "Schema Validation",
            "Budgeted Tool Use",
            "Benchmark Impact Study",
            "Recent Recovery Dataset",
        ]
        search_arxiv.return_value = [
            PaperNode(
                paper_id=f"paper-{index}",
                title=f"{topic} for Language Agents",
                abstract="Tool use evaluation benchmark and failure recovery.",
                publish_date=str(2017 + index),
                source="arxiv",
                relevance_tier="direct",
                relevance_score=1.0 - index * 0.02,
            )
            for index, topic in enumerate(distinct_topics)
        ]

        def apply_metadata(shortlist, max_papers):
            self.assertGreater(len(shortlist), 8)
            shortlist["paper-8"].citation_count = 500
            shortlist["paper-8"].citation_count_known = True
            for paper in shortlist.values():
                if paper.paper_id != "paper-8":
                    paper.citation_count_known = True
            return len(shortlist), 0, len(shortlist)

        enrich_metadata.side_effect = apply_metadata
        result = searcher_node(
            {
                "topic": "AI agent tool use evaluation",
                "mode": "balanced",
                "max_results": 8,
                "retrieval_plan": {
                    "topic": "AI agent tool use evaluation",
                    "strict_queries": ["agent tool use evaluation"],
                    "broad_queries": [],
                    "recall_queries": [],
                    "filters": {},
                    "rerank_signals": ["tool use", "evaluation"],
                },
                "paper_nodes": {},
                "logs": [],
                "decisions": [],
                "tool_events": [],
                "error_events": [],
            }
        )

        self.assertIn("paper-8", result["paper_nodes"])


if __name__ == "__main__":
    unittest.main()
