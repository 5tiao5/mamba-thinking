from __future__ import annotations

import re
from typing import Any


def audit_evidence_coverage(
    *,
    focus_facets: list[dict[str, Any]],
    papers: dict[str, Any],
) -> dict[str, Any]:
    """Measure whether retrieved papers support each required focus facet."""

    entries: list[dict[str, Any]] = []
    missing: list[str] = []
    weak: list[str] = []
    unevaluable: list[str] = []

    for facet in focus_facets:
        if not isinstance(facet, dict) or not bool(facet.get("required", True)):
            continue
        label = " ".join(str(facet.get("label", "")).split()).strip()
        if not label:
            continue
        terms = _facet_evidence_terms(facet)
        matches = _facet_paper_matches(terms=terms, papers=papers)
        direct_count = sum(1 for match in matches if match["match_type"] == "direct")
        adjacent_count = sum(1 for match in matches if match["match_type"] == "adjacent")

        if not terms:
            evidence_level = "not_evaluable"
            unevaluable.append(label)
        elif direct_count >= 2:
            evidence_level = "strong"
        elif direct_count == 1:
            evidence_level = "supported"
        elif adjacent_count:
            evidence_level = "adjacent_only"
            weak.append(label)
        else:
            evidence_level = "missing"
            missing.append(label)

        entries.append(
            {
                "label": label,
                "required": True,
                "evidence_level": evidence_level,
                "direct_paper_count": direct_count,
                "adjacent_paper_count": adjacent_count,
                "matched_paper_count": len(matches),
                "matched_papers": matches[:6],
                "search_terms": terms,
            }
        )

    required_count = len(entries)
    supported_count = sum(
        1
        for entry in entries
        if entry["evidence_level"] in {"strong", "supported"}
    )
    if required_count == 0:
        status = "not_required"
    elif len(unevaluable) == required_count:
        status = "not_evaluable"
    elif supported_count == required_count:
        status = "covered"
    elif supported_count or weak:
        status = "partial"
    else:
        status = "uncovered"
    return {
        "status": status,
        "required_count": required_count,
        "supported_count": supported_count,
        "missing_count": len(missing),
        "weak_count": len(weak),
        "unevaluable_count": len(unevaluable),
        "missing_facets": missing,
        "weak_facets": weak,
        "unevaluable_facets": unevaluable,
        "facets": entries,
    }


def audit_query_coverage(
    *,
    focus_facets: list[dict[str, Any]],
    scheduled_queries: list[str],
) -> dict[str, Any]:
    """Map every required focus facet to queries that will actually run."""

    normalized_queries = [
        (query, _normalize(query))
        for query in scheduled_queries
        if str(query).strip()
    ]
    entries: list[dict[str, Any]] = []
    uncovered: list[str] = []

    for facet in focus_facets:
        if not isinstance(facet, dict) or not bool(facet.get("required", True)):
            continue
        label = " ".join(str(facet.get("label", "")).split()).strip()
        if not label:
            continue
        candidates = [
            *list(facet.get("query_candidates", []) or []),
            *list(facet.get("search_terms", []) or []),
        ]
        matched_queries = _matching_queries(
            candidates=candidates,
            normalized_queries=normalized_queries,
        )
        covered = bool(matched_queries)
        if not covered:
            uncovered.append(label)
        entries.append(
            {
                "label": label,
                "required": True,
                "covered": covered,
                "matched_queries": matched_queries,
                "reason": (
                    "scheduled_query_match"
                    if covered
                    else "no_executable_query"
                ),
            }
        )

    required_count = len(entries)
    covered_count = required_count - len(uncovered)
    if required_count == 0:
        status = "not_required"
    elif not uncovered:
        status = "covered"
    elif covered_count == 0:
        status = "uncovered"
    else:
        status = "partial"
    return {
        "status": status,
        "required_count": required_count,
        "covered_count": covered_count,
        "uncovered_count": len(uncovered),
        "uncovered_facets": uncovered,
        "facets": entries,
    }


def required_facet_queries(focus_facets: list[dict[str, Any]]) -> list[str]:
    """Return one executable query per required facet, preserving user order."""

    queries: list[str] = []
    seen: set[str] = set()
    for facet in focus_facets:
        if not isinstance(facet, dict) or not bool(facet.get("required", True)):
            continue
        candidates = list(facet.get("query_candidates", []) or [])
        for candidate in candidates:
            query = " ".join(str(candidate).split()).strip()
            key = query.casefold()
            if not query or key in seen:
                continue
            seen.add(key)
            queries.append(query)
            break
    return queries


