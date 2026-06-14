from __future__ import annotations

import math
import re
from collections import defaultdict
from typing import Dict, List

from product_agent.research_agent.models import PaperNode
from product_agent.schemas.audit import AuditGap, AuditReport, AuditResult

from .audit_common import TaxonomyBranch, canonical, contains_phrase, paper_search_text


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
        paper_texts = {paper_id: paper_search_text(paper) for paper_id, paper in papers.items()}
        category_index = defaultdict(list)

        for paper_id, paper in papers.items():
            if paper.taxonomy_category:
                category_index[canonical(paper.taxonomy_category)].append(paper_id)

        for branch in taxonomy:
            category_key = canonical(branch.name)
            direct_matches = category_index.get(category_key, [])
            grounded_matches = [
                paper_id
                for paper_id, paper in papers.items()
                if any(
                    canonical(assigned_branch) == category_key
                    for assigned_branch in getattr(
                        paper, "expert_taxonomy_branches", []
                    )
                )
            ]
            semantic_matches = [
                paper_id
                for paper_id, text in paper_texts.items()
                if contains_phrase(text, branch.name) or contains_phrase(text, branch.description)
            ]
            matched_papers = sorted(
                set(direct_matches + grounded_matches + semantic_matches)
            )

            concept_hits = []
            missing_concepts = []
            concept_texts = [
                paper_texts[paper_id]
                for paper_id in matched_papers
                if paper_id in paper_texts
            ]
            for concept in branch.required_concepts:
                if any(
                    self._supports_concept(text, concept)
                    for text in concept_texts
                ):
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
                        description=f"研究方向“{branch.name}”当前没有匹配到论文证据。",
                        affected_items=[branch.name],
                        suggestion="继续补充覆盖该研究方向的代表性论文或综述。",
                    )
                )
                gaps.append(
                    AuditGap(
                        type="taxonomy",
                        severity="error",
                        description=f"当前证据尚未覆盖研究方向“{branch.name}”。",
                        affected_items=[branch.name],
                        actionable=True,
                        related_papers=[],
                        suggestion="优先检索该方向的代表性论文、综述或 benchmark 工作。",
                    )
                )
            if missing_concepts:
                joined = ", ".join(missing_concepts)
                reports.append(
                    AuditReport(
                        type="taxonomy",
                        severity="warning",
                        description=f"研究方向“{branch.name}”还缺少关键概念：{joined}。",
                        affected_items=[branch.name],
                        suggestion="补充能够覆盖这些关键概念的论文证据。",
                    )
                )
                gaps.append(
                    AuditGap(
                        type="taxonomy",
                        severity="warning",
                        description=f"方向“{branch.name}”缺少关键概念：{joined}。",
                        affected_items=[branch.name],
                        actionable=True,
                        related_papers=matched_papers,
                        suggestion="优先补充讨论这些概念的方法、评测或案例论文。",
                    )
                )

        if not papers:
            reports.append(
                AuditReport(
                    type="taxonomy",
                    severity="error",
                    description="当前没有可用于 taxonomy 覆盖分析的论文节点。",
                    affected_items=[],
                    suggestion="请先完成论文检索或导入相关知识后再进行分析。",
                )
            )
            gaps.append(
                AuditGap(
                    type="taxonomy",
                    severity="error",
                    description="当前没有可用于审计的论文证据。",
                    affected_items=[],
                    actionable=False,
                )
            )

        return AuditResult(
            score=sum(scores) / len(scores) if scores else 0.0,
            reports=reports,
            gaps=gaps,
        )

    @staticmethod
    def _supports_concept(text: str, concept: str) -> bool:
        if contains_phrase(text, concept):
            return True

        concept_tokens = TaxonomyAuditService._concept_tokens(concept)
        if not concept_tokens:
            return False
        text_tokens = TaxonomyAuditService._concept_tokens(text)
        shared_count = len(concept_tokens & text_tokens)
        required_count = 1 if len(concept_tokens) == 1 else max(
            2, math.ceil(len(concept_tokens) * 0.66)
        )
        return shared_count >= required_count

    @staticmethod
    def _concept_tokens(value: str) -> set[str]:
        generic = {
            "and",
            "for",
            "from",
            "with",
            "via",
            "the",
            "based",
            "method",
            "methods",
            "approach",
            "approaches",
        }
        tokens = set()
        for token in re.findall(r"[a-zA-Z][a-zA-Z0-9]{1,}", canonical(value)):
            normalized = token[:-1] if len(token) > 4 and token.endswith("s") else token
            if normalized in {"mllm", "mllms"}:
                normalized = "llm"
            if len(normalized) >= 3 and normalized not in generic:
                tokens.add(normalized)
        return tokens
