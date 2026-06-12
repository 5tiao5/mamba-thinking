from __future__ import annotations

import asyncio
import json
import math
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Protocol, Tuple
from uuid import uuid4

from product_agent.domain import KnowledgeDocument
from product_agent.repositories import KnowledgeRepository, ResearchTaskRepository

_OPENALEX_WORKS_API = "https://api.openalex.org/works"
_ARXIV_API = "http://export.arxiv.org/api/query"
_HTTP_TIMEOUT_SECONDS = 20
_DOI_PATTERN = re.compile(r"(10\.\d{4,9}/[-._;()/:A-Z0-9]+)", re.IGNORECASE)
_ARXIV_ID_PATTERN = re.compile(r"(?P<id>\d{4}\.\d{4,5})(?:v\d+)?", re.IGNORECASE)
_ARXIV_URL_PATTERN = re.compile(
    r"https?://arxiv\.org/(?:(?:abs|pdf)/)(?P<id>\d{4}\.\d{4,5})(?:v\d+)?(?:\.pdf)?",
    re.IGNORECASE,
)


# ============================================================================
# 领域对象（与 KnowledgeDocument 配合使用）
# ============================================================================

@dataclass
class DocumentChunk:
    """知识文档片段，用于 embedding 和检索。"""
    chunk_id: str
    document_id: str
    source_title: str
    source_task_id: Optional[str]
    content: str
    start_idx: int
    end_idx: int
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchResult:
    """检索结果（含片段及综合分数）。"""
    chunk: DocumentChunk
    score: float
    rank: int


@dataclass
class KnowledgeHit:
    document_id: str
    title: str
    snippet: str
    score: float
    scope: str
    source_task_id: Optional[str] = None
    source_type: str = ""
    evidence_level: str = "candidate"
    matched_chunk_count: int = 0
    supporting_snippets: List[str] = field(default_factory=list)


@dataclass
class PaperImportCandidate:
    candidate_id: str
    title: str
    authors: List[str] = field(default_factory=list)
    year: Optional[int] = None
    abstract: str = ""
    source_url: Optional[str] = None
    pdf_url: Optional[str] = None
    doi: Optional[str] = None
    arxiv_id: Optional[str] = None
    source: str = ""
    venue: Optional[str] = None
    openalex_id: Optional[str] = None
    is_exact_match: bool = False


# ============================================================================
# 可插拔组件协议（接口定义）
# ============================================================================

class Chunker(Protocol):
    """文本分块器协议。"""
    def chunk(self, text: str, metadata: Dict[str, Any]) -> List[DocumentChunk]:
        """将文本切分为多个 DocumentChunk。"""
        ...


class Embedder(Protocol):
    """文本向量化协议。"""
    def embed(self, texts: List[str]) -> List[List[float]]:
        """将文本列表转换为向量列表。"""
        ...


class VectorStore(Protocol):
    """向量存储协议。"""
    def add(self, chunks: List[DocumentChunk], vectors: List[List[float]]) -> None:
        """添加文档块及其向量。"""
        ...
    def similarity_search(
        self,
        query_vector: List[float],
        top_k: int,
        filter_tags: Optional[List[str]] = None
    ) -> List[Tuple[DocumentChunk, float]]:
        """向量相似度检索，可选标签过滤。"""
        ...
    def delete_by_document_id(self, document_id: str) -> None:
        """删除指定文档的所有块。"""
        ...


class Reranker(Protocol):
    """重排序器协议。"""
    def rerank(self, query: str, documents: List[str]) -> List[float]:
        """对文档列表进行重排序，返回每个文档的相关性分数。"""
        ...


# ============================================================================
# 默认实现（用于开发测试，生产环境请替换为真实组件）
# ============================================================================

class SimpleChunker:
    """基于段落和固定大小的简单分块器。"""

    def __init__(self, chunk_size: int = 500, overlap: int = 50):
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk(self, text: str, metadata: Dict[str, Any]) -> List[DocumentChunk]:
        paragraphs = re.split(r'\n\s*\n', text)
        chunks = []
        global_pos = 0
        doc_id = metadata.get("document_id", "unknown")
        title = metadata.get("title", "")
        task_id = metadata.get("source_task_id")
        tags = metadata.get("tags", [])

        for para in paragraphs:
            if not para.strip():
                continue
            start = 0
            para_len = len(para)
            while start < para_len:
                end = min(start + self.chunk_size, para_len)
                chunk_text = para[start:end]
                chunk_id = f"{doc_id}_chunk_{len(chunks)}"
                chunks.append(DocumentChunk(
                    chunk_id=chunk_id,
                    document_id=doc_id,
                    source_title=title,
                    source_task_id=task_id,
                    content=chunk_text,
                    start_idx=global_pos + start,
                    end_idx=global_pos + end,
                    tags=tags,
                    metadata=metadata.copy()
                ))
                start += (self.chunk_size - self.overlap)
            global_pos += para_len + 2
        return chunks