def facet_rescue_queries(
    *,
    focus_facets: list[dict[str, Any]],
    evidence_coverage: dict[str, Any],
    attempted_queries: list[str],
    topic_anchor: str = "",
) -> list[dict[str, str]]:
    """Build one topic-grounded rescue query per weak or missing facet."""

    rescue_labels = {
        *list(evidence_coverage.get("missing_facets", []) or []),
        *list(evidence_coverage.get("weak_facets", []) or []),
    }
    attempted = {_normalize(query) for query in attempted_queries}
    rescue_queries: list[dict[str, str]] = []

    for facet in focus_facets:
        if not isinstance(facet, dict):
            continue
        label = " ".join(str(facet.get("label", "")).split()).strip()
        if label not in rescue_labels:
            continue
        candidates = [
            *list(facet.get("search_terms", []) or [])[1:],
            *list(facet.get("search_terms", []) or [])[:1],
            *list(facet.get("query_candidates", []) or []),
        ]
        for candidate in candidates:
            query = _anchor_query(candidate, topic_anchor)
            normalized = _normalize(query)
            if not normalized or normalized in attempted:
                continue
            attempted.add(normalized)
            rescue_queries.append({"facet": label, "query": query})
            break
    return rescue_queries


def _anchor_query(query: Any, topic_anchor: str) -> str:
    clean_query = " ".join(str(query).split()).strip()
    clean_anchor = " ".join(str(topic_anchor).split()).strip()
    if not clean_query or not clean_anchor:
        return clean_query or clean_anchor
    if _normalize(clean_anchor) in _normalize(clean_query):
        return clean_query
    return f"{clean_anchor} {clean_query}"


def _matching_queries(
    *,
    candidates: list[Any],
    normalized_queries: list[tuple[str, str]],
) -> list[str]:
    matches: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized_candidate = _normalize(candidate)
        if not normalized_candidate:
            continue
        candidate_tokens = set(normalized_candidate.split())
        for query, normalized_query in normalized_queries:
            query_tokens = set(normalized_query.split())
            if (
                normalized_candidate in normalized_query
                or candidate_tokens.issubset(query_tokens)
            ):
                key = query.casefold()
                if key not in seen:
                    seen.add(key)
                    matches.append(query)
    return matches


def _facet_evidence_terms(facet: dict[str, Any]) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    for value in list(facet.get("search_terms", []) or []):
        normalized = _normalize(value)
        if len(normalized.split()) < 2 or normalized in seen:
            continue
        seen.add(normalized)
        terms.append(normalized)
    return terms[:3]


def _facet_paper_matches(
    *,
    terms: list[str],
    papers: dict[str, Any],
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for paper_id, paper in papers.items():
        source = str(_paper_value(paper, "source") or "").casefold()
        if source in {"seed", "fallback"}:
            continue
        paper_relevance_tier = str(
            _paper_value(paper, "relevance_tier") or "candidate"
        ).casefold()
        if paper_relevance_tier not in {"direct", "adjacent"}:
            continue
        title = _normalize(
            " ".join(
                [
                    str(_paper_value(paper, "title") or ""),
                    *list(_paper_value(paper, "keywords") or []),
                ]
            )
        )
        abstract = _normalize(_paper_value(paper, "abstract") or "")
        title_term = _best_term_match(terms, title)
        abstract_term = _best_term_match(terms, abstract)
        if title_term:
            facet_match_location = "title"
            matched_term = title_term
        elif abstract_term:
            facet_match_location = "abstract"
            matched_term = abstract_term
        else:
            continue
        match_type = (
            "direct"
            if paper_relevance_tier == "direct"
            and facet_match_location == "title"
            else "adjacent"
        )
        matches.append(
            {
                "paper_id": str(paper_id),
                "title": str(_paper_value(paper, "title") or ""),
                "match_type": match_type,
                "matched_term": matched_term,
                "paper_relevance_tier": paper_relevance_tier,
                "facet_match_location": facet_match_location,
            }
        )
    matches.sort(key=lambda item: 0 if item["match_type"] == "direct" else 1)
    return matches


def _best_term_match(terms: list[str], text: str) -> str:
    text_tokens = set(text.split())
    for term in terms:
        if term in text:
            return term
        term_tokens = set(term.split())
        if len(term_tokens) >= 2 and len(term_tokens & text_tokens) / len(term_tokens) >= 0.75:
            return term
    return ""


def _paper_value(paper: Any, field: str) -> Any:
    if isinstance(paper, dict):
        return paper.get(field)
    return getattr(paper, field, None)


def _normalize(value: Any) -> str:
    return " ".join(
        token.casefold()
        for token in re.findall(r"[A-Za-z][A-Za-z0-9-]*", str(value or ""))
    )
