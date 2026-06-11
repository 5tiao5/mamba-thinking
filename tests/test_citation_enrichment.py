from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from product_agent.models import PaperNode
from product_agent.research_agent.nodes.searcher import searcher_node
from product_agent.tools import (
    _semantic_scholar_identifiers,
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

    @patch("product_agent.tools._fetch_s2_references")
    def test_cross_source_reference_maps_to_local_canonical_id(self, fetch_references) -> None:
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
        fetch_references.side_effect = [
            [],
            [{"s2": "other-s2-id", "arxiv": "2401.01234", "doi": ""}],
        ]

        enriched, linked = enrich_paper_references(
            {
                predecessor.paper_id: predecessor,
                successor.paper_id: successor,
            }
        )

        self.assertEqual(enriched, 1)
        self.assertEqual(linked, 1)
        self.assertEqual(successor.references, ["2401.01234"])

    @patch("product_agent.research_agent.nodes.searcher.enrich_paper_references")
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
        enrich_references.return_value = (1, 0)
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

    @patch("product_agent.research_agent.nodes.searcher.enrich_paper_references")
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


if __name__ == "__main__":
    unittest.main()
