from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Tuple

from models import PaperNode

_ARXIV_API = "http://export.arxiv.org/api/query"
_S2_API = "https://api.semanticscholar.org/graph/v1/paper/search"
_REQUEST_TIMEOUT = 15


def _semantic_scholar_headers() -> Dict[str, str]:
    headers = {"User-Agent": "ProductAgent/1.0"}
    api_key = str(os.environ.get("S2_API_KEY", "") or "").strip()
    if api_key:
        headers["x-api-key"] = api_key
    return headers


# ── arXiv ────────────────────────────────────────────────────────────────────

def search_papers(query: str, max_results: int = 10) -> List[PaperNode]:
    """Search arXiv and return PaperNode list sorted by relevance."""
    if not query.strip():
        return []

    params = urllib.parse.urlencode(
        {
            "search_query": _build_arxiv_search_query(query),
            "start": "0",
            "max_results": str(max(max_results, 3)),
            "sortBy": "relevance",
        }
    )
    url = f"{_ARXIV_API}?{params}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ProductAgent/1.0"})
        with urllib.request.urlopen(req, timeout=_REQUEST_TIMEOUT) as resp:
            raw = resp.read().decode("utf-8")
        return _parse_arxiv_atom(raw, query)
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise RuntimeError(
                "arXiv rate limit reached; retry later instead of treating this "
                "as an empty literature result."
            ) from exc
        return []
    except Exception:
        return []


def search_papers_recall(
    queries: List[str],
    max_results: int = 10,
) -> List[PaperNode]:
    """Run one bounded arXiv OR query for recall rescue.

    Each input remains an exact short phrase. The downstream relevance layer
    still decides whether a retrieved paper is usable evidence.
    """

    compiled = _build_arxiv_recall_query(queries)
    if not compiled:
        return []
    params = urllib.parse.urlencode(
        {
            "search_query": compiled,
            "start": "0",
            "max_results": str(max(max_results, 3)),
            "sortBy": "relevance",
        }
    )
    url = f"{_ARXIV_API}?{params}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ProductAgent/1.0"})
        with urllib.request.urlopen(req, timeout=_REQUEST_TIMEOUT) as resp:
            raw = resp.read().decode("utf-8")
        return _parse_arxiv_atom(raw, " OR ".join(queries))
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise RuntimeError(
                "arXiv rate limit reached during recall rescue; retry later."
            ) from exc
        return []
    except Exception:
        return []


def _build_arxiv_recall_query(queries: List[str]) -> str:
    phrases: List[str] = []
    for query in queries:
        normalized = " ".join(
            re.findall(r"[A-Za-z][A-Za-z0-9-]*", str(query or ""))
        ).strip()
        if not normalized:
            continue
        words = normalized.split()
        if len(words) > 5:
            normalized = " ".join(words[:5])
        phrase = f'all:"{normalized.casefold()}"'
        if phrase not in phrases:
            phrases.append(phrase)
    return " OR ".join(phrases[:3])


def _build_arxiv_search_query(query: str) -> str:
    """Compile a natural-language query into recall-friendly arXiv syntax.

    Wrapping the whole request in ``all:"..."`` behaves like a long phrase
    search and frequently returns zero results. Short academic phrases are
    preserved, while the remaining informative terms are combined with AND.
    """

    normalized = " ".join(str(query or "").replace("-", " ").split()).strip()
    if not normalized:
        return "all:*"

    lowered = normalized.casefold()
    phrase_aliases = (
        ("software engineering", "software engineering"),
        ("software development", "software development"),
        ("development lifecycle", "development lifecycle"),
        ("scientific literature", "scientific literature"),
        ("research assistant", "research assistant"),
        ("literature review", "literature review"),
        ("evidence citation", "evidence citation"),
        ("multi agent", "multi agent"),
        ("function calling", "function calling"),
        ("tool calling", "tool calling"),
        ("tool use", "tool use"),
        ("language agent", "language agent"),
        ("coding agent", "coding agent"),
        ("code agent", "code agent"),
        ("failure mode", "failure mode"),
    )
    clauses: List[str] = []
    consumed = lowered
    for needle, phrase in phrase_aliases:
        if needle not in consumed:
            continue
        clauses.append(f'all:"{phrase}"')
        consumed = consumed.replace(needle, " ")

    stopwords = {
        "a", "an", "the", "and", "or", "for", "with", "from", "to", "of",
        "in", "on", "by", "paper", "papers", "recent", "latest", "study",
        "studies", "research",
    }
    tokens = [
        token.casefold()
        for token in re.findall(r"[A-Za-z][A-Za-z0-9]+", consumed)
        if token.casefold() not in stopwords and len(token) >= 2
    ]
    for token in list(dict.fromkeys(tokens))[:5]:
        clauses.append(f"all:{token}")

    return " AND ".join(clauses[:6]) or f'all:"{normalized}"'


