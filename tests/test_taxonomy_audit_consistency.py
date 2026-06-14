from __future__ import annotations

import unittest

from product_agent.models import PaperNode
from product_agent.research_agent.nodes.auditor import _attach_gap_evidence
from product_agent.schemas.audit import AuditGap
from product_agent.services.audit_common import TaxonomyBranch
from product_agent.services.evidence_snapshot_service import EvidenceSnapshotService
from product_agent.services.taxonomy_audit_service import TaxonomyAuditService


class TaxonomyAuditConsistencyTests(unittest.TestCase):
    def test_grounded_assignment_prevents_false_missing_branch_gap(self) -> None:
        paper = PaperNode(
            paper_id="paper-fusion",
            title="Sparse Shortcuts for Efficient Multimodal Models",
            abstract="A lightweight projector and sparse routing method.",
            expert_taxonomy_branches=["Multimodal Fusion Architectures"],
        )
        branch = TaxonomyBranch(
            name="Multimodal Fusion Architectures",
            description="Architectures for combining multiple modalities.",
            required_concepts=(),
        )

        result = TaxonomyAuditService().audit(
            {paper.paper_id: paper},
            [branch],
        )

        self.assertEqual(result.gaps, [])
        self.assertEqual(result.score, 1.0)

    def test_gap_evidence_uses_readable_related_paper_titles(self) -> None:
        paper = PaperNode(
            paper_id="paper-fusion",
            title="Sparse Shortcuts for Efficient Multimodal Models",
        )
        gap = AuditGap(
            type="taxonomy",
            severity="warning",
            description="Missing robustness evidence.",
            affected_items=["Multimodal Fusion Architectures"],
            related_papers=[paper.paper_id],
        )

        _attach_gap_evidence({paper.paper_id: paper}, [gap])

        self.assertEqual(
            gap.to_dict()["evidence"],
            ["Sparse Shortcuts for Efficient Multimodal Models (paper-fusion)"],
        )

    def test_required_concept_uses_scoped_token_coverage(self) -> None:
        paper = PaperNode(
            paper_id="paper-fusion",
            title="Sparse Shortcuts for Efficient Fusion in Multimodal Models",
            abstract="We introduce efficient routing for multimodal representations.",
            expert_taxonomy_branches=["Multimodal Fusion Architectures"],
        )
        branch = TaxonomyBranch(
            name="Multimodal Fusion Architectures",
            description="Architectures for combining multiple modalities.",
            required_concepts=("sparse fusion mechanisms",),
        )

        result = TaxonomyAuditService().audit(
            {paper.paper_id: paper},
            [branch],
        )

        self.assertEqual(result.gaps, [])
        self.assertEqual(result.score, 1.0)

    def test_required_concept_is_not_borrowed_from_another_branch(self) -> None:
        fusion_paper = PaperNode(
            paper_id="paper-fusion",
            title="Multimodal Fusion Architecture",
            abstract="A fusion architecture for multimodal inputs.",
            expert_taxonomy_branches=["Multimodal Fusion Architectures"],
        )
        unrelated_paper = PaperNode(
            paper_id="paper-robustness",
            title="Missing Modality Robustness",
            abstract="Robust inference when a modality is missing.",
            expert_taxonomy_branches=["Robust Multimodal Learning"],
        )
        branch = TaxonomyBranch(
            name="Multimodal Fusion Architectures",
            description="Architectures for combining multiple modalities.",
            required_concepts=("missing modality robustness",),
        )

        result = TaxonomyAuditService().audit(
            {
                fusion_paper.paper_id: fusion_paper,
                unrelated_paper.paper_id: unrelated_paper,
            },
            [branch],
        )

        self.assertEqual(len(result.gaps), 1)
        self.assertEqual(result.gaps[0].related_papers, [fusion_paper.paper_id])

    def test_required_concept_normalizes_mllm_and_llm_aliases(self) -> None:
        paper = PaperNode(
            paper_id="paper-translation",
            title="Image Translation with MLLM Prior Knowledge",
            abstract="Large multimodal models guide infrared-visible translation.",
            expert_taxonomy_branches=[
                "Image Translation and Fusion for Downstream Tasks"
            ],
        )
        branch = TaxonomyBranch(
            name="Image Translation and Fusion for Downstream Tasks",
            description="Multimodal image translation.",
            required_concepts=("LLM priors",),
        )

        result = TaxonomyAuditService().audit(
            {paper.paper_id: paper},
            [branch],
        )

        self.assertEqual(result.gaps, [])

    def test_snapshot_falls_back_to_related_papers_for_legacy_gaps(self) -> None:
        snapshot = EvidenceSnapshotService().build(
            topic="multimodal fusion",
            papers={},
            taxonomy={},
            edges=[],
            gaps=[
                {
                    "id": "gap-legacy",
                    "description": "Weak graph relation",
                    "related_papers": ["paper-a", "paper-b"],
                }
            ],
            retrieval_plan={},
            retrieval_outcome={},
            alignment_score=0.5,
            audit_reports=[],
        )

        self.assertEqual(
            snapshot["gaps"][0]["evidence"],
            ["paper-a", "paper-b"],
        )
        self.assertEqual(snapshot["stats"]["evidence_backed_gap_count"], 1)


if __name__ == "__main__":
    unittest.main()
