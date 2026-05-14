from __future__ import annotations

import os
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

from llm_client import call_openai_json
from observability import record_audit_event, record_decision, record_tool_event

from ..models import EvolutionEdge, PaperNode, ResearchState


OVERLAP_THRESHOLD = 0.40
LOW_CONFIDENCE_THRESHOLD = 0.45

IMPROVEMENT_TERMS = {
    "improve",
    "improved",
    "improves",
    "better",
    "enhance",
    "enhanced",
    "extend",
    "extends",
    "solve",
    "address",
}
EVALUATION_TERMS = {
    "experiment",
    "evaluation",
    "benchmark",
    "result",
    "results",
    "accuracy",
    "performance",
    "dataset",
}


@dataclass(frozen=True)
class TaxonomyBranch:
    name: str
    description: str
    required_concepts: Tuple[str, ...]


def auditor_node(state: ResearchState) -> ResearchState:
    """
    Audit the current analysis result and convert hidden quality issues into
    explicit reports and gaps.

    This implementation now lives inside `product_agent/research_agent/`,
    which means the new pipeline no longer depends on the legacy root-level
    `auditor.py` node wrapper.
    """

    papers = _normalize_papers(state.get("paper_nodes", {}))
    edges = _normalize_edges(state.get("evolution_graph", []))
    taxonomy = _normalize_taxonomy(state.get("expert_taxonomy", {}))

    _enrich_edge_reasoning(papers, edges)

    taxonomy_score, taxonomy_reports, taxonomy_gaps = _audit_taxonomy_alignment(papers, taxonomy)
    graph_score, graph_reports, graph_gaps = _audit_graph_logic(papers, edges)
    llm_reports, llm_gaps = _audit_edges_with_llm(papers, edges[:8])

    if os.environ.get("SKIP_AUDITOR_LLM") == "1":
        record_tool_event(
            state,
            tool_name="LLM edge auditor",
            input_summary=f"edges={len(edges[:8])}",
            status="skipped",
            note="Current mode skips LLM edge auditing.",
        )
    elif any(edge.relationship.lower() in {"improves", "extends", "solves"} for edge in edges[:8]):
        record_tool_event(
            state,
            tool_name="LLM edge auditor",
            input_summary=f"edges={len(edges[:8])}",
            status="success" if llm_reports or llm_gaps else "fallback",
            output_count=len(llm_reports) + len(llm_gaps),
            note="Semantic audit over improvement-style edges.",
        )

    reports = taxonomy_reports + graph_reports + llm_reports
    gaps = _dedupe(taxonomy_gaps + graph_gaps + llm_gaps)
    _mark_gap_candidates(papers, gaps)

    for gap in gaps[:20]:
        record_audit_event(
            state,
            event_type="gap_detected",
            summary=gap,
            severity="warning",
            recovery="Use the gap in Corrector or Synthesizer for follow-up analysis.",
        )

    alignment_score = round((taxonomy_score * 0.65) + (graph_score * 0.35), 3)
    record_audit_event(
        state,
        event_type="alignment_score",
        summary=f"taxonomy_score={taxonomy_score:.3f}, graph_score={graph_score:.3f}, final={alignment_score:.3f}",
        severity="info",
        recovery="Pass the result to Corrector for repair or acceptance.",
    )

    if not reports:
        reports = ["Audit passed: no obvious taxonomy or graph consistency issues were found."]

    updated = dict(state)
    updated["paper_nodes"] = papers
    updated["evolution_graph"] = edges
    updated["alignment_score"] = alignment_score
    updated["audit_reports"] = reports
    updated["detected_gaps"] = gaps

    record_decision(
        updated,
        stage="auditor",
        decision=f"Detected {len(gaps)} gaps with score {alignment_score}.",
        reason="Compare the paper graph against taxonomy coverage and graph consistency rules.",
        next_step="corrector",
    )
    updated.setdefault("logs", []).append(f"Auditor completed with alignment_score={alignment_score}.")
    return updated


