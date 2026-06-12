from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Callable, Dict, Iterable

from product_agent.paper_content_tools import (
    FullTextDocument,
    FullTextUnavailableError,
    PaperResolution,
    PaperResolutionError,
    fetch_full_text,
    resolve_paper,
)
from product_agent.models import EvolutionEdge, PaperNode
from product_agent.services.relationship_evidence_service import (
    classify_relationship_sentence,
    normalize_evidence_text,
    source_aliases,
    split_evidence_sentences,
)


_PREFERRED_SECTIONS = (
    "related work",
    "background",
    "introduction",
    "method",
    "methodology",
    "approach",
    "experiment",
    "experiments",
    "evaluation",
    "result",
    "results",
    "discussion",
    "limitation",
    "limitations",
    "conclusion",
)
_RELATIONSHIP_CONFIDENCE = {
    "improvement": 0.97,
    "extension": 0.96,
    "comparison": 0.95,
}


@dataclass
class FullTextVerificationResult:
    edges: list[EvolutionEdge]
    attempted_edges: int = 0
    resolved_papers: int = 0
    parsed_documents: int = 0
    upgraded_edges: int = 0
    failures: int = 0


@dataclass(frozen=True)
class FullTextClaim:
    relationship: str
    section: str
    page: int
    sentence: str
    match_type: str = "direct_name"
    citation_label: str = ""
    reference_entry: str = ""


class FullTextRelationshipService:
    """Upgrade explicit citations using page-aware claims from target PDFs."""

    def __init__(
        self,
        *,
        resolver: Callable[[str], PaperResolution | None] = resolve_paper,
        fetcher: Callable[..., FullTextDocument] = fetch_full_text,
    ) -> None:
        self.resolver = resolver
        self.fetcher = fetcher

    def verify(
        self,
        papers: Dict[str, PaperNode],
        edges: Iterable[EvolutionEdge],
        *,
        max_edges: int,
        max_pages: int = 40,
    ) -> FullTextVerificationResult:
        edge_list = list(edges)
        if max_edges <= 0:
            return FullTextVerificationResult(edges=edge_list)

        candidates = [
            edge
            for edge in edge_list
            if self._is_candidate(papers, edge)
        ][:max_edges]
        if not candidates:
            return FullTextVerificationResult(edges=edge_list)

        resolutions: dict[str, PaperResolution | None] = {}
        documents: dict[str, FullTextDocument | None] = {}
        replacements: dict[tuple[str, str], EvolutionEdge] = {}
        result = FullTextVerificationResult(
            edges=edge_list,
            attempted_edges=len(candidates),
        )

        for edge in candidates:
            source = papers[edge.source]
            target = papers[edge.target]
            target_key = target.paper_id
            try:
                if target_key not in resolutions:
                    resolutions[target_key] = self.resolver(
                        _paper_resolution_input(target)
                    )
                    if resolutions[target_key] is not None:
                        result.resolved_papers += 1
                resolution = resolutions[target_key]
                if resolution is None or not resolution.pdf_url:
                    continue

                if target_key not in documents:
                    documents[target_key] = self.fetcher(
                        resolution,
                        max_pages=max_pages,
                    )
                    result.parsed_documents += 1
                document = documents[target_key]
                if document is None:
                    continue

                upgraded = self.verify_edge(
                    source,
                    target,
                    edge,
                    document=document,
                )
                if upgraded is not edge:
                    replacements[(edge.source, edge.target)] = upgraded
                    result.upgraded_edges += 1
            except (PaperResolutionError, FullTextUnavailableError, OSError, ValueError):
                result.failures += 1

        result.edges = [
            replacements.get((edge.source, edge.target), edge)
            for edge in edge_list
        ]
        return result

    def verify_edge(
        self,
        source: PaperNode,
        target: PaperNode,
        edge: EvolutionEdge,
        *,
        document: FullTextDocument,
    ) -> EvolutionEdge:
        evidence = _find_fulltext_claim(source, document)
        if evidence is None:
            return edge

        confidence = _RELATIONSHIP_CONFIDENCE[evidence.relationship]
        if evidence.match_type == "citation_marker":
            confidence -= 0.02
        explicit_reference = "explicit_reference" in str(edge.provenance or "")
        if not explicit_reference:
            confidence -= 0.07
        provenance = (
            "explicit_reference+fulltext_claim"
            if explicit_reference
            else "fulltext_claim"
        )
        detail = {
            "source_type": (
                "fulltext_citation"
                if evidence.match_type == "citation_marker"
                else "fulltext"
            ),
            "section": evidence.section,
            "page": evidence.page,
            "snippet": evidence.sentence,
            "source_url": document.source_url,
            "source_paper_id": source.paper_id,
            "target_paper_id": target.paper_id,
            "citation_label": evidence.citation_label,
            "reference_entry": evidence.reference_entry,
        }
        citation_note = (
            f" | ref {evidence.citation_label}"
            if evidence.citation_label
            else ""
        )
        snippet = (
            f"[Full text | {evidence.section} | p.{evidence.page}"
            f"{citation_note}] {evidence.sentence}"
        )
        return replace(
            edge,
            relationship=evidence.relationship,
            reasoning=(
                f"Verified as {evidence.relationship}: the target paper "
                + (
                    "uses a citation marker mapped to the source paper and states "
                    "the relationship in the same full-text sentence."
                    if evidence.match_type == "citation_marker"
                    else "directly names the source paper and states the relationship "
                    "in its full text."
                )
            ),
            weight=confidence,
            evidence="Direct relationship claim in target paper full text.",
            provenance=provenance,
            confidence=confidence,
            evidence_level="confirmed" if explicit_reference else "supported",
            evidence_snippets=[snippet],
            evidence_details=[detail],
        )

    @staticmethod
    def _is_candidate(
        papers: Dict[str, PaperNode],
        edge: EvolutionEdge,
    ) -> bool:
        source = papers.get(edge.source)
        target = papers.get(edge.target)
        if source is None or target is None:
            return False
        if edge.relationship != "citation":
            return False
        if "explicit_reference" not in str(edge.provenance or ""):
            return False
        if _is_fallback_paper(source) or _is_fallback_paper(target):
            return False
        if not _has_resolvable_identity(target):
            return False
        return bool(source_aliases(source))


