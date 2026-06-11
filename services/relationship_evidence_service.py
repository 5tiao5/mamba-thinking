from __future__ import annotations

import re
from dataclasses import replace
from typing import Dict, Iterable

from product_agent.research_agent.models import EvolutionEdge, PaperNode


_IMPROVEMENT_TERMS = (
    "improve",
    "improved",
    "improves",
    "improvement",
    "outperform",
    "outperformed",
    "outperforms",
    "better than",
    "higher accuracy",
    "lower error",
    "more effective",
)
_EVALUATION_TERMS = (
    "accuracy",
    "benchmark",
    "evaluation",
    "experiment",
    "performance",
    "result",
    "score",
    "success rate",
)
_EXTENSION_TERMS = (
    "build on",
    "builds on",
    "building on",
    "build upon",
    "builds upon",
    "building upon",
    "extend",
    "extended",
    "extends",
    "extension",
    "generalize",
    "generalized",
    "generalizes",
    "adapt",
    "adapted",
    "adapts",
)
_COMPARISON_TERMS = (
    "compare",
    "compared",
    "compares",
    "comparison",
    "contrast",
    "contrasted",
    "versus",
    "against",
)
_STRONG_RELATIONSHIPS = {
    "improve",
    "improves",
    "improvement",
    "extend",
    "extends",
    "extension",
    "compare",
    "compares",
    "comparison",
    "solve",
    "solves",
}


class RelationshipEvidenceService:
    """Verify paper relationships against explicit metadata and abstract text.

    Candidate discovery and semantic verification are intentionally separate:
    taxonomy or keyword similarity may nominate a pair, but only direct textual
    evidence can upgrade it to comparison, extension, or improvement.
    """

    def verify(
        self,
        papers: Dict[str, PaperNode],
        edges: Iterable[EvolutionEdge],
    ) -> list[EvolutionEdge]:
        verified: list[EvolutionEdge] = []
        for edge in edges:
            source = papers.get(edge.source)
            target = papers.get(edge.target)
            if source is None or target is None:
                verified.append(edge)
                continue
            verified.append(self.verify_edge(source, target, edge))
        return verified

    def verify_edge(
        self,
        source: PaperNode,
        target: PaperNode,
        edge: EvolutionEdge,
    ) -> EvolutionEdge:
        explicit_reference = edge.provenance == "explicit_reference"
        evidence_sentence = _find_direct_evidence_sentence(source, target)
        relationship = _classify_sentence(evidence_sentence) if evidence_sentence else ""

        if relationship:
            confidence = {
                "improvement": 0.94 if explicit_reference else 0.86,
                "extension": 0.92 if explicit_reference else 0.84,
                "comparison": 0.9 if explicit_reference else 0.82,
            }[relationship]
            provenance = (
                "explicit_reference+abstract_claim"
                if explicit_reference
                else "abstract_claim"
            )
            return replace(
                edge,
                relationship=relationship,
                reasoning=(
                    f"Verified as {relationship}: the target paper directly names "
                    "the source paper and states the relationship in its abstract."
                ),
                weight=confidence,
                evidence="Direct relationship claim in target abstract.",
                provenance=provenance,
                confidence=confidence,
                evidence_level="confirmed" if explicit_reference else "supported",
                evidence_snippets=[evidence_sentence],
            )

        if explicit_reference:
            return replace(
                edge,
                relationship="citation",
                reasoning=(
                    "Explicit reference metadata confirms that the target cites the "
                    "source, but the available abstract does not justify a stronger "
                    "extension, improvement, or comparison claim."
                ),
                weight=1.0,
                evidence="Explicit reference metadata.",
                provenance="explicit_reference",
                confidence=1.0,
                evidence_level="confirmed",
            )

        if edge.relationship.lower().strip() in _STRONG_RELATIONSHIPS:
            downgraded_from = edge.relationship
            snippets = list(edge.evidence_snippets)
            snippets.append(
                f"Downgraded from {downgraded_from}: no direct source mention and relationship claim were found."
            )
            return replace(
                edge,
                relationship="related",
                reasoning=(
                    f"Downgraded from {downgraded_from}: current metadata supports "
                    "thematic relatedness only, not a direct evolution claim."
                ),
                weight=min(edge.weight or 0.49, 0.49),
                evidence="No direct relationship evidence was found in the available abstract.",
                confidence=min(edge.confidence or 0.49, 0.49),
                evidence_level="inferred",
                evidence_snippets=snippets,
            )

        return edge


def _find_direct_evidence_sentence(source: PaperNode, target: PaperNode) -> str:
    aliases = _source_aliases(source)
    if not aliases:
        return ""

    target_text = " ".join([target.title or "", target.abstract or ""]).strip()
    for sentence in _sentences(target_text):
        normalized = _normalize(sentence)
        if any(alias in normalized for alias in aliases):
            return sentence.strip()
    return ""


def _source_aliases(source: PaperNode) -> set[str]:
    aliases: set[str] = set()
    title = " ".join((source.title or "").split()).strip()
    normalized_title = _normalize(title)
    if len(normalized_title) >= 12:
        aliases.add(normalized_title)

    title_prefix = title.split(":", 1)[0].strip()
    normalized_prefix = _normalize(title_prefix)
    if 4 <= len(normalized_prefix) <= 60:
        aliases.add(normalized_prefix)

    for token in re.findall(r"[A-Za-z][A-Za-z0-9-]{3,}", title):
        if "-" in token or token.isupper() or any(char.isupper() for char in token[1:]):
            aliases.add(_normalize(token))

    for identifier in (source.paper_id, source.doi):
        normalized_identifier = _normalize(identifier)
        if len(normalized_identifier) >= 6:
            aliases.add(normalized_identifier)
    return aliases


def _classify_sentence(sentence: str) -> str:
    normalized = _normalize(sentence)
    if not normalized:
        return ""

    has_improvement = _contains_any(normalized, _IMPROVEMENT_TERMS)
    has_evaluation = _contains_any(normalized, _EVALUATION_TERMS)
    if has_improvement and has_evaluation:
        return "improvement"
    if _contains_any(normalized, _EXTENSION_TERMS):
        return "extension"
    if _contains_any(normalized, _COMPARISON_TERMS):
        return "comparison"
    return ""


def _sentences(text: str) -> list[str]:
    return [
        part.strip()
        for part in re.split(r"(?<=[.!?。！？])\s+", text)
        if part.strip()
    ]


def _contains_any(text: str, terms: Iterable[str]) -> bool:
    return any(term in text for term in terms)


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value).lower()).strip()