def _audit_taxonomy_alignment(
    papers: Dict[str, PaperNode], taxonomy: List[TaxonomyBranch]
) -> Tuple[float, List[str], List[str]]:
    if not taxonomy:
        return 0.0, ["Taxonomy audit skipped because expert_taxonomy is empty."], [
            "Missing expert_taxonomy baseline."
        ]

    reports: List[str] = []
    gaps: List[str] = []
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
            reports.append(f"Branch '{branch.name}' has no matched paper nodes.")
            gaps.append(f"Missing taxonomy branch: {branch.name}.")
        if missing_concepts:
            joined = ", ".join(missing_concepts)
            reports.append(f"Branch '{branch.name}' lacks required concepts: {joined}.")
            gaps.append(f"Missing required concepts in '{branch.name}': {joined}.")

    if not papers:
        reports.append("No paper nodes are available for taxonomy coverage.")
        gaps.append("No paper_nodes available for audit.")

    return (sum(scores) / len(scores) if scores else 0.0), reports, gaps


def _audit_graph_logic(
    papers: Dict[str, PaperNode], edges: List[EvolutionEdge]
) -> Tuple[float, List[str], List[str]]:
    reports: List[str] = []
    gaps: List[str] = []
    if not edges:
        return 0.0, ["Evolution graph is empty."], ["No evolution_graph edges found."]

    total_checks = 0
    failed_checks = 0
    existing_pairs = {(edge.source, edge.target) for edge in edges}

    for edge in edges:
        total_checks += 1
        source = papers.get(edge.source)
        target = papers.get(edge.target)
        if source is None or target is None:
            failed_checks += 1
            reports.append(f"Edge {edge.source} -> {edge.target} references missing paper node(s).")
            gaps.append(f"Dangling edge: {edge.source} -> {edge.target}.")
            continue

        same_category = _canonical(source.taxonomy_category) == _canonical(target.taxonomy_category)
        overlap = _keyword_overlap(source, target)
        if not same_category and overlap < OVERLAP_THRESHOLD:
            failed_checks += 1
            reports.append(
                f"Edge {edge.source} -> {edge.target} crosses taxonomy categories with keyword overlap {overlap:.2f}."
            )
            gaps.append(f"Weak cross-category edge: {edge.source} -> {edge.target} overlap={overlap:.2f}.")

        relationship = edge.relationship.lower().strip()
        if relationship in {"improves", "improve", "extends", "solves"}:
            total_checks += 1
            evidence_text = _paper_search_text(target)
            has_claim = any(term in evidence_text for term in IMPROVEMENT_TERMS)
            has_eval = any(term in evidence_text for term in EVALUATION_TERMS)
            if not (has_claim and has_eval):
                failed_checks += 1
                reports.append(
                    f"Edge {edge.source} -> {edge.target} is marked as improvement but lacks clear evidence."
                )
                gaps.append(f"Unsupported improvement claim: {edge.source} -> {edge.target}.")

    for paper in papers.values():
        for ref_id in paper.references:
            if ref_id in papers and (ref_id, paper.paper_id) not in existing_pairs:
                total_checks += 1
                failed_checks += 1
                reports.append(f"Paper {paper.paper_id} references {ref_id}, but no graph edge exists.")
                gaps.append(f"Missing reference edge: {ref_id} -> {paper.paper_id}.")

        if paper.confidence_score and paper.confidence_score < LOW_CONFIDENCE_THRESHOLD:
            total_checks += 1
            failed_checks += 1
            reports.append(f"Paper {paper.paper_id} has low confidence_score={paper.confidence_score:.2f}.")
            gaps.append(f"Low-confidence paper node: {paper.paper_id}.")

    score = 1.0 - (failed_checks / total_checks) if total_checks else 0.0
    return max(0.0, min(1.0, score)), reports, gaps