def _paper_resolution_input(paper: PaperNode) -> str:
    if paper.doi:
        return paper.doi
    if (paper.source or "").lower() == "arxiv" and paper.paper_id:
        return paper.paper_id
    if "arxiv.org/" in str(paper.url or "").lower():
        return paper.url
    return paper.title


def _is_fallback_paper(paper: PaperNode) -> bool:
    return (paper.source or "").lower() in {"seed", "fallback"}


def _has_resolvable_identity(paper: PaperNode) -> bool:
    source = (paper.source or "").lower()
    if source in {"arxiv", "semantic_scholar", "openalex"}:
        return True
    if paper.doi:
        return True
    return "arxiv.org/" in str(paper.url or "").lower()


def _find_fulltext_claim(
    source: PaperNode,
    document: FullTextDocument,
) -> FullTextClaim | None:
    aliases = source_aliases(source)
    if not aliases:
        return None

    citation_entries = _reference_entries(document)
    citation_labels = _labels_for_source(aliases, citation_entries)
    sections = sorted(
        document.sections,
        key=lambda section: _section_priority(section.heading),
    )
    for section in sections:
        if _is_reference_heading(section.heading):
            continue
        for page, passage in _section_passages(document, section):
            for sentence in split_evidence_sentences(passage):
                normalized = normalize_evidence_text(sentence)
                if not any(alias in normalized for alias in aliases):
                    continue
                relationship = classify_relationship_sentence(sentence)
                if relationship:
                    return FullTextClaim(
                        relationship=relationship,
                        section=section.heading or "Unknown section",
                        page=page,
                        sentence=sentence.strip(),
                    )

            for sentence in split_evidence_sentences(passage):
                relationship = classify_relationship_sentence(sentence)
                if not relationship:
                    continue
                matched_label = _matched_citation_label(sentence, citation_labels)
                if not matched_label:
                    continue
                return FullTextClaim(
                    relationship=relationship,
                    section=section.heading or "Unknown section",
                    page=page,
                    sentence=sentence.strip(),
                    match_type="citation_marker",
                    citation_label=f"[{matched_label}]",
                    reference_entry=citation_entries[matched_label],
                )
    return None


def _section_priority(heading: str) -> tuple[int, str]:
    normalized = normalize_evidence_text(heading)
    for index, preferred in enumerate(_PREFERRED_SECTIONS):
        if preferred in normalized:
            return index, normalized
    return len(_PREFERRED_SECTIONS), normalized


def _reference_entries(document: FullTextDocument) -> dict[str, str]:
    entries: dict[str, str] = {}
    for section in document.sections:
        if not _is_reference_heading(section.heading):
            continue
        text = _join_wrapped_reference_lines(section.text)
        matches = list(
            re.finditer(
                r"(?m)^\s*(?:\[(?P<bracket>\d{1,4})\]|(?P<plain>\d{1,4})\.)\s+",
                text,
            )
        )
        for index, match in enumerate(matches):
            label = match.group("bracket") or match.group("plain") or ""
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            entry = " ".join(text[match.end():end].split()).strip()
            if label and entry:
                entries[label] = entry
    return entries


def _join_wrapped_reference_lines(text: str) -> str:
    dehyphenated = re.sub(
        r"(?<=[A-Za-z])-\s*\n\s*(?=[A-Za-z])",
        "",
        str(text or ""),
    )
    return dehyphenated


def _labels_for_source(
    aliases: set[str],
    entries: dict[str, str],
) -> set[str]:
    labels: set[str] = set()
    for label, entry in entries.items():
        normalized_entry = normalize_evidence_text(entry)
        if any(alias in normalized_entry for alias in aliases):
            labels.add(label)
    return labels


def _matched_citation_label(sentence: str, labels: set[str]) -> str:
    if not labels:
        return ""
    cited: set[str] = set()
    for marker in re.findall(r"\[([0-9,\s;\-–—]+)\]", sentence):
        cited.update(re.findall(r"\d{1,4}", marker))
    return next((label for label in sorted(labels) if label in cited), "")


def _section_passages(
    document: FullTextDocument,
    section,
) -> list[tuple[int, str]]:
    passages = [
        (page.page_number, page.text)
        for page in document.pages
        if section.start_page <= page.page_number <= section.end_page and page.text
    ]
    normalized_pages = normalize_evidence_text(
        " ".join(text for _, text in passages)
    )
    normalized_section = normalize_evidence_text(section.text)
    if normalized_section and normalized_section not in normalized_pages:
        passages.append((section.start_page, section.text))
    return passages or [(section.start_page, section.text)]


def _is_reference_heading(heading: str) -> bool:
    return normalize_evidence_text(heading) in {"references", "bibliography"}
