from __future__ import annotations

import unittest
from unittest.mock import patch

from product_agent.models import EvolutionEdge, PaperNode
from product_agent.paper_content_tools import (
    FullTextDocument,
    FullTextPage,
    FullTextSection,
    PaperResolution,
)
from product_agent.research_agent.nodes.evolution import evolution_node
from product_agent.services.fulltext_relationship_service import (
    FullTextRelationshipService,
    FullTextVerificationResult,
)
from product_agent.services.graph_audit_service import GraphAuditService
from product_agent.services.workspace_mapper import _map_graph_edge


def _paper(
    paper_id: str,
    title: str,
    *,
    source: str = "arxiv",
    references: list[str] | None = None,
) -> PaperNode:
    return PaperNode(
        paper_id=paper_id,
        title=title,
        source=source,
        publish_date="2025",
        references=references or [],
    )


def _document(*sections: FullTextSection) -> FullTextDocument:
    return FullTextDocument(
        source_url="https://arxiv.org/pdf/2501.01234.pdf",
        pages=[FullTextPage(page_number=1, text="paper text")],
        sections=list(sections),
        parser="test",
    )


class FullTextRelationshipTests(unittest.TestCase):
    def test_explicit_citation_upgrades_from_fulltext_extension_claim(self) -> None:
        source = _paper("2401.00001", "AgentBench")
        target = _paper(
            "2501.01234",
            "AgentBench for Multimodal Tasks",
            references=[source.paper_id],
        )
        edge = EvolutionEdge(
            source=source.paper_id,
            target=target.paper_id,
            relationship="citation",
            provenance="explicit_reference",
            confidence=1.0,
            evidence_level="confirmed",
        )
        resolver_calls: list[str] = []

        def resolver(reference: str) -> PaperResolution:
            resolver_calls.append(reference)
            return PaperResolution(
                paper_id=target.paper_id,
                title=target.title,
                source="arxiv",
                pdf_url="https://arxiv.org/pdf/2501.01234.pdf",
            )

        service = FullTextRelationshipService(
            resolver=resolver,
            fetcher=lambda resolution, max_pages: _document(
                FullTextSection(
                    heading="Related Work",
                    start_page=3,
                    end_page=3,
                    text=(
                        "Building on AgentBench, we extend the benchmark to "
                        "multimodal tool-use tasks."
                    ),
                )
            ),
        )

        result = service.verify(
            {source.paper_id: source, target.paper_id: target},
            [edge],
            max_edges=1,
        )

        upgraded = result.edges[0]
        self.assertEqual(resolver_calls, [target.paper_id])
        self.assertEqual(upgraded.relationship, "extension")
        self.assertEqual(
            upgraded.provenance,
            "explicit_reference+fulltext_claim",
        )
        self.assertEqual(upgraded.evidence_level, "confirmed")
        self.assertEqual(upgraded.evidence_details[0]["section"], "Related Work")
        self.assertEqual(upgraded.evidence_details[0]["page"], 3)
        self.assertIn("p.3", upgraded.evidence_snippets[0])
        self.assertEqual(result.upgraded_edges, 1)

    def test_bibliography_title_alone_does_not_create_strong_relation(self) -> None:
        source = _paper("2401.00001", "AgentBench")
        target = _paper(
            "2501.01234",
            "A New Benchmark",
            references=[source.paper_id],
        )
        edge = EvolutionEdge(
            source=source.paper_id,
            target=target.paper_id,
            relationship="citation",
            provenance="explicit_reference",
        )
        service = FullTextRelationshipService(
            resolver=lambda reference: PaperResolution(
                paper_id=target.paper_id,
                title=target.title,
                source="arxiv",
                pdf_url="https://arxiv.org/pdf/2501.01234.pdf",
            ),
            fetcher=lambda resolution, max_pages: _document(
                FullTextSection(
                    heading="References",
                    start_page=12,
                    end_page=12,
                    text="AgentBench. A benchmark for language agents.",
                )
            ),
        )

        result = service.verify(
            {source.paper_id: source, target.paper_id: target},
            [edge],
            max_edges=1,
        )

        self.assertEqual(result.edges[0].relationship, "citation")
        self.assertEqual(result.upgraded_edges, 0)

    def test_numbered_citation_is_mapped_back_to_source_paper(self) -> None:
        source = _paper(
            "2401.00001",
            "AgentBench: Evaluating LLMs as Agents",
        )
        target = _paper(
            "2501.01234",
            "A New Agent Evaluation",
            references=[source.paper_id],
        )
        edge = EvolutionEdge(
            source=source.paper_id,
            target=target.paper_id,
            relationship="citation",
            provenance="explicit_reference",
        )
        service = FullTextRelationshipService(
            resolver=lambda reference: PaperResolution(
                paper_id=target.paper_id,
                title=target.title,
                source="arxiv",
                pdf_url="https://arxiv.org/pdf/2501.01234.pdf",
            ),
            fetcher=lambda resolution, max_pages: _document(
                FullTextSection(
                    heading="Related Work",
                    start_page=2,
                    end_page=2,
                    text=(
                        "Building on the established agent benchmark [12], "
                        "we extend evaluation to multi-turn recovery."
                    ),
                ),
                FullTextSection(
                    heading="References",
                    start_page=11,
                    end_page=11,
                    text=(
                        "[11] Other Authors. An unrelated benchmark.\n"
                        "[12] Liu et al. AgentBench: Evaluating LLMs as\n"
                        "Agents. 2023.\n"
                        "[13] Other Authors. Another paper."
                    ),
                ),
            ),
        )

        result = service.verify(
            {source.paper_id: source, target.paper_id: target},
            [edge],
            max_edges=1,
        )

        upgraded = result.edges[0]
        self.assertEqual(upgraded.relationship, "extension")
        self.assertEqual(
            upgraded.evidence_details[0]["source_type"],
            "fulltext_citation",
        )
        self.assertEqual(upgraded.evidence_details[0]["citation_label"], "[12]")
        self.assertIn(
            "AgentBench: Evaluating LLMs as Agents",
            upgraded.evidence_details[0]["reference_entry"],
        )
        self.assertIn("ref [12]", upgraded.evidence_snippets[0])

    def test_claim_uses_actual_page_when_section_spans_multiple_pages(self) -> None:
        source = _paper("2401.00001", "AgentBench")
        target = _paper("2501.01234", "Agent Evaluation", references=[source.paper_id])
        edge = EvolutionEdge(
            source=source.paper_id,
            target=target.paper_id,
            relationship="citation",
            provenance="explicit_reference",
        )
        document = FullTextDocument(
            source_url="https://example.org/paper.pdf",
            pages=[
                FullTextPage(page_number=3, text="Related Work\nPrior studies exist."),
                FullTextPage(
                    page_number=4,
                    text="Building on AgentBench, we extend evaluation to recovery.",
                ),
            ],
            sections=[
                FullTextSection(
                    heading="Related Work",
                    start_page=3,
                    end_page=4,
                    text=(
                        "Prior studies exist. Building on AgentBench, "
                        "we extend evaluation to recovery."
                    ),
                )
            ],
            parser="test",
        )
        service = FullTextRelationshipService()

        upgraded = service.verify_edge(
            source,
            target,
            edge,
            document=document,
        )

        self.assertEqual(upgraded.evidence_details[0]["page"], 4)

    def test_unmapped_numbered_citation_does_not_upgrade_edge(self) -> None:
        source = _paper("2401.00001", "AgentBench")
        target = _paper(
            "2501.01234",
            "A New Agent Evaluation",
            references=[source.paper_id],
        )
        edge = EvolutionEdge(
            source=source.paper_id,
            target=target.paper_id,
            relationship="citation",
            provenance="explicit_reference",
        )
        service = FullTextRelationshipService(
            resolver=lambda reference: PaperResolution(
                paper_id=target.paper_id,
                title=target.title,
                source="arxiv",
                pdf_url="https://arxiv.org/pdf/2501.01234.pdf",
            ),
            fetcher=lambda resolution, max_pages: _document(
                FullTextSection(
                    heading="Related Work",
                    start_page=2,
                    end_page=2,
                    text="Building on prior work [12], we extend the benchmark.",
                ),
                FullTextSection(
                    heading="References",
                    start_page=11,
                    end_page=11,
                    text="[12] Other Authors. A different benchmark.",
                ),
            ),
        )

        result = service.verify(
            {source.paper_id: source, target.paper_id: target},
            [edge],
            max_edges=1,
        )

        self.assertEqual(result.edges[0].relationship, "citation")
        self.assertEqual(result.upgraded_edges, 0)

    def test_one_target_pdf_is_reused_for_multiple_candidate_edges(self) -> None:
        first = _paper("2401.00001", "AgentBench")
        second = _paper("2402.00002", "ToolBench")
        target = _paper(
            "2501.01234",
            "Unified Agent Evaluation",
            references=[first.paper_id, second.paper_id],
        )
        edges = [
            EvolutionEdge(
                source=source.paper_id,
                target=target.paper_id,
                relationship="citation",
                provenance="explicit_reference",
            )
            for source in (first, second)
        ]
        fetch_calls = 0

        def fetcher(resolution, max_pages):
            nonlocal fetch_calls
            fetch_calls += 1
            return _document(
                FullTextSection(
                    heading="Evaluation",
                    start_page=5,
                    end_page=5,
                    text=(
                        "We compare our protocol against AgentBench. "
                        "We also compare against ToolBench."
                    ),
                )
            )

        service = FullTextRelationshipService(
            resolver=lambda reference: PaperResolution(
                paper_id=target.paper_id,
                title=target.title,
                source="arxiv",
                pdf_url="https://arxiv.org/pdf/2501.01234.pdf",
            ),
            fetcher=fetcher,
        )
        result = service.verify(
            {
                first.paper_id: first,
                second.paper_id: second,
                target.paper_id: target,
            },
            edges,
            max_edges=2,
        )

        self.assertEqual(fetch_calls, 1)
        self.assertEqual(result.parsed_documents, 1)
        self.assertEqual(
            [edge.relationship for edge in result.edges],
            ["comparison", "comparison"],
        )

    @patch(
        "product_agent.research_agent.nodes.evolution.FullTextRelationshipService.verify"
    )
    def test_balanced_evolution_limits_fulltext_verification_to_one_edge(
        self,
        verify,
    ) -> None:
        source = _paper("2401.00001", "AgentBench")
        target = _paper(
            "2501.01234",
            "AgentBench Extension",
            references=[source.paper_id],
        )
        verify.side_effect = lambda papers, edges, max_edges: FullTextVerificationResult(
            edges=list(edges),
            attempted_edges=1,
        )

        state = evolution_node(
            {
                "topic": "agent evaluation",
                "mode": "balanced",
                "paper_nodes": {
                    source.paper_id: source,
                    target.paper_id: target,
                },
            }
        )

        self.assertEqual(verify.call_args.kwargs["max_edges"], 1)
        tool_event = state["tool_events"][-1]
        self.assertEqual(
            tool_event["tool_name"],
            "Open Full-text Relationship Verifier",
        )

    def test_fulltext_evidence_survives_mapping_and_graph_audit(self) -> None:
        source = _paper("2401.00001", "AgentBench")
        target = _paper("2501.01234", "AgentBench Extension")
        edge = EvolutionEdge(
            source=source.paper_id,
            target=target.paper_id,
            relationship="extension",
            provenance="explicit_reference+fulltext_claim",
            confidence=0.96,
            evidence_level="confirmed",
            evidence_snippets=[
                "[Full text | Method | p.4] Building on AgentBench, we extend it."
            ],
            evidence_details=[
                {
                    "source_type": "fulltext",
                    "section": "Method",
                    "page": 4,
                    "snippet": "Building on AgentBench, we extend it.",
                    "source_url": "https://example.org/paper.pdf",
                }
            ],
        )

        mapped = _map_graph_edge(edge, set())
        audit = GraphAuditService().audit(
            {source.paper_id: source, target.paper_id: target},
            [edge],
        )

        self.assertEqual(mapped["evidence_details"][0]["page"], 4)
        self.assertEqual(audit.gaps, [])
        self.assertEqual(audit.score, 1.0)


if __name__ == "__main__":
    unittest.main()