def _audit_edges_with_llm(
    papers: Dict[str, PaperNode], edges: List[EvolutionEdge]
) -> Tuple[List[str], List[str]]:
    if os.environ.get("SKIP_AUDITOR_LLM") == "1":
        return [], []

    improves_edges = [edge for edge in edges if edge.relationship.lower() in {"improves", "extends", "solves"}]
    if not improves_edges:
        return [], []

    payload = []
    for edge in improves_edges[:5]:
        source = papers.get(edge.source)
        target = papers.get(edge.target)
        if source and target:
            payload.append(
                {
                    "source_id": edge.source,
                    "source_title": source.title,
                    "source_abstract": source.abstract[:1200],
                    "target_id": edge.target,
                    "target_title": target.title,
                    "target_abstract": target.abstract[:1200],
                    "relationship": edge.relationship,
                }
            )

    if not payload:
        return [], []

    data = call_openai_json(
        (
            "Audit whether the following paper evolution edges are actually supported by semantic evidence. "
            "Return JSON only in the format "
            '{"items":[{"edge":"source->target","supported":true,"reason":"...","gap":"..."}]}\n'
            f"{payload}"
        ),
        system=(
            "You are a research-logic auditor. Judge whether the target abstract truly supports the claimed "
            "relationship to the source paper, and return valid JSON only."
        ),
        max_output_tokens=1600,
    )
    if not data or not isinstance(data.get("items"), list):
        return [], []

    reports: List[str] = []
    gaps: List[str] = []
    for item in data["items"]:
        edge = str(item.get("edge", ""))
        reason = str(item.get("reason", "")).strip()
        supported = bool(item.get("supported", False))
        if reason:
            reports.append(f"LLM audit {edge}: {reason}")
        if not supported:
            gap = str(item.get("gap") or f"LLM found an unsupported evolution edge: {edge}.")
            gaps.append(gap)
    return reports, gaps


def _normalize_papers(raw: Any) -> Dict[str, PaperNode]:
    if isinstance(raw, Mapping):
        items = raw.items()
    else:
        items = ((getattr(item, "paper_id", str(index)), item) for index, item in enumerate(raw or []))

    papers = {}
    for key, value in items:
        if isinstance(value, PaperNode):
            paper = value
        else:
            payload = dict(value)
            payload.setdefault("paper_id", key)
            paper = PaperNode(**payload)
        papers[paper.paper_id] = paper
    return papers


def _normalize_edges(raw: Any) -> List[EvolutionEdge]:
    return [edge if isinstance(edge, EvolutionEdge) else EvolutionEdge(**dict(edge)) for edge in raw or []]


def _normalize_taxonomy(raw: Any) -> List[TaxonomyBranch]:
    if not raw:
        return []
    taxonomy = raw.get("taxonomy", raw) if isinstance(raw, Mapping) else raw
    branches: List[TaxonomyBranch] = []
    if isinstance(taxonomy, Mapping):
        for name, payload in taxonomy.items():
            payload = payload if isinstance(payload, Mapping) else {"description": str(payload)}
            branches.append(
                TaxonomyBranch(
                    name=str(name),
                    description=str(payload.get("description", "")),
                    required_concepts=tuple(str(x) for x in payload.get("required_concepts", [])),
                )
            )
    return branches


def _enrich_edge_reasoning(papers: Dict[str, PaperNode], edges: List[EvolutionEdge]) -> None:
    for edge in edges:
        if edge.reasoning:
            continue
        source = papers.get(edge.source)
        target = papers.get(edge.target)
        if not source or not target:
            continue
        edge.reasoning = (
            f"Audited as '{edge.relationship}' because source and target share taxonomy or keywords; "
            f"keyword_overlap={_keyword_overlap(source, target):.2f}."
        )


def _mark_gap_candidates(papers: Dict[str, PaperNode], gaps: Sequence[str]) -> None:
    gap_text = " ".join(gaps)
    for paper_id, paper in papers.items():
        if paper_id in gap_text:
            paper.is_gap_candidate = True


def _paper_search_text(paper: PaperNode) -> str:
    return _canonical(" ".join([paper.title, paper.abstract, paper.taxonomy_category, " ".join(paper.keywords)]))


def _keyword_overlap(left: PaperNode, right: PaperNode) -> float:
    left_words = set(left.keywords or re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", _paper_search_text(left)))
    right_words = set(right.keywords or re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", _paper_search_text(right)))
    if not left_words or not right_words:
        return 0.0
    return len(left_words & right_words) / len(left_words | right_words)


def _contains_phrase(text: str, phrase: str) -> bool:
    return bool(phrase) and _canonical(phrase) in text


def _canonical(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("_", " ").replace("-", " ").lower()).strip()


def _dedupe(items: Iterable[str]) -> List[str]:
    result: List[str] = []
    seen = set()
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result