class HashEmbedder:
    """
    确定性哈希嵌入器，无需外部依赖。

    使用多哈希特征哈希技巧将文本映射为固定维度的稠密向量。
    相同文本始终产生相同向量，支持有意义的余弦相似度比较。
    用于替代 Test DummyEmbedder（随机向量，无意义）。
    """

    def __init__(self, dimension: int = 768, num_hashes: int = 2):
        self.dim = dimension
        self.num_hashes = num_hashes

    def embed(self, texts: List[str]) -> List[List[float]]:
        import hashlib
        import math
        import struct

        results = []
        for text in texts:
            vec = [0.0] * self.dim
            words = self._tokenize(text)
            if not words:
                results.append(vec)
                continue

            for word in words:
                for seed in range(self.num_hashes):
                    h = hashlib.md5(f"{seed}:{word}".encode()).digest()
                    idx = struct.unpack_from("I", h[:4])[0] % self.dim
                    sign = 1 if (h[4] & 1) == 0 else -1
                    vec[idx] += sign

            norm = math.sqrt(sum(v * v for v in vec))
            if norm > 0:
                vec = [v / norm for v in vec]
            results.append(vec)

        return results

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        import re

        text = text.lower()
        tokens = re.findall(r"[a-z][a-z0-9]{2,}", text)
        stop_words = {
            "the", "and", "for", "are", "was", "but", "not", "you", "all",
            "can", "had", "her", "his", "its", "out", "see", "may", "use",
            "has", "how", "new", "now", "our", "way", "who", "did", "due",
            "get", "got", "yet", "any", "few", "own", "set", "too", "two",
            "also", "been", "each", "from", "have", "into", "like", "more",
            "much", "only", "over", "some", "such", "than", "that", "them",
            "then", "they", "this", "very", "well", "what", "when", "will",
            "with", "which", "their", "there", "where", "about", "would",
            "could", "should", "after", "before", "other", "between",
            "paper", "papers", "study", "studies", "research", "survey",
            "results", "method", "using", "based", "approach", "propose",
            "methods", "models", "model", "data", "analysis",
        }
        return [t for t in tokens if t not in stop_words and len(t) >= 3]


class DummyEmbedder:
    """占位 embedding 模型（随机向量）。仅用于测试。"""

    def __init__(self, dimension: int = 384):
        self.dim = dimension

    def embed(self, texts: List[str]) -> List[List[float]]:
        import random
        return [[random.random() for _ in range(self.dim)] for _ in texts]


class InMemoryVectorStore:
    """内存版向量存储，支持余弦相似度和标签过滤。"""

    def __init__(self):
        self.chunks: List[DocumentChunk] = []
        self.vectors: List[List[float]] = []

    def add(self, chunks: List[DocumentChunk], vectors: List[List[float]]) -> None:
        self.chunks.extend(chunks)
        self.vectors.extend(vectors)

    def similarity_search(
        self,
        query_vector: List[float],
        top_k: int,
        filter_tags: Optional[List[str]] = None
    ) -> List[Tuple[DocumentChunk, float]]:
        def cosine_sim(v1, v2):
            dot = sum(a * b for a, b in zip(v1, v2))
            norm1 = math.sqrt(sum(a * a for a in v1))
            norm2 = math.sqrt(sum(b * b for b in v2))
            if norm1 == 0 or norm2 == 0:
                return 0.0
            return dot / (norm1 * norm2)

        scored = []
        for chunk, vec in zip(self.chunks, self.vectors):
            if filter_tags:
                if not any(tag in chunk.tags for tag in filter_tags):
                    continue
            sim = cosine_sim(query_vector, vec)
            scored.append((chunk, sim))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    def delete_by_document_id(self, document_id: str) -> None:
        indices_to_keep = [i for i, c in enumerate(self.chunks) if c.document_id != document_id]
        self.chunks = [self.chunks[i] for i in indices_to_keep]
        self.vectors = [self.vectors[i] for i in indices_to_keep]


class NoopReranker:
    """占位重排序器，返回原始顺序（不改变排序）。"""
    def rerank(self, query: str, documents: List[str]) -> List[float]:
        return [1.0] * len(documents)



