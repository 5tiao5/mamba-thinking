from __future__ import annotations

import importlib
import ipaddress
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher
from typing import Any


_ARXIV_API = "https://export.arxiv.org/api/query"
_OPENALEX_API = "https://api.openalex.org/works"
_REQUEST_TIMEOUT = 20
_DEFAULT_MAX_PDF_BYTES = 20 * 1024 * 1024
_ARXIV_ID_PATTERN = re.compile(r"(?P<id>\d{4}\.\d{4,5})(?:v\d+)?", re.IGNORECASE)
_DOI_PATTERN = re.compile(r"(10\.\d{4,9}/[-._;()/:A-Z0-9]+)", re.IGNORECASE)
_HEADING_PATTERN = re.compile(
    r"^(?:\d+(?:\.\d+)*\s+)?"
    r"(abstract|introduction|background|related work|method(?:ology)?|"
    r"approach|experiments?|evaluation|results?|discussion|limitations?|"
    r"conclusion|references|bibliography)\s*$",
    re.IGNORECASE,
)


class PaperResolutionError(RuntimeError):
    """Raised when a paper identifier cannot be resolved safely."""


class FullTextUnavailableError(RuntimeError):
    """Raised when open full text cannot be fetched or parsed."""


@dataclass
class PaperResolution:
    paper_id: str
    title: str
    source: str
    source_url: str = ""
    pdf_url: str = ""
    doi: str = ""
    arxiv_id: str = ""
    abstract: str = ""
    authors: list[str] = field(default_factory=list)
    publish_date: str = ""
    resolution_method: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FullTextPage:
    page_number: int
    text: str


@dataclass
class FullTextSection:
    heading: str
    start_page: int
    end_page: int
    text: str


@dataclass
class FullTextDocument:
    source_url: str
    pages: list[FullTextPage]
    sections: list[FullTextSection]
    parser: str
    total_pages: int = 0
    metadata: dict[str, str] = field(default_factory=dict)
    truncated: bool = False
    warnings: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n\n".join(page.text for page in self.pages if page.text)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["text"] = self.text
        return payload


def resolve_paper(reference: str) -> PaperResolution | None:
    """Resolve an arXiv ID, DOI, URL, or paper title into one paper identity."""

    normalized = " ".join(str(reference or "").split()).strip()
    if not normalized:
        return None

    arxiv_id = _extract_arxiv_id(normalized)
    if arxiv_id:
        return _resolve_arxiv(arxiv_id)

    doi = _extract_doi(normalized)
    if doi:
        return _resolve_openalex_doi(doi)

    return _resolve_openalex_title(normalized)


