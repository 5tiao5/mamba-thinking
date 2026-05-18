from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Tuple

from product_agent.research_agent.models import PaperNode
from product_agent.schemas.audit import AuditGap, AuditReport, AuditResult

from .auditor import TaxonomyBranch, _canonical, _contains_phrase, _paper_search_text


class TaxonomyAuditService:
    """Taxonomy 对齐审计服务"""

    def audit(
        self, papers: Dict[str, PaperNode], taxonomy: List[TaxonomyBranch]
    ) -> AuditResult:
        if not taxonomy:
            return AuditResult(
                score=0.0,
                reports=[
                    AuditReport(
                        type="taxonomy",
                        severity="warning",
                        description="Taxonomy audit skipped because expert_taxonomy is empty.",
                        affected_items=[],
                        suggestion="Provide expert_taxonomy baseline.",
                    )
                ],
                gaps=[
                    AuditGap(
                        type="taxonomy",
                        severity="error",
                        description="Missing expert_taxonomy baseline.",
                        affected_items=[],
                        actionable=False,
                    )
                ],
            )

        reports: List[AuditReport] = []
        gaps: List[AuditGap] = []
        scores: List[float] = []
        paper_texts = {paper_id: _paper_search_text(paper) for paper_id, paper in papers.items()}
        category_index = defaultdict(list)

        for paper_id, paper in papers.items():
            if paper.taxonomy_category:
                category_index[_canonical(paper.taxonomy_category)].append(paper_id)

        for branch in taxonomy:
            category_key = _canonical(branch.name)
            direct_matches = category_index.get(category_key, [])
            semantic_matches = [
                paper_id
                for paper_id, text in paper_texts.items()
                if _contains_phrase(text, branch.name) or _contains_phrase(text, branch.description)
            ]
            matched_papers = sorted(set(direct_matches + semantic_matches))

            concept_hits = []
            missing_concepts = []
            for concept in branch.required_concepts:
                if any(_contains_phrase(text, concept) for text in paper_texts.values()):
                    concept_hits.append(concept)
                else:
                    missing_concepts.append(concept)

            concept_score = len(concept_hits) / len(branch.required_concepts) if branch.required_concepts else 1.0
            branch_score = (0.45 if matched_papers else 0.0) + (0.55 * concept_score)
            scores.append(branch_score)

            if not matched_papers:
                reports.append(
                    AuditReport(
                        type="taxonomy",
                        severity="warning",
                        description=f"Branch '{branch.name}' has no matched paper nodes.",
                        affected_items=[branch.name],
                        suggestion="Add papers covering this branch.",
                    )
                )
                gaps.append(
                    AuditGap(
                        type="taxonomy",
                        severity="error",
                        description=f"Missing taxonomy branch: {branch.name}.",
                        affected_items=[branch.name],
                        actionable=True,
                        related_papers=[],
                        suggestion="Search for papers in this category.",
                    )
                )
            if missing_concepts:
                joined = ", ".join(missing_concepts)
                reports.append(
                    AuditReport(
                        type="taxonomy",
                        severity="warning",
                        description=f"Branch '{branch.name}' lacks required concepts: {joined}.",
                        affected_items=[branch.name],
                        suggestion="Find papers covering these concepts.",
                    )
                )
                gaps.append(
                    AuditGap(
                        type="taxonomy",
                        severity="warning",
                        description=f"Missing required concepts in '{branch.name}': {joined}.",
                        affected_items=[branch.name],
                        actionable=True,
                        related_papers=matched_papers,
                        suggestion="Add papers with these concepts.",
                    )
                )

        if not papers:
            reports.append(
                AuditReport(
                    type="taxonomy",
                    severity="error",
                    description="No paper nodes are available for taxonomy coverage.",
                    affected_items=[],
                    suggestion="Ensure papers are loaded.",
                )
            )
            gaps.append(
                AuditGap(
                    type="taxonomy",
                    severity="error",
                    description="No paper_nodes available for audit.",
                    affected_items=[],
                    actionable=False,
                )
            )

        return AuditResult(
            score=sum(scores) / len(scores) if scores else 0.0,
            reports=reports,
            gaps=gaps,
        )