def search_survey_papers(topic: str, max_results: int = 6) -> List[PaperNode]:
    """Search arXiv for survey/review papers on a topic."""
    survey_query = f'({topic}) AND (survey OR review OR "state of the art" OR comprehensive)'
    papers = search_papers(survey_query, max_results=max(max_results, 8))
    # Prioritize papers with survey-like titles
    survey_keywords = {"survey", "review", "comprehensive", "state of the art", "overview"}
    scored: List[Tuple[int, PaperNode]] = []
    for p in papers:
        title_lower = p.title.lower()
        score = sum(1 for kw in survey_keywords if kw in title_lower)
        scored.append((score, p))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [p for _, p in scored[:max_results]]


def _parse_arxiv_atom(xml_text: str, query: str) -> List[PaperNode]:
    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "arxiv": "http://arxiv.org/schemas/atom",
    }
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    papers: List[PaperNode] = []
    for entry in root.findall("atom:entry", ns):
        arxiv_id = _text(entry, "atom:id", ns).rsplit("/", 1)[-1]
        title = " ".join(_text(entry, "atom:title", ns).split())
        abstract = " ".join(_text(entry, "atom:summary", ns).split())
        authors = [
            " ".join(a.text.split()) if a.text else ""
            for a in entry.findall("atom:author/atom:name", ns)
        ]
        published = _text(entry, "atom:published", ns)[:10]
        categories = [
            c.get("term", "")
            for c in entry.findall("atom:category", ns)
            if c.get("term")
        ]
        primary = categories[0] if categories else ""
        keyword = _keyword_from_categories(primary)

        papers.append(
            PaperNode(
                paper_id=arxiv_id,
                title=title,
                abstract=abstract,
                authors=authors,
                keywords=[keyword] if keyword else [],
                publish_date=published,
                source="arxiv",
                taxonomy_category=primary,
                url=f"https://arxiv.org/abs/{arxiv_id}",
            )
        )
    return papers


# ── Semantic Scholar ──────────────────────────────────────────────────────────

