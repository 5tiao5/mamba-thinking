from __future__ import annotations

import re
from dataclasses import replace
from typing import Dict, Iterable

from product_agent.models import EvolutionEdge, PaperNode


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

_PROBLEM_TERMS = (
    "failure mode",
    "fail when",
    "error propagation",
    "misuse",
    "wrong final answer",
    "challenge",
    "limitation",
    "lack of",
    "unreliable",
)
_STRONG_FAILURE_TERMS = (
    "failure mode",
    "fail when",
    "error propagation",
    "misuse",
    "wrong final answer",
)
_RESPONSE_TERMS = (
    "mitigation",
    "recovery",
    "recoverability",
    "diagnostic",
    "validation",
    "verification",
    "improve reliability",
    "improving tool calling reliability",
    "improving generalization",
    "robust",
)
_BENCHMARK_TERMS = (
    "benchmark",
    "dataset",
    "evaluation",
    "evaluate",
)
_METHOD_TERMS = (
    "framework",
    "method",
    "approach",
    "scaffold",
    "optimization",
    "schema",
    "policy",
)
_ANALYSIS_TERMS = (
    "analyze",
    "analysis",
    "investigate",
    "characterize",
    "quantify",
)
_DIMENSION_TERMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("trajectory-level behavior", ("trajectory", "execution trace", "agent trace")),
    ("multi-turn state", ("multi-turn", "stateful", "final state")),
    ("failure recovery", ("failure recovery", "recoverability", "recovery policy", "self-recovery")),
    ("judge reliability", ("judge reliability", "human annotation", "human-validated", "kappa")),
    ("runtime error propagation", ("error propagation", "runtime mitigation", "propagates to")),
    ("tool selection", ("tool selection", "tool mis-selection", "candidate tool")),
    ("interface validation", ("schema", "structured diagnostics", "tool contract")),
    ("execution provenance", ("provenance", "evidence tracing", "audit")),
    ("efficiency and budgets", ("budget", "efficiency", "cost", "latency")),
    ("cross-domain generalization", ("generalization", "across domains", "multi-domain")),
)


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

    def infer_landscape_edge(
        self,
        source: PaperNode,
        target: PaperNode,
    ) -> EvolutionEdge | None:
        """Infer a useful research-landscape relation from both abstracts.

        These relations describe analytical progression across the selected
        evidence set. They are deliberately marked inferred and never claim
        that the target cites or historically builds on the source.
        """

        source_profile = _paper_profile(source)
        target_profile = _paper_profile(target)
        shared_dimensions = source_profile["dimensions"] & target_profile["dimensions"]
        added_dimensions = target_profile["dimensions"] - source_profile["dimensions"]

        if (
            source_profile["strong_failure"]
            and "analysis" in source_profile["roles"]
            and target_profile["response"]
            and "method" in target_profile["roles"]
            and (shared_dimensions or _shared_tool_context(source, target))
        ):
            return EvolutionEdge(
                source=source.paper_id,
                target=target.paper_id,
                relationship="addresses",
                reasoning=(
                    "Landscape inference: the source characterizes a tool-use "
                    "failure or reliability problem, while the later paper proposes "
                    "a recovery, mitigation, validation, or robustness response."
                ),
                weight=0.72,
                evidence="Complementary problem and response signals in both abstracts.",
                provenance="landscape_profile",
                confidence=0.72,
                evidence_level="inferred",
                evidence_snippets=[
                    f"source_problem_signals={', '.join(source_profile['problem'])}",
                    f"target_response_signals={', '.join(target_profile['response'])}",
                    f"shared_dimensions={', '.join(sorted(shared_dimensions)) or 'tool-use reliability'}",
                ],
            )

        if (
            source_profile["benchmark"]
            and target_profile["benchmark"]
            and added_dimensions
            and (shared_dimensions or _shared_tool_context(source, target))
        ):
            return EvolutionEdge(
                source=source.paper_id,
                target=target.paper_id,
                relationship="scope_extension",
                reasoning=(
                    "Landscape inference: both papers evaluate tool-using agents, "
                    "and the later paper adds evaluation dimensions not visible in "
                    "the earlier paper's abstract."
                ),
                weight=0.68,
                evidence="Evaluation-dimension profiles extracted from both abstracts.",
                provenance="landscape_profile",
                confidence=0.68,
                evidence_level="inferred",
                evidence_snippets=[
                    f"shared_dimensions={', '.join(sorted(shared_dimensions)) or 'general tool-use evaluation'}",
                    f"target_added_dimensions={', '.join(sorted(added_dimensions))}",
                ],
            )

        if (
            source_profile["roles"] != target_profile["roles"]
            and source_profile["roles"]
            and target_profile["roles"]
            and (shared_dimensions or _shared_tool_context(source, target))
        ):
            return EvolutionEdge(
                source=source.paper_id,
                target=target.paper_id,
                relationship="complements",
                reasoning=(
                    "Landscape inference: the papers address the same research "
                    "area from different roles, such as benchmark, analysis, method, "
                    "or provenance."
                ),
                weight=0.58,
                evidence="Distinct contribution roles with shared tool-use context.",
                provenance="landscape_profile",
                confidence=0.58,
                evidence_level="inferred",
                evidence_snippets=[
                    f"source_roles={', '.join(sorted(source_profile['roles']))}",
                    f"target_roles={', '.join(sorted(target_profile['roles']))}",
                    f"shared_dimensions={', '.join(sorted(shared_dimensions)) or 'tool-use agents'}",
                ],
            )
        return None

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


def _paper_profile(paper: PaperNode) -> dict[str, set[str] | list[str] | bool]:
    text = _normalize(" ".join([paper.title or "", paper.abstract or ""]))
    problem = [term for term in _PROBLEM_TERMS if term in text]
    strong_failure = [term for term in _STRONG_FAILURE_TERMS if term in text]
    response = [term for term in _RESPONSE_TERMS if term in text]
    dimensions = {
        label
        for label, terms in _DIMENSION_TERMS
        if any(term in text for term in terms)
    }
    roles: set[str] = set()
    if _contains_any(text, _BENCHMARK_TERMS):
        roles.add("benchmark")
    if _contains_any(text, _METHOD_TERMS):
        roles.add("method")
    if _contains_any(text, _ANALYSIS_TERMS):
        roles.add("analysis")
    if "provenance" in text or "evidence tracing" in text or "audit" in text:
        roles.add("provenance")
    return {
        "problem": problem,
        "strong_failure": strong_failure,
        "response": response,
        "dimensions": dimensions,
        "roles": roles,
        "benchmark": "benchmark" in roles,
    }


def _shared_tool_context(source: PaperNode, target: PaperNode) -> bool:
    source_text = _normalize(" ".join([source.title or "", source.abstract or ""]))
    target_text = _normalize(" ".join([target.title or "", target.abstract or ""]))
    context_terms = ("tool use", "tool calling", "tool using", "language agent", "llm agent")
    return any(term in source_text and term in target_text for term in context_terms)


def source_aliases(source: PaperNode) -> set[str]:
    """Return normalized identifiers that may directly name a source paper."""
    return _source_aliases(source)


def classify_relationship_sentence(sentence: str) -> str:
    """Classify one direct paper-relationship claim."""
    return _classify_sentence(sentence)


def split_evidence_sentences(text: str) -> list[str]:
    """Split abstract or full-text evidence into candidate sentences."""
    return _sentences(text)


def normalize_evidence_text(value: str) -> str:
    """Normalize evidence text for conservative alias matching."""
    return _normalize(value)