def fetch_full_text(
    paper_or_url: PaperResolution | str,
    *,
    max_pages: int = 40,
    max_bytes: int = _DEFAULT_MAX_PDF_BYTES,
) -> FullTextDocument:
    """Download an open PDF and return page-aware, section-aware text."""

    pdf_url = (
        paper_or_url.pdf_url
        if isinstance(paper_or_url, PaperResolution)
        else str(paper_or_url or "").strip()
    )
    if not pdf_url:
        raise FullTextUnavailableError("No open PDF URL is available for this paper.")
    _validate_public_https_url(pdf_url)

    request = urllib.request.Request(
        pdf_url,
        headers={
            "User-Agent": "ProductAgent/1.0",
            "Accept": "application/pdf",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=_REQUEST_TIMEOUT) as response:
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > max_bytes:
                raise FullTextUnavailableError(
                    f"PDF exceeds the {max_bytes} byte download limit."
                )
            content_type = str(response.headers.get("Content-Type", "")).lower()
            payload = response.read(max_bytes + 1)
    except FullTextUnavailableError:
        raise
    except Exception as exc:
        raise FullTextUnavailableError(f"Unable to download open PDF: {exc}") from exc

    if len(payload) > max_bytes:
        raise FullTextUnavailableError(
            f"PDF exceeds the {max_bytes} byte download limit."
        )
    if "pdf" not in content_type and not payload.startswith(b"%PDF"):
        raise FullTextUnavailableError("The resolved full-text URL did not return a PDF.")

    return parse_pdf_bytes(payload, source_url=pdf_url, max_pages=max_pages)


def parse_pdf_bytes(
    payload: bytes,
    *,
    source_url: str = "",
    max_pages: int = 40,
) -> FullTextDocument:
    """Parse PDF bytes with optional PyMuPDF support."""

    if not payload:
        raise FullTextUnavailableError("The PDF payload is empty.")
    if max_pages < 1:
        raise ValueError("max_pages must be at least 1.")

    try:
        fitz = importlib.import_module("fitz")
    except ModuleNotFoundError as exc:
        raise FullTextUnavailableError(
            "PDF parsing requires PyMuPDF. Install it with `pip install pymupdf`."
        ) from exc

    try:
        document = fitz.open(stream=payload, filetype="pdf")
        total_pages = len(document)
        pdf_metadata = {
            str(key): " ".join(str(value or "").split())
            for key, value in dict(document.metadata or {}).items()
            if str(value or "").strip()
        }
        page_limit = min(total_pages, max_pages)
        pages = [
            FullTextPage(
                page_number=index + 1,
                text=_clean_page_text(document.load_page(index).get_text("text")),
            )
            for index in range(page_limit)
        ]
        document.close()
    except Exception as exc:
        raise FullTextUnavailableError(f"Unable to parse PDF content: {exc}") from exc

    warnings: list[str] = []
    if not any(page.text for page in pages):
        warnings.append(
            "The PDF contains no extractable text; it may require OCR."
        )
    truncated = total_pages > page_limit
    if truncated:
        warnings.append(
            f"Only the first {page_limit} of {total_pages} pages were parsed."
        )

    return FullTextDocument(
        source_url=source_url,
        pages=pages,
        sections=_build_sections(pages),
        parser="pymupdf",
        total_pages=total_pages,
        metadata=pdf_metadata,
        truncated=truncated,
        warnings=warnings,
    )


def _resolve_arxiv(arxiv_id: str) -> PaperResolution | None:
    url = f"{_ARXIV_API}?{urllib.parse.urlencode({'id_list': arxiv_id})}"
    payload = _request_bytes(url)
    if not payload:
        return None

    namespace = {"atom": "http://www.w3.org/2005/Atom"}
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise PaperResolutionError("arXiv returned invalid metadata.") from exc
    entry = root.find("atom:entry", namespace)
    if entry is None:
        return None

    resolved_id = _atom_text(entry, "atom:id", namespace).rsplit("/", 1)[-1]
    resolved_id = re.sub(r"v\d+$", "", resolved_id, flags=re.IGNORECASE) or arxiv_id
    authors = [
        _atom_text(author, "atom:name", namespace)
        for author in entry.findall("atom:author", namespace)
    ]
    return PaperResolution(
        paper_id=resolved_id,
        title=_atom_text(entry, "atom:title", namespace),
        source="arxiv",
        source_url=f"https://arxiv.org/abs/{resolved_id}",
        pdf_url=f"https://arxiv.org/pdf/{resolved_id}.pdf",
        doi="",
        arxiv_id=resolved_id,
        abstract=_atom_text(entry, "atom:summary", namespace),
        authors=[author for author in authors if author],
        publish_date=_atom_text(entry, "atom:published", namespace)[:10],
        resolution_method="arxiv_id",
    )


def _resolve_openalex_doi(doi: str) -> PaperResolution | None:
    encoded = urllib.parse.quote(f"https://doi.org/{doi}", safe=":/")
    payload = _request_json(f"{_OPENALEX_API}/{encoded}")
    if not isinstance(payload, dict):
        return None
    return _openalex_to_resolution(payload, resolution_method="doi")


def _resolve_openalex_title(title: str) -> PaperResolution | None:
    query = urllib.parse.urlencode({"search": title, "per-page": "5"})
    payload = _request_json(f"{_OPENALEX_API}?{query}")
    results = payload.get("results", []) if isinstance(payload, dict) else []
    candidates = [
        item for item in results
        if isinstance(item, dict) and str(item.get("display_name", "")).strip()
    ]
    if not candidates:
        return None

    requested = _normalize_title(title)
    best = max(
        candidates,
        key=lambda item: SequenceMatcher(
            None,
            requested,
            _normalize_title(str(item.get("display_name", ""))),
        ).ratio(),
    )
    score = SequenceMatcher(
        None,
        requested,
        _normalize_title(str(best.get("display_name", ""))),
    ).ratio()
    if score < 0.55:
        return None
    return _openalex_to_resolution(best, resolution_method="title")


def _openalex_to_resolution(
    item: dict[str, Any],
    *,
    resolution_method: str,
) -> PaperResolution:
    ids = item.get("ids", {}) or {}
    doi = _extract_doi(str(ids.get("doi") or item.get("doi") or "")) or ""
    locations = [
        item.get("best_oa_location") or {},
        item.get("primary_location") or {},
    ]
    pdf_url = next(
        (
            str(location.get("pdf_url") or "").strip()
            for location in locations
            if str(location.get("pdf_url") or "").strip()
        ),
        "",
    )
    source_url = next(
        (
            str(location.get("landing_page_url") or "").strip()
            for location in locations
            if str(location.get("landing_page_url") or "").strip()
        ),
        str(item.get("id") or ""),
    )
    arxiv_id = _extract_arxiv_id(f"{source_url} {pdf_url}") or ""
    authors = [
        str((authorship.get("author") or {}).get("display_name") or "").strip()
        for authorship in item.get("authorships", []) or []
        if isinstance(authorship, dict)
    ]
    return PaperResolution(
        paper_id=arxiv_id or doi or str(item.get("id") or "").rsplit("/", 1)[-1],
        title=" ".join(str(item.get("display_name") or "").split()),
        source="openalex",
        source_url=source_url,
        pdf_url=pdf_url,
        doi=doi,
        arxiv_id=arxiv_id,
        abstract=_decode_openalex_abstract(item.get("abstract_inverted_index")),
        authors=[author for author in authors if author],
        publish_date=str(item.get("publication_date") or item.get("publication_year") or ""),
        resolution_method=resolution_method,
    )


def _request_bytes(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "ProductAgent/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=_REQUEST_TIMEOUT) as response:
            return response.read()
    except Exception as exc:
        raise PaperResolutionError(f"Unable to resolve paper metadata: {exc}") from exc


def _request_json(url: str) -> dict[str, Any]:
    payload = _request_bytes(url)
    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PaperResolutionError("Paper metadata source returned invalid JSON.") from exc
    return decoded if isinstance(decoded, dict) else {}


def _extract_arxiv_id(value: str) -> str | None:
    match = _ARXIV_ID_PATTERN.search(str(value or ""))
    return match.group("id") if match else None


def _extract_doi(value: str) -> str | None:
    match = _DOI_PATTERN.search(str(value or ""))
    if not match:
        return None
    return match.group(1).rstrip(".,;)").lower()


def _atom_text(
    element: ET.Element,
    tag: str,
    namespace: dict[str, str],
) -> str:
    found = element.find(tag, namespace)
    return " ".join((found.text or "").split()) if found is not None else ""


def _decode_openalex_abstract(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    positioned: list[tuple[int, str]] = []
    for token, positions in value.items():
        for position in positions or []:
            if isinstance(position, int):
                positioned.append((position, str(token)))
    return " ".join(token for _, token in sorted(positioned))


def _normalize_title(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(value or "").casefold()))


def _validate_public_https_url(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise FullTextUnavailableError("Full text must use a public HTTPS URL.")

    hostname = parsed.hostname.casefold()
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise FullTextUnavailableError("Local full-text URLs are not allowed.")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return
    if not address.is_global:
        raise FullTextUnavailableError("Private full-text URLs are not allowed.")


def _clean_page_text(value: str) -> str:
    lines = [" ".join(line.split()) for line in str(value or "").splitlines()]
    return "\n".join(line for line in lines if line).strip()


def _build_sections(pages: list[FullTextPage]) -> list[FullTextSection]:
    sections: list[FullTextSection] = []
    heading = "Front Matter"
    start_page = pages[0].page_number if pages else 1
    end_page = start_page
    content: list[str] = []

    def flush() -> None:
        text = "\n".join(content).strip()
        if text:
            sections.append(
                FullTextSection(
                    heading=heading,
                    start_page=start_page,
                    end_page=end_page,
                    text=text,
                )
            )

    for page in pages:
        for line in page.text.splitlines():
            if _HEADING_PATTERN.fullmatch(line.strip()):
                flush()
                heading = line.strip()
                start_page = page.page_number
                end_page = page.page_number
                content = []
                continue
            content.append(line)
            end_page = page.page_number
    flush()
    return sections
