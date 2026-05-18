from __future__ import annotations

import asyncio
import math
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional, Protocol, Tuple
from uuid import uuid4

from product_agent.domain import KnowledgeDocument
from product_agent.repositories import KnowledgeRepository


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
    共享知识与后续 RAG 的统一入口。

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
        self.embedder = embedder or DummyEmbedder()
        self.vector_store = vector_store or InMemoryVectorStore()
        self.reranker = reranker or NoopReranker()
        self.enable_hybrid_search = enable_hybrid_search
        self.keyword_weight = keyword_weight
        self.vector_weight = vector_weight
        self.async_indexing = async_indexing


    def save_summary(
        self,
        *,
        title: str,
        content: str,
        source_task_id: str | None = None,
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
        document = KnowledgeDocument(
            document_id=f"doc_{uuid4().hex[:12]}",
            title=title,
            source_task_id=source_task_id,
            content=content,
            tags=tags or [],
            metadata={"created_at": datetime.now(UTC).isoformat()},
        )
        saved_doc = self.repository.save(document)
        if index_immediately:
            if self.async_indexing:
                asyncio.create_task(self._index_document_async(saved_doc))
            else:
                self._index_document(saved_doc)
        return saved_doc

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

    def search_by_keyword(self, keyword: str, limit: int = 10) -> List[KnowledgeDocument]:
        """
        简单关键词检索（不区分大小写）。

        Args:
            keyword: 关键词
            limit: 返回数量上限

        Returns:
            匹配的 KnowledgeDocument 列表
        """
        keyword_lower = keyword.lower()
        results = []
        for doc in self.repository.list_all():
            if keyword_lower in doc.title.lower() or keyword_lower in doc.content.lower():
                results.append(doc)
                if len(results) >= limit:
                    break
        return results

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

    def get_document(self, document_id: str) -> Optional[KnowledgeDocument]:
        """根据文档 ID 获取原始文档。"""
        return self.repository.get(document_id)

    def list_documents(self) -> List[KnowledgeDocument]:
        """列出所有原始文档（调试用）。"""
        return self.repository.list_all()

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