def search_semantic_scholar(query: str, max_results: int = 10) -> List[PaperNode]:
    """Search Semantic Scholar and return PaperNode list."""
    if not query.strip():
        return []

    params = urllib.parse.urlencode(
        {
            "query": query,
            "limit": str(max(max_results, 3)),
            "fields": "title,abstract,authors,year,externalIds,citationCount,url",
        }
    )
    url = f"{_S2_API}?{params}"
    try:
        req = urllib.request.Request(url, headers=_semantic_scholar_headers())
        with urllib.request.urlopen(req, timeout=_REQUEST_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise RuntimeError(
                "Semantic Scholar rate limit reached; configure S2_API_KEY "
                "or continue with arXiv recall."
            ) from exc
        return []
    except Exception:
        return []

    papers: List[PaperNode] = []
    for item in data.get("data", []):
        paper_id = item.get("paperId", "")
        title = item.get("title") or ""
        abstract = item.get("abstract") or ""
        authors = [a.get("name", "") for a in item.get("authors", [])]
        year = str(item.get("year") or "")
        ext_ids = item.get("externalIds", {}) or {}
        arxiv_id = ext_ids.get("ArXiv", "")
        doi = ext_ids.get("DOI", "")

        papers.append(
            PaperNode(
                paper_id=paper_id,
                title=" ".join(title.split()),
                abstract=" ".join(abstract.split()),
                authors=authors,
                publish_date=year,
                source="semantic_scholar",
                citation_count=item.get("citationCount", 0),
                citation_count_known=item.get("citationCount") is not None,
                citation_source="semantic_scholar",
                url=item.get("url") or f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else "",
                doi=doi,
            )
        )
    return papers


# ── Citation Enrichment ──────────────────────────────────────────────────────

def enrich_paper_references(
    papers: Dict[str, PaperNode], max_papers: int = 6
) -> Tuple[int, int]:
    """Fetch references from Semantic Scholar and link local cross-references.

    Returns (enriched_count, linked_references).
    """
    enriched, linked, _ = enrich_paper_metadata(papers, max_papers=max_papers)
    return enriched, linked


def enrich_paper_metadata(
    papers: Dict[str, PaperNode], max_papers: int = 6
) -> Tuple[int, int, int]:
    """Batch-fetch citation counts and references for the analysis set.

    Returns ``(enriched_count, linked_references, citation_counts_fetched)``.
    A missing API result remains explicitly unknown rather than being presented
    as a real zero citation count.
    """
    paper_items = [
        paper
        for paper in papers.values()
        if (paper.source or "").lower() not in {"seed", "fallback"}
    ][:max_papers]
    if not paper_items:
        return 0, 0, 0

    enriched = 0
    linked = 0
    citation_counts_fetched = 0
    local_aliases = _local_paper_aliases(papers)
    metadata_items = _fetch_s2_metadata_batch(paper_items)

    for paper, metadata in zip(paper_items, metadata_items):
        if not isinstance(metadata, dict):
            continue
        enriched += 1
        citation_count = metadata.get("citationCount")
        if citation_count is not None:
            paper.citation_count = max(int(citation_count or 0), 0)
            paper.citation_count_known = True
            paper.citation_source = "semantic_scholar"
            citation_counts_fetched += 1

        references = _metadata_references(metadata)
        normalized_refs: List[str] = []
        linked_for_paper = set()
        for reference in references:
            local_paper_id = _match_local_reference(reference, local_aliases)
            if local_paper_id and local_paper_id != paper.paper_id:
                normalized_refs.append(local_paper_id)
                linked_for_paper.add(local_paper_id)
            else:
                external_id = _preferred_reference_id(reference)
                if external_id:
                    normalized_refs.append(external_id)
        paper.references = list(dict.fromkeys([*paper.references, *normalized_refs]))
        linked += len(linked_for_paper)

    return enriched, linked, citation_counts_fetched


def _fetch_s2_metadata_batch(papers: List[PaperNode]) -> List[Dict[str, Any] | None]:
    identifiers: List[str] = []
    for paper in papers:
        candidates = _semantic_scholar_identifiers(paper)
        identifiers.append(candidates[0] if candidates else str(paper.paper_id or "").strip())

    return _request_s2_metadata_batch(identifiers)


def _request_s2_metadata_batch(
    identifiers: List[str],
) -> List[Dict[str, Any] | None]:
    if not identifiers:
        return []
    url = (
        "https://api.semanticscholar.org/graph/v1/paper/batch"
        "?fields=paperId,citationCount,externalIds,references.paperId,references.externalIds"
    )
    request = urllib.request.Request(
        url,
        data=json.dumps({"ids": identifiers}).encode("utf-8"),
        headers={**_semantic_scholar_headers(), "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=_REQUEST_TIMEOUT) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 400 and len(identifiers) > 1:
            midpoint = len(identifiers) // 2
            return [
                *_request_s2_metadata_batch(identifiers[:midpoint]),
                *_request_s2_metadata_batch(identifiers[midpoint:]),
            ]
        if exc.code == 400:
            return [None]
        raise
    if not isinstance(payload, list):
        return [None] * len(identifiers)
    return [item if isinstance(item, dict) else None for item in payload[: len(identifiers)]] + [
        None
    ] * max(len(identifiers) - len(payload), 0)


def _metadata_references(metadata: Dict[str, Any]) -> List[Dict[str, str]]:
    references: List[Dict[str, str]] = []
    for cited in metadata.get("references", []) or []:
        if not isinstance(cited, dict):
            continue
        ext = cited.get("externalIds", {}) or {}
        reference = {
            "s2": str(cited.get("paperId", "") or "").strip(),
            "arxiv": str(ext.get("ArXiv", "") or "").strip(),
            "doi": str(ext.get("DOI", "") or "").strip(),
        }
        if any(reference.values()):
            references.append(reference)
    return references


def _fetch_s2_references(paper: PaperNode) -> List[Dict[str, str]]:
    for identifier in _semantic_scholar_identifiers(paper):
        encoded_identifier = urllib.parse.quote(identifier, safe=":")
        url = (
            "https://api.semanticscholar.org/graph/v1/paper/"
            f"{encoded_identifier}/references?limit=40&fields=paperId,externalIds"
        )
        req = urllib.request.Request(url, headers=_semantic_scholar_headers())
        try:
            with urllib.request.urlopen(req, timeout=_REQUEST_TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.HTTPError, urllib.error.URLError):
            continue

        references: List[Dict[str, str]] = []
        for ref in data.get("data", []):
            cited = ref.get("citedPaper", {}) or {}
            ext = cited.get("externalIds", {}) or {}
            reference = {
                "s2": str(cited.get("paperId", "") or "").strip(),
                "arxiv": str(ext.get("ArXiv", "") or "").strip(),
                "doi": str(ext.get("DOI", "") or "").strip(),
            }
            if any(reference.values()):
                references.append(reference)
        return references
    return []


def _semantic_scholar_identifiers(paper: PaperNode) -> List[str]:
    identifiers: List[str] = []
    doi = _normalize_doi(paper.doi)
    if doi:
        identifiers.append(f"DOI:{doi}")

    arxiv_id = _paper_arxiv_id(paper)
    if arxiv_id:
        identifiers.append(f"ARXIV:{arxiv_id}")

    paper_id = str(paper.paper_id or "").strip()
    if (
        paper_id
        and _normalize_paper_identifier(paper_id)
        != _normalize_paper_identifier(arxiv_id)
    ):
        identifiers.append(paper_id)
    return list(dict.fromkeys(identifiers))


def _paper_arxiv_id(paper: PaperNode) -> str:
    source = str(paper.source or "").lower()
    paper_id = str(paper.paper_id or "").strip()
    if source == "arxiv" and paper_id:
        return re.sub(r"v\d+$", "", paper_id, flags=re.IGNORECASE)
    match = re.search(r"arxiv\.org/(?:abs|pdf)/([^?#/]+)", str(paper.url or ""), flags=re.IGNORECASE)
    if not match:
        return ""
    return re.sub(
        r"v\d+$",
        "",
        match.group(1).removesuffix(".pdf"),
        flags=re.IGNORECASE,
    )


def _local_paper_aliases(papers: Dict[str, PaperNode]) -> Dict[str, str]:
    aliases: Dict[str, str] = {}
    for canonical_id, paper in papers.items():
        candidates = [
            canonical_id,
            paper.paper_id,
            _paper_arxiv_id(paper),
            _normalize_doi(paper.doi),
        ]
        for candidate in candidates:
            normalized = _normalize_paper_identifier(candidate)
            if normalized:
                aliases.setdefault(normalized, canonical_id)
    return aliases


def _match_local_reference(
    reference: Dict[str, str],
    local_aliases: Dict[str, str],
) -> str:
    for key in ("s2", "arxiv", "doi"):
        normalized = _normalize_paper_identifier(reference.get(key, ""))
        if normalized and normalized in local_aliases:
            return local_aliases[normalized]
    return ""


def _preferred_reference_id(reference: Dict[str, str]) -> str:
    return (
        str(reference.get("arxiv", "") or "").strip()
        or str(reference.get("doi", "") or "").strip()
        or str(reference.get("s2", "") or "").strip()
    )


def _normalize_doi(value: str) -> str:
    normalized = str(value or "").strip().lower()
    normalized = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", normalized)
    normalized = re.sub(r"^doi:\s*", "", normalized)
    return normalized


def _normalize_paper_identifier(value: str) -> str:
    normalized = str(value or "").strip().lower()
    normalized = re.sub(r"^(?:arxiv|doi):\s*", "", normalized)
    normalized = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", normalized)
    normalized = re.sub(r"^https?://arxiv\.org/(?:abs|pdf)/", "", normalized)
    normalized = normalized.removesuffix(".pdf").strip()
    if re.fullmatch(r"\d{4}\.\d{4,5}v\d+", normalized):
        normalized = re.sub(r"v\d+$", "", normalized)
    return normalized


# ── Taxonomy Builder ─────────────────────────────────────────────────────────

def build_taxonomy(source_text: str) -> Dict[str, Any]:
    """Build an expert taxonomy from paper text.

    Uses LLM if available, otherwise falls back to keyword extraction.
    """
    if not source_text.strip():
        return {"taxonomy": {}}

    # Try LLM first
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("DEEPSEEK_API_KEY")
    if api_key:
        from llm_client import call_openai_json

        prompt = f"""
Based on the following research paper abstracts, build an expert taxonomy.
Group papers into 3-6 branches. For each branch, provide:
- A concise name
- A one-sentence description
- 2-4 required concepts that define the branch

Return JSON only:
{{"taxonomy": {{"Branch Name": {{"description": "...", "required_concepts": ["...", "..."]}}}}}}

Paper text:
{source_text[:6000]}
"""
        result = call_openai_json(
            prompt,
            system="You are a research taxonomy expert. Return valid JSON only.",
        )
        if result and "taxonomy" in result:
            return result

    # Keyword fallback
    return _keyword_taxonomy(source_text)


def _keyword_taxonomy(text: str) -> Dict[str, Any]:
    """Build a simple taxonomy by extracting recurring capitalized phrases."""
    lowered = text.lower()
    branches: Dict[str, Dict[str, Any]] = {}

    patterns = [
        ("methods", ["method", "approach", "technique", "algorithm", "model", "framework", "architecture"]),
        ("evaluation", ["evaluation", "benchmark", "experiment", "metric", "performance", "accuracy", "result"]),
        ("applications", ["application", "deployment", "real-world", "industry", "practice", "case study"]),
        ("limitations", ["limitation", "challenge", "failure", "issue", "problem", "bottleneck", "gap"]),
        ("future directions", ["future", "direction", "opportunity", "potential", "trend", "promising"]),
    ]

    for name, keywords in patterns:
        matched = [kw for kw in keywords if kw in lowered]
        if matched:
            branches[name] = {
                "description": f"Papers related to {name} in this research area.",
                "required_concepts": matched[:3],
            }

    return {"taxonomy": branches} if branches else {"taxonomy": {}}


# ── helpers ───────────────────────────────────────────────────────────────────

def _text(element: ET.Element, tag: str, ns: Dict[str, str]) -> str:
    child = element.find(tag, ns)
    return child.text.strip() if child is not None and child.text else ""


def _keyword_from_categories(category: str) -> str:
    mapping = {
        "cs.AI": "artificial intelligence",
        "cs.CL": "natural language processing",
        "cs.LG": "machine learning",
        "cs.CV": "computer vision",
        "cs.SE": "software engineering",
        "cs.RO": "robotics",
        "cs.HC": "human-computer interaction",
        "cs.IR": "information retrieval",
        "stat.ML": "statistical machine learning",
    }
    if not category:
        return ""
    for code, label in mapping.items():
        if code in category:
            return label
    return ""
