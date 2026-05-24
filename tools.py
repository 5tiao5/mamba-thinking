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


# ── arXiv ────────────────────────────────────────────────────────────────────

def search_papers(query: str, max_results: int = 10) -> List[PaperNode]:
    """Search arXiv and return PaperNode list sorted by relevance."""
    if not query.strip():
        return []

    encoded = urllib.parse.quote(f'all:"{query}"', safe="")
    url = (
        f"{_ARXIV_API}?search_query={encoded}"
        f"&start=0&max_results={max(max_results, 3)}"
        f"&sortBy=relevance"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ProductAgent/1.0"})
        with urllib.request.urlopen(req, timeout=_REQUEST_TIMEOUT) as resp:
            raw = resp.read().decode("utf-8")
        return _parse_arxiv_atom(raw, query)
    except Exception:
        return []


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
        req = urllib.request.Request(url, headers={"User-Agent": "ProductAgent/1.0"})
        with urllib.request.urlopen(req, timeout=_REQUEST_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
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
    enriched = 0
    linked = 0
    paper_items = list(papers.values())[:max_papers]
    local_ids = set(papers.keys())
    local_dois = {p.doi for p in papers.values() if p.doi}

    for paper in paper_items:
        if paper.references:
            continue
        try:
            refs = _fetch_s2_references(paper.paper_id)
            if refs:
                paper.references = refs
                enriched += 1
                for ref_id in refs:
                    if ref_id in local_ids or ref_id in local_dois:
                        linked += 1
        except Exception:
            continue

    return enriched, linked


def _fetch_s2_references(paper_id: str) -> List[str]:
    url = f"https://api.semanticscholar.org/graph/v1/paper/{paper_id}/references?limit=20&fields=externalIds"
    req = urllib.request.Request(url, headers={"User-Agent": "ProductAgent/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=_REQUEST_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError):
        return []

    ref_ids: List[str] = []
    for ref in data.get("data", []):
        cited = ref.get("citedPaper", {})
        ext = cited.get("externalIds", {}) or {}
        arxiv_id = ext.get("ArXiv", "")
        if arxiv_id:
            ref_ids.append(arxiv_id)
        else:
            ref_ids.append(cited.get("paperId", ""))
    return [r for r in ref_ids if r]


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