class KnowledgeService:
    """
    研究私有知识、全局共享知识与后续 RAG 的统一入口。

    TODO(iter3-knowledge-service):
    当前定位:
    - 本类是“知识共享 / RAG”的产品层入口
    - 现在只提供保存和读取骨架，不直接绑定具体向量库

    待实现:
    1. 接入 chunking
       实现思路:
       - 以 report / paper brief / taxonomy summary 为输入
       - 按段落、标题或主题块拆分成 chunk

    2. 接入 embedding
       实现思路:
       - 给每个 chunk 生成 embedding
       - embedding 存储方案后置，不阻塞当前服务接口设计

    3. 支持按 topic / tag 检索
       实现思路:
       - 先做关键词过滤
       - 后续替换为“关键词 + 向量召回”的混合检索

    4. 支持来源标注
       实现思路:
       - 每个知识片段都保留 source_task_id / source_type / title
       - 让后续回答能引用知识来源
    """

    def __init__(
        self,
        repository: KnowledgeRepository,
        chunker: Optional[Chunker] = None,
        embedder: Optional[Embedder] = None,
        vector_store: Optional[VectorStore] = None,
        reranker: Optional[Reranker] = None,
        *,
        task_repository: Optional[ResearchTaskRepository] = None,
        enable_hybrid_search: bool = True,
        keyword_weight: float = 0.3,
        vector_weight: float = 0.7,
        async_indexing: bool = False
    ) -> None:
        """
        初始化 KnowledgeService。

        Args:
            repository: 知识文档仓储
            chunker: 文本分块器（默认 SimpleChunker）
            embedder: 向量化模型（默认 DummyEmbedder）
            vector_store: 向量存储（默认 InMemoryVectorStore）
            reranker: 重排序器（默认 NoopReranker）
            enable_hybrid_search: 是否启用混合检索（关键词+向量）
            keyword_weight: 关键词检索权重
            vector_weight: 向量检索权重
            async_indexing: 是否异步建立索引（不阻塞保存）
        """
        self.repository = repository
        self.chunker = chunker or SimpleChunker()
        self.embedder = embedder or HashEmbedder()
        self.vector_store = vector_store or InMemoryVectorStore()
        self.reranker = reranker or NoopReranker()
        self.task_repository = task_repository
        self.enable_hybrid_search = enable_hybrid_search
        self.keyword_weight = keyword_weight
        self.vector_weight = vector_weight
        self.async_indexing = async_indexing
        self.paper_candidate_cache: Dict[str, PaperImportCandidate] = {}


    def save_summary(
        self,
        *,
        title: str,
        content: str,
        source_task_id: str | None = None,
        conversation_id: str | None = None,
        tags: List[str] | None = None,
        index_immediately: bool = True
    ) -> KnowledgeDocument:
        """
        保存一份知识摘要文档。

        Args:
            title: 文档标题
            content: 文档正文或摘要
            source_task_id: 来源任务 ID
            tags: 标签列表
            index_immediately: 是否立即建立索引（分块+向量化）

        Returns:
            保存后的 KnowledgeDocument
        """
        metadata: Dict[str, Any] = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source_type": "workspace_summary",
            "visibility": "conversation" if conversation_id else "shared",
        }
        if conversation_id:
            metadata["conversation_id"] = conversation_id

        document = KnowledgeDocument(
            document_id=f"doc_{uuid4().hex[:12]}",
            title=title,
            source_task_id=source_task_id,
            content=content,
            tags=tags or [],
            metadata=metadata,
        )
        saved_doc = self.repository.save(document)
        if index_immediately:
            self._maybe_index_document(saved_doc)
        return saved_doc

    def import_document(
        self,
        *,
        title: str,
        content: str,
        tags: List[str] | None = None,
        source_url: str | None = None,
        source_task_id: str | None = None,
        conversation_id: str | None = None,
        notes: str | None = None,
        metadata_extra: Dict[str, Any] | None = None,
        index_immediately: bool = True
    ) -> KnowledgeDocument:
        """Save a user-imported knowledge document for later retrieval and grounding."""
        metadata = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source_type": "user_import",
            "visibility": "conversation" if conversation_id else "shared",
        }
        if source_url:
            metadata["source_url"] = source_url
        if conversation_id:
            metadata["conversation_id"] = conversation_id
        if notes:
            metadata["notes"] = notes
        if metadata_extra:
            metadata.update(metadata_extra)

        document = KnowledgeDocument(
            document_id=f"doc_{uuid4().hex[:12]}",
            title=title,
            source_task_id=source_task_id,
            content=content,
            tags=tags or [],
            metadata=metadata,
        )
        saved_doc = self.repository.save(document)
        if index_immediately:
            self._maybe_index_document(saved_doc)
        return saved_doc

    def search_paper_candidates(self, query: str, *, limit: int = 3) -> List[PaperImportCandidate]:
        normalized_query = " ".join(query.strip().split())
        if len(normalized_query) < 2:
            return []

        exact_arxiv_id = self._extract_arxiv_id(normalized_query)
        if exact_arxiv_id:
            candidate = self._fetch_arxiv_candidate(exact_arxiv_id)
            return self._cache_paper_candidates([candidate] if candidate else [])

        exact_doi = self._extract_doi(normalized_query)
        if exact_doi:
            candidate = self._fetch_openalex_candidate_by_doi(exact_doi)
            return self._cache_paper_candidates([candidate] if candidate else [])

        candidates = self._search_openalex_candidates(normalized_query, limit=max(limit, 3))
        return self._cache_paper_candidates(candidates[:limit])

    def import_paper_candidate(
        self,
        candidate_id: str,
        *,
        conversation_id: str | None = None,
        notes: str | None = None,
        tags: List[str] | None = None,
    ) -> KnowledgeDocument:
        candidate = self.paper_candidate_cache.get(candidate_id)
        if candidate is None:
            raise KeyError(candidate_id)

        auto_tags = self._build_paper_import_tags(candidate)
        merged_tags = []
        for tag in [*(tags or []), *auto_tags]:
            normalized = tag.strip().lower()
            if normalized and normalized not in merged_tags:
                merged_tags.append(normalized)

        metadata_extra = {
            "source_type": "paper_import",
            "import_method": "paper_candidate",
            "paper_source": candidate.source,
            "authors": list(candidate.authors),
            "year": candidate.year,
            "doi": candidate.doi,
            "arxiv_id": candidate.arxiv_id,
            "pdf_url": candidate.pdf_url,
            "venue": candidate.venue,
            "openalex_id": candidate.openalex_id,
            "is_exact_match": candidate.is_exact_match,
        }

        return self.import_document(
            title=candidate.title,
            content=self._build_paper_import_content(candidate),
            tags=merged_tags,
            source_url=candidate.source_url,
            conversation_id=conversation_id,
            notes=notes,
            metadata_extra=metadata_extra,
            index_immediately=True,
        )

    def _cache_paper_candidates(self, candidates: List[PaperImportCandidate]) -> List[PaperImportCandidate]:
        for candidate in candidates:
            self.paper_candidate_cache[candidate.candidate_id] = candidate
        return candidates

    def _fetch_json(self, url: str) -> Dict[str, Any] | List[Any] | None:
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "ProductAgent/1.0"})
            with urllib.request.urlopen(request, timeout=_HTTP_TIMEOUT_SECONDS) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception:
            return None

    def _fetch_text(self, url: str) -> str | None:
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "ProductAgent/1.0"})
            with urllib.request.urlopen(request, timeout=_HTTP_TIMEOUT_SECONDS) as response:
                return response.read().decode("utf-8")
        except Exception:
            return None

    def _extract_doi(self, query: str) -> str | None:
        match = _DOI_PATTERN.search(query)
        return match.group(1).strip() if match else None

    def _extract_arxiv_id(self, query: str) -> str | None:
        url_match = _ARXIV_URL_PATTERN.search(query)
        if url_match:
            return url_match.group("id")

        normalized = query.strip()
        if normalized.lower().startswith("arxiv:"):
            normalized = normalized.split(":", 1)[1].strip()

        id_match = _ARXIV_ID_PATTERN.fullmatch(normalized)
        if id_match:
            return id_match.group("id")
        return None

    def _fetch_arxiv_candidate(self, arxiv_id: str) -> PaperImportCandidate | None:
        url = f"{_ARXIV_API}?id_list={urllib.parse.quote(arxiv_id, safe='')}"
        xml_text = self._fetch_text(url)
        if not xml_text:
            return None

        ns = {
            "atom": "http://www.w3.org/2005/Atom",
        }
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return None

        entry = root.find("atom:entry", ns)
        if entry is None:
            return None

        title = " ".join((entry.findtext("{http://www.w3.org/2005/Atom}title") or "").split())
        abstract = " ".join((entry.findtext("{http://www.w3.org/2005/Atom}summary") or "").split())
        published = (entry.findtext("{http://www.w3.org/2005/Atom}published") or "")[:4]
        authors = []
        for author in entry.findall("{http://www.w3.org/2005/Atom}author"):
            name = " ".join((author.findtext("{http://www.w3.org/2005/Atom}name") or "").split())
            if name:
                authors.append(name)

        source_url = None
        pdf_url = None
        for link in entry.findall("{http://www.w3.org/2005/Atom}link"):
            href = link.attrib.get("href", "").strip()
            if not href:
                continue
            if link.attrib.get("title") == "pdf" or href.endswith(".pdf"):
                pdf_url = href
            elif link.attrib.get("rel") == "alternate":
                source_url = href

        candidate = PaperImportCandidate(
            candidate_id=f"paper_candidate_{uuid4().hex[:12]}",
            title=title or f"arXiv {arxiv_id}",
            authors=authors,
            year=int(published) if published.isdigit() else None,
            abstract=abstract,
            source_url=source_url or f"https://arxiv.org/abs/{arxiv_id}",
            pdf_url=pdf_url,
            arxiv_id=arxiv_id,
            source="arxiv",
            venue="arXiv",
            is_exact_match=True,
        )
        doi = self._extract_doi(candidate.abstract)  # unlikely, but harmless
        if doi:
            candidate.doi = doi
        return candidate

    def _fetch_openalex_candidate_by_doi(self, doi: str) -> PaperImportCandidate | None:
        encoded = urllib.parse.quote(f"https://doi.org/{doi}", safe="")
        payload = self._fetch_json(f"{_OPENALEX_WORKS_API}/{encoded}")
        if not isinstance(payload, dict):
            return None
        return self._paper_candidate_from_openalex_result(payload, exact_query=doi)

    def _search_openalex_candidates(self, query: str, limit: int) -> List[PaperImportCandidate]:
        encoded_query = urllib.parse.quote(query)
        payload = self._fetch_json(f"{_OPENALEX_WORKS_API}?search={encoded_query}&per-page={max(limit * 2, limit)}")
        if not isinstance(payload, dict):
            return []

        results = payload.get("results")
        if not isinstance(results, list):
            return []

        candidates: List[PaperImportCandidate] = []
        seen_titles: set[str] = set()
        for item in results:
            if not isinstance(item, dict):
                continue
            candidate = self._paper_candidate_from_openalex_result(item, exact_query=query)
            if candidate is None:
                continue
            normalized_title = self._normalize_match_text(candidate.title)
            if normalized_title in seen_titles:
                continue
            seen_titles.add(normalized_title)
            candidates.append(candidate)

        candidates.sort(
            key=lambda candidate: (
                0 if candidate.is_exact_match else 1,
                abs((candidate.year or 0) - datetime.now(timezone.utc).year),
                candidate.title.lower(),
            )
        )
        return candidates[:limit]

    def _paper_candidate_from_openalex_result(
        self,
        item: Dict[str, Any],
        *,
        exact_query: str,
    ) -> PaperImportCandidate | None:
        title = " ".join(str(item.get("display_name") or "").split())
        if not title:
            return None

        authorships = item.get("authorships") or []
        authors: List[str] = []
        for authorship in authorships[:8]:
            if not isinstance(authorship, dict):
                continue
            author = authorship.get("author") or {}
            name = " ".join(str(author.get("display_name") or "").split())
            if name:
                authors.append(name)

        primary_location = item.get("primary_location") or {}
        landing_page_url = primary_location.get("landing_page_url") or item.get("id")
        pdf_url = primary_location.get("pdf_url")
        ids = item.get("ids") or {}
        raw_doi = ids.get("doi") or item.get("doi")
        doi = self._normalize_doi(raw_doi)
        arxiv_id = self._extract_arxiv_id(str(landing_page_url or "")) or self._extract_arxiv_id(str(pdf_url or ""))
        if arxiv_id is None and doi and doi.lower().startswith("10.48550/arxiv."):
            arxiv_id = doi.split("arxiv.", 1)[1]

        year = item.get("publication_year")
        if not isinstance(year, int):
            year = None

        venue = None
        source_info = primary_location.get("source") or {}
        if isinstance(source_info, dict):
            venue = source_info.get("display_name")

        candidate = PaperImportCandidate(
            candidate_id=f"paper_candidate_{uuid4().hex[:12]}",
            title=title,
            authors=authors,
            year=year,
            abstract=self._reconstruct_openalex_abstract(item.get("abstract_inverted_index")),
            source_url=str(landing_page_url) if landing_page_url else None,
            pdf_url=str(pdf_url) if pdf_url else None,
            doi=doi,
            arxiv_id=arxiv_id,
            source="openalex",
            venue=str(venue) if venue else None,
            openalex_id=str(item.get("id") or ""),
            is_exact_match=self._is_exact_title_match(title, exact_query),
        )
        return candidate

    @staticmethod
    def _normalize_doi(value: Any) -> str | None:
        if not value:
            return None
        text = str(value).strip()
        if not text:
            return None
        if text.lower().startswith("https://doi.org/"):
            return text.split("doi.org/", 1)[1]
        if text.lower().startswith("http://doi.org/"):
            return text.split("doi.org/", 1)[1]
        return text

    @staticmethod
    def _reconstruct_openalex_abstract(abstract_index: Any) -> str:
        if not isinstance(abstract_index, dict) or not abstract_index:
            return ""

        positioned_words: List[Tuple[int, str]] = []
        for word, positions in abstract_index.items():
            if not isinstance(word, str) or not isinstance(positions, list):
                continue
            for position in positions:
                if isinstance(position, int):
                    positioned_words.append((position, word))

        if not positioned_words:
            return ""

        positioned_words.sort(key=lambda item: item[0])
        return " ".join(word for _, word in positioned_words)

    @staticmethod
    def _normalize_match_text(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()

    def _is_exact_title_match(self, title: str, query: str) -> bool:
        normalized_title = self._normalize_match_text(title)
        normalized_query = self._normalize_match_text(query)
        if not normalized_query:
            return False
        if normalized_title == normalized_query:
            return True
        return normalized_query in normalized_title and len(normalized_query) >= max(12, len(normalized_title) - 8)

    def _build_paper_import_tags(self, candidate: PaperImportCandidate) -> List[str]:
        tags = ["paper-import", candidate.source]
        if candidate.arxiv_id:
            tags.append("arxiv")
        if candidate.year:
            tags.append(str(candidate.year))
            if candidate.year >= datetime.now(timezone.utc).year - 2:
                tags.append("recent-paper")
        if candidate.venue:
            venue_tag = self._normalize_match_text(candidate.venue).replace(" ", "-")
            if venue_tag:
                tags.append(venue_tag[:40])
        deduped: List[str] = []
        for tag in tags:
            normalized = tag.strip().lower()
            if normalized and normalized not in deduped:
                deduped.append(normalized)
        return deduped

    @staticmethod
    def _build_paper_import_content(candidate: PaperImportCandidate) -> str:
        lines = [f"Paper title: {candidate.title}"]
        if candidate.authors:
            lines.append(f"Authors: {', '.join(candidate.authors)}")
        if candidate.year:
            lines.append(f"Year: {candidate.year}")
        if candidate.venue:
            lines.append(f"Venue: {candidate.venue}")
        if candidate.doi:
            lines.append(f"DOI: {candidate.doi}")
        if candidate.arxiv_id:
            lines.append(f"arXiv: {candidate.arxiv_id}")
        if candidate.source_url:
            lines.append(f"Landing page: {candidate.source_url}")
        if candidate.pdf_url:
            lines.append(f"PDF: {candidate.pdf_url}")

        abstract = " ".join(candidate.abstract.split())
        if abstract:
            lines.extend(["", "Abstract:", abstract])
        else:
            lines.extend(["", "Abstract:", "No abstract was available from the upstream metadata source."])

        return "\n".join(lines)

    def _maybe_index_document(self, document: KnowledgeDocument) -> None:
        """Index a document, using async if an event loop is running, else sync."""
        if self.async_indexing:
            try:
                loop = asyncio.get_running_loop()
                asyncio.create_task(self._index_document_async(document))
                return
            except RuntimeError:
                pass  # no running event loop, fall through to sync
        self._index_document(document)

    async def _index_document_async(self, document: KnowledgeDocument) -> None:
        """异步索引文档（避免阻塞主线程）。"""
        await asyncio.to_thread(self._index_document, document)

    def _index_document(self, document: KnowledgeDocument) -> None:
        """同步索引：分块 → embedding → 存入向量库。"""
        metadata = {
            "document_id": document.document_id,
            "title": document.title,
            "source_task_id": document.source_task_id,
            "tags": document.tags,
            "created_at": document.metadata.get("created_at"),
            "conversation_id": document.metadata.get("conversation_id"),
            "source_type": document.metadata.get("source_type"),
        }
        chunks = self.chunker.chunk(document.content, metadata)
        if not chunks:
            return
        chunk_texts = [c.content for c in chunks]
        vectors = self.embedder.embed(chunk_texts)
        self.vector_store.add(chunks, vectors)

    def reindex_all(self) -> None:
        """重新索引仓库中所有文档（幂等操作）。"""
        for doc in self.repository.list_all():
            self._index_document(doc)

    # ------------------------------------------------------------------------
    # 检索方法
    # ------------------------------------------------------------------------

    def retrieve_by_tags(self, tags: List[str], limit: int = 10) -> List[KnowledgeDocument]:
        """
        按标签检索文档（至少包含一个 tag）。

        Args:
            tags: 标签列表
            limit: 返回数量上限

        Returns:
            匹配的 KnowledgeDocument 列表
        """
        return self.repository.list_by_tags(tags, limit)

    def search_by_keyword(
        self, keyword: str, limit: int = 10, min_score: float = 0.0
    ) -> List[KnowledgeDocument]:
        """
        关键词检索（不区分大小写，按相关性评分排序）。

        Args:
            keyword: 关键词（支持多词，空格分隔）
            limit: 返回数量上限
            min_score: 最低分数阈值（低于此分的文档不返回）

        Returns:
            匹配的 KnowledgeDocument 列表（按分数降序）
        """
        scored = self._score_documents_by_keyword(keyword, min_score=min_score)
        return [doc for _, doc in scored[:limit]]

    def retrieve_hits_for_context(
        self,
        query: str,
        *,
        top_k: int = 5,
        max_chars_per_doc: int = 300,
        knowledge_scope: str = "shared",
        conversation_id: str | None = None,
    ) -> list[KnowledgeHit]:
        """
        Retrieve structured knowledge hits for context assembly.

        Scope semantics:
        - none: disable knowledge retrieval
        - conversation_only: only documents owned by the current conversation
        - shared: current conversation documents plus explicitly global documents

        Documents owned by another conversation are never visible.
        """
        normalized_scope = self._normalize_knowledge_scope(knowledge_scope)
        if normalized_scope == "none":
            return []

        search_limit = max(top_k * (8 if normalized_scope == "conversation_only" else 4), top_k)
        hybrid_results = self.retrieve(
            query,
            top_k=search_limit,
            hybrid=self.enable_hybrid_search,
            use_reranker=False,
        )
        hits = self._hits_from_search_results(
            hybrid_results,
            top_k=top_k,
            max_chars_per_doc=max_chars_per_doc,
            knowledge_scope=normalized_scope,
            conversation_id=conversation_id,
        )

        if len(hits) >= top_k:
            return hits[:top_k]

        existing_doc_ids = {hit.document_id for hit in hits}
        scored_docs = self._score_documents_by_keyword(query, min_score=0.5)
        filtered_docs = self._filter_scored_documents_for_scope(
            scored_docs[: max(search_limit * 2, top_k)],
            knowledge_scope=normalized_scope,
            conversation_id=conversation_id,
        )

        for score, doc in filtered_docs:
            if doc.document_id in existing_doc_ids:
                continue
            normalized_keyword_score = min(float(score) / 8.0, 1.0)
            hits.append(
                KnowledgeHit(
                    document_id=doc.document_id,
                    title=doc.title.strip(),
                    snippet=self._build_document_excerpt(doc, max_chars=max_chars_per_doc),
                    score=round(normalized_keyword_score, 3),
                    scope=self._document_scope(doc, conversation_id=conversation_id),
                    source_task_id=doc.source_task_id,
                    source_type=str(doc.metadata.get("source_type", "")),
                    evidence_level=self._knowledge_evidence_level(
                        document=doc,
                        aggregate_score=normalized_keyword_score,
                        matched_chunk_count=1,
                    ),
                    matched_chunk_count=1,
                    supporting_snippets=[self._build_document_excerpt(doc, max_chars=max(max_chars_per_doc, 1200))],
                )
            )
            existing_doc_ids.add(doc.document_id)
            if len(hits) >= top_k:
                break
        return hits

    def retrieve_for_context(
        self,
        query: str,
        *,
        top_k: int = 5,
        max_chars_per_doc: int = 300,
        knowledge_scope: str = "shared",
        conversation_id: str | None = None,
    ) -> list[str]:
        """
        检索相关知识并格式化为可注入上下文的文本片段。

        Args:
            query: 查询字符串（用户消息 + 主题）
            top_k: 最多返回的知识片段数
            max_chars_per_doc: 每个知识文档的摘要最大字符数

        Returns:
            格式化的知识上下文字符串列表，如 ["[Knowledge] DocTitle: excerpt...", ...]
        """
        hits = self.retrieve_hits_for_context(
            query,
            top_k=top_k,
            max_chars_per_doc=max_chars_per_doc,
            knowledge_scope=knowledge_scope,
            conversation_id=conversation_id,
        )
        return [self.format_hit_for_context(hit) for hit in hits]

    def format_hit_for_context(self, hit: KnowledgeHit) -> str:
        source_tag = ""
        if hit.source_task_id:
            source_tag = f" [task:{hit.source_task_id[:8]}]"
        elif hit.source_type == "user_import":
            source_tag = " [imported]"
        elif hit.scope == "conversation":
            source_tag = " [conversation]"
        return f"[Knowledge]{source_tag} {hit.title}: {hit.snippet}"

    def vector_search(
        self,
        query: str,
        top_k: int = 5,
        tags: List[str] | None = None
    ) -> List[SearchResult]:
        """
        纯向量检索。

        Args:
            query: 查询字符串
            top_k: 返回结果数量
            tags: 标签过滤（只返回包含任一 tag 的文档块）

        Returns:
            SearchResult 列表，按分数降序排列
        """
        query_vector = self.embedder.embed([query])[0]
        chunks_with_scores = self.vector_store.similarity_search(
            query_vector, top_k, filter_tags=tags
        )
        return [
            SearchResult(chunk=c, score=s, rank=i + 1)
            for i, (c, s) in enumerate(chunks_with_scores)
        ]

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        tags: List[str] | None = None,
        hybrid: Optional[bool] = None,
        keyword_weight: Optional[float] = None,
        vector_weight: Optional[float] = None,
        use_reranker: bool = True
    ) -> List[SearchResult]:
        """
        统一检索入口（支持混合检索 + 重排序）。

        Args:
            query: 查询字符串
            top_k: 最终返回数量
            tags: 标签过滤（只返回包含任一 tag 的文档块）
            hybrid: 是否启用混合检索（默认使用实例配置）
            keyword_weight: 关键词检索权重（覆盖实例配置）
            vector_weight: 向量检索权重（覆盖实例配置）
            use_reranker: 是否使用重排序器

        Returns:
            SearchResult 列表，按综合分数降序排列
        """
        if hybrid is None:
            hybrid = self.enable_hybrid_search

        # 1. 向量检索（获取更多候选，用于混合）
        query_vector = self.embedder.embed([query])[0]
        candidate_k = top_k * 3 if hybrid else top_k
        vector_results = self.vector_store.similarity_search(
            query_vector, candidate_k, filter_tags=tags
        )
        # 转为 dict: chunk_id -> (score, chunk)
        vec_map = {chunk.chunk_id: (score, chunk) for chunk, score in vector_results}

        if not hybrid:
            # 纯向量检索
            results = [
                SearchResult(chunk=c, score=s, rank=i + 1)
                for i, (c, s) in enumerate(vector_results[:top_k])
            ]
            if use_reranker:
                results = self._apply_reranker(query, results)
            return results

        # 2. 关键词检索（获取文档级分数，再映射到块）
        kw_candidates = self.search_by_keyword(query, limit=candidate_k)
        kw_doc_scores = {}
        for doc in kw_candidates:
            score = 0
            if query.lower() in doc.title.lower():
                score += 3
            if query.lower() in doc.content.lower():
                score += 1
            kw_doc_scores[doc.document_id] = score

        # 3. 融合分数（归一化）
        w_k = keyword_weight if keyword_weight is not None else self.keyword_weight
        w_v = vector_weight if vector_weight is not None else self.vector_weight
        total = w_k + w_v
        if total == 0:
            w_k = w_v = 0.5
        else:
            w_k /= total
            w_v /= total

        combined = []
        for chunk_id, (vec_score, chunk) in vec_map.items():
            # 向量分数已经在 [0,1] 范围（余弦相似度）
            kw_score = min(kw_doc_scores.get(chunk.document_id, 0) / 5.0, 1.0)
            hybrid_score = w_v * vec_score + w_k * kw_score
            combined.append((chunk, hybrid_score))

        combined.sort(key=lambda x: x[1], reverse=True)
        results = [
            SearchResult(chunk=c, score=s, rank=i + 1)
            for i, (c, s) in enumerate(combined[:top_k])
        ]

        if use_reranker:
            results = self._apply_reranker(query, results)
        return results

    def _apply_reranker(self, query: str, results: List[SearchResult]) -> List[SearchResult]:
        """使用重排序器重新计算分数并排序。"""
        if not results:
            return results
        docs = [r.chunk.content for r in results]
        rerank_scores = self.reranker.rerank(query, docs)
        for i, r in enumerate(results):
            r.score = rerank_scores[i]
        results.sort(key=lambda x: x.score, reverse=True)
        for i, r in enumerate(results):
            r.rank = i + 1
        return results

    # ------------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------------

    def _score_documents_by_keyword(
        self,
        keyword: str,
        *,
        min_score: float = 0.0,
    ) -> list[tuple[float, KnowledgeDocument]]:
        query_words = [w.strip().lower() for w in keyword.split() if len(w.strip()) >= 2]
        if not query_words:
            return []

        scored: list[tuple[float, KnowledgeDocument]] = []
        for doc in self.repository.list_all():
            title_lower = doc.title.lower()
            content_lower = doc.content.lower()
            tags_lower = [t.lower() for t in (doc.tags or [])]

            score = 0.0
            for word in query_words:
                if word == title_lower:
                    score += 5.0
                elif word in title_lower:
                    score += 3.0
                if word in content_lower:
                    score += 1.0
                for tag in tags_lower:
                    if word in tag:
                        score += 2.0
                        break

            content_len = max(1, len(content_lower))
            length_penalty = min(1.0, 500.0 / content_len)
            score *= length_penalty

            if score > 0 and score >= min_score:
                scored.append((score, doc))

        scored.sort(key=lambda item: item[0], reverse=True)
        return scored

    def _hits_from_search_results(
        self,
        results: List[SearchResult],
        *,
        top_k: int,
        max_chars_per_doc: int,
        knowledge_scope: str,
        conversation_id: str | None,
    ) -> list[KnowledgeHit]:
        doc_cache: dict[str, KnowledgeDocument | None] = {}
        grouped_results: dict[str, list[SearchResult]] = {}

        for result in results:
            document_id = str(getattr(result.chunk, "document_id", "") or "").strip()
            if not document_id:
                continue

            if document_id not in doc_cache:
                doc_cache[document_id] = self.repository.get(document_id)
            document = doc_cache[document_id]
            if document is None:
                continue

            if not self._document_visible_for_scope(
                document,
                knowledge_scope=knowledge_scope,
                conversation_id=conversation_id,
            ):
                continue

            grouped_results.setdefault(document.document_id, []).append(result)

        aggregated_hits: list[KnowledgeHit] = []
        for document_id, doc_results in grouped_results.items():
            document = doc_cache.get(document_id)
            if document is None:
                continue

            top_results = sorted(doc_results, key=lambda item: item.score, reverse=True)[:3]
            supporting_snippets = self._unique_supporting_snippets(
                [
                    self._build_chunk_excerpt(
                        getattr(item.chunk, "content", "") or "",
                        max_chars=max(max_chars_per_doc, 1200),
                    )
                    for item in top_results
                ]
            )
            primary_snippet = (
                supporting_snippets[0]
                if supporting_snippets
                else self._build_document_excerpt(document, max_chars=max_chars_per_doc)
            )
            aggregate_score = self._aggregate_document_relevance(top_results)
            aggregated_hits.append(
                KnowledgeHit(
                    document_id=document.document_id,
                    title=document.title.strip(),
                    snippet=primary_snippet,
                    score=round(aggregate_score, 3),
                    scope=self._document_scope(document, conversation_id=conversation_id),
                    source_task_id=document.source_task_id,
                    source_type=str(document.metadata.get("source_type", "")),
                    evidence_level=self._knowledge_evidence_level(
                        document=document,
                        aggregate_score=aggregate_score,
                        matched_chunk_count=len(supporting_snippets) or len(top_results),
                    ),
                    matched_chunk_count=len(supporting_snippets) or len(top_results),
                    supporting_snippets=supporting_snippets,
                )
            )

        ordered_hits = sorted(aggregated_hits, key=lambda hit: hit.score, reverse=True)
        return ordered_hits[:top_k]

    @staticmethod
    def _aggregate_document_relevance(results: List[SearchResult]) -> float:
        if not results:
            return 0.0
        top_score = max(float(item.score) for item in results)
        if len(results) == 1:
            return min(top_score, 1.0)
        remaining = [float(item.score) for item in results if float(item.score) != top_score]
        avg_remaining = sum(remaining) / len(remaining) if remaining else top_score
        aggregate = top_score * 0.75 + avg_remaining * 0.25 + min(0.05 * (len(results) - 1), 0.1)
        return min(aggregate, 1.0)

    def _knowledge_evidence_level(
        self,
        *,
        document: KnowledgeDocument,
        aggregate_score: float,
        matched_chunk_count: int,
    ) -> str:
        source_type = str(document.metadata.get("source_type", "") or "").strip().lower()
        confidence = max(0.0, min(float(aggregate_score), 1.0))

        if source_type in {"paper_import", "workspace_summary"}:
            confidence += 0.12
        elif source_type == "user_import":
            confidence += 0.06

        if matched_chunk_count >= 2:
            confidence += 0.08
        if matched_chunk_count >= 3:
            confidence += 0.04

        confidence = min(confidence, 1.0)
        if confidence >= 0.82:
            return "strong"
        if confidence >= 0.62:
            return "moderate"
        return "candidate"

    @staticmethod
    def _unique_supporting_snippets(snippets: List[str], *, limit: int = 3) -> list[str]:
        values: list[str] = []
        seen: set[str] = set()
        for snippet in snippets:
            normalized = " ".join((snippet or "").split()).strip()
            if not normalized:
                continue
            key = normalized.casefold()
            if key in seen:
                continue
            seen.add(key)
            values.append(normalized)
            if len(values) >= limit:
                break
        return values

    def _filter_scored_documents_for_scope(
        self,
        scored_docs: list[tuple[float, KnowledgeDocument]],
        *,
        knowledge_scope: str,
        conversation_id: str | None,
    ) -> list[tuple[float, KnowledgeDocument]]:
        normalized_scope = self._normalize_knowledge_scope(knowledge_scope)
        return [
            (score, doc)
            for score, doc in scored_docs
            if self._document_visible_for_scope(
                doc,
                knowledge_scope=normalized_scope,
                conversation_id=conversation_id,
            )
        ]

    @staticmethod
    def _normalize_knowledge_scope(knowledge_scope: str | None) -> str:
        if knowledge_scope in {"none", "conversation_only", "shared"}:
            return str(knowledge_scope)
        return "shared"

    def _document_scope(self, document: KnowledgeDocument, *, conversation_id: str | None) -> str:
        return "conversation" if self._document_matches_conversation(document, conversation_id=conversation_id) else "shared"

    def _document_visible_for_scope(
        self,
        document: KnowledgeDocument,
        *,
        knowledge_scope: str,
        conversation_id: str | None,
    ) -> bool:
        normalized_scope = self._normalize_knowledge_scope(knowledge_scope)
        if normalized_scope == "none":
            return False

        owner_conversation_id = self._document_conversation_id(document)
        if normalized_scope == "conversation_only":
            return bool(
                conversation_id
                and owner_conversation_id
                and owner_conversation_id == conversation_id
            )

        # "shared" means global knowledge plus the active research corpus.
        # A private document from another conversation must never leak in.
        return not owner_conversation_id or owner_conversation_id == conversation_id

    def _document_matches_conversation(
        self,
        document: KnowledgeDocument,
        *,
        conversation_id: str | None,
    ) -> bool:
        if not conversation_id:
            return False

        return self._document_conversation_id(document) == conversation_id

    def _document_conversation_id(self, document: KnowledgeDocument) -> str:
        metadata_conversation_id = str(document.metadata.get("conversation_id", "") or "").strip()
        if metadata_conversation_id:
            return metadata_conversation_id

        if not document.source_task_id or self.task_repository is None:
            return ""

        task = self.task_repository.get(document.source_task_id)
        return str(task.conversation_id).strip() if task else ""

    @staticmethod
    def _build_document_excerpt(document: KnowledgeDocument, *, max_chars: int) -> str:
        content = " ".join((document.content or "").split())
        excerpt = content[:max_chars]
        if len(content) > max_chars:
            excerpt += "..."
        return excerpt

    @staticmethod
    def _build_chunk_excerpt(content: str, *, max_chars: int) -> str:
        normalized = " ".join((content or "").split())
        if not normalized:
            return ""
        excerpt = normalized[:max_chars]
        if len(normalized) > max_chars:
            excerpt += "..."
        return excerpt

    def get_document(self, document_id: str) -> Optional[KnowledgeDocument]:
        """根据文档 ID 获取原始文档。"""
        return self.repository.get(document_id)

    def delete_document(self, document_id: str) -> bool:
        """
        删除文档及其所有索引块。

        Args:
            document_id: 文档 ID

        Returns:
            是否删除成功
        """
        doc = self.repository.get(document_id)
        if not doc:
            return False
        # 从向量存储中删除相关块
        self.vector_store.delete_by_document_id(document_id)
        # 从仓库中删除（需要 repository 支持 delete）
        return self.repository.delete(document_id)

    def list_documents(self) -> List[KnowledgeDocument]:
        """List documents in reverse created_at order for predictable UI rendering."""
        documents = self.repository.list_all()
        documents.sort(key=lambda item: item.metadata.get("created_at", ""), reverse=True)
        return documents
