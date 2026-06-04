from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from product_agent.domain import (
    Conversation,
    ConversationWorkingMemory,
    GapRecord,
    KnowledgeDocument,
    MessageRecord,
    PaperRecord,
    ResearchIdeaRecord,
    ResearchTask,
    ResearchWorkspace,
    SkillDescriptor,
)

from .sqlite_db import SQLiteDatabase


def _dump_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _load_json(value: str) -> Any:
    return json.loads(value) if value else None


def _dump_datetime(value: datetime) -> str:
    return value.isoformat()


def _load_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


class SQLiteConversationRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def create(self, conversation: Conversation) -> Conversation:
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO conversations (
                    conversation_id, title, topic, status, message_ids_json,
                    latest_task_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    conversation.conversation_id,
                    conversation.title,
                    conversation.topic,
                    conversation.status,
                    _dump_json(list(conversation.message_ids)),
                    conversation.latest_task_id,
                    _dump_datetime(conversation.created_at),
                    _dump_datetime(conversation.updated_at),
                ),
            )
            connection.commit()
        return conversation

    def get(self, conversation_id: str) -> Conversation | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM conversations WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_entity(row)

    def update(self, conversation: Conversation) -> Conversation:
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE conversations
                SET title = ?, topic = ?, status = ?, message_ids_json = ?,
                    latest_task_id = ?, created_at = ?, updated_at = ?
                WHERE conversation_id = ?
                """,
                (
                    conversation.title,
                    conversation.topic,
                    conversation.status,
                    _dump_json(list(conversation.message_ids)),
                    conversation.latest_task_id,
                    _dump_datetime(conversation.created_at),
                    _dump_datetime(conversation.updated_at),
                    conversation.conversation_id,
                ),
            )
            connection.commit()
        return conversation

    def list_all(self) -> list[Conversation]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM conversations ORDER BY updated_at DESC"
            ).fetchall()
        return [self._row_to_entity(row) for row in rows]

    def delete(self, conversation_id: str) -> bool:
        with self.database.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM conversations WHERE conversation_id = ?",
                (conversation_id,),
            )
            connection.commit()
        return cursor.rowcount > 0

    @staticmethod
    def _row_to_entity(row) -> Conversation:
        return Conversation(
            conversation_id=row["conversation_id"],
            title=row["title"],
            topic=row["topic"],
            status=row["status"],
            message_ids=list(_load_json(row["message_ids_json"]) or []),
            latest_task_id=row["latest_task_id"],
            created_at=_load_datetime(row["created_at"]),
            updated_at=_load_datetime(row["updated_at"]),
        )


class SQLiteMessageRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def create(self, message: MessageRecord) -> MessageRecord:
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO messages (
                    message_id, conversation_id, role, content, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    message.message_id,
                    message.conversation_id,
                    message.role,
                    message.content,
                    _dump_json(message.metadata),
                    _dump_datetime(message.created_at),
                ),
            )
            connection.commit()
        return message

    def list_by_conversation(self, conversation_id: str) -> list[MessageRecord]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM messages
                WHERE conversation_id = ?
                ORDER BY created_at ASC
                """,
                (conversation_id,),
            ).fetchall()
        return [self._row_to_entity(row) for row in rows]

    def delete_by_conversation(self, conversation_id: str) -> int:
        with self.database.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM messages WHERE conversation_id = ?",
                (conversation_id,),
            )
            connection.commit()
        return cursor.rowcount

    @staticmethod
    def _row_to_entity(row) -> MessageRecord:
        return MessageRecord(
            message_id=row["message_id"],
            conversation_id=row["conversation_id"],
            role=row["role"],
            content=row["content"],
            metadata=dict(_load_json(row["metadata_json"]) or {}),
            created_at=_load_datetime(row["created_at"]),
        )


class SQLiteResearchTaskRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def create(self, task: ResearchTask) -> ResearchTask:
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO research_tasks (
                    task_id, conversation_id, topic, status, trigger_message_id,
                    mode, knowledge_scope, selected_skill_ids_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task.task_id,
                    task.conversation_id,
                    task.topic,
                    task.status,
                    task.trigger_message_id,
                    task.mode,
                    task.knowledge_scope,
                    _dump_json(list(task.selected_skill_ids)),
                    _dump_datetime(task.created_at),
                    _dump_datetime(task.updated_at),
                ),
            )
            connection.commit()
        return task

    def get(self, task_id: str) -> ResearchTask | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM research_tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_entity(row)

    def update(self, task: ResearchTask) -> ResearchTask:
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE research_tasks
                SET conversation_id = ?, topic = ?, status = ?, trigger_message_id = ?,
                    mode = ?, knowledge_scope = ?, selected_skill_ids_json = ?,
                    created_at = ?, updated_at = ?
                WHERE task_id = ?
                """,
                (
                    task.conversation_id,
                    task.topic,
                    task.status,
                    task.trigger_message_id,
                    task.mode,
                    task.knowledge_scope,
                    _dump_json(list(task.selected_skill_ids)),
                    _dump_datetime(task.created_at),
                    _dump_datetime(task.updated_at),
                    task.task_id,
                ),
            )
            connection.commit()
        return task

    def list_all(self) -> list[ResearchTask]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM research_tasks ORDER BY updated_at DESC"
            ).fetchall()
        return [self._row_to_entity(row) for row in rows]

    def delete_by_conversation(self, conversation_id: str) -> list[str]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT task_id FROM research_tasks WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchall()
            task_ids = [str(row["task_id"]) for row in rows]
            connection.execute(
                "DELETE FROM research_tasks WHERE conversation_id = ?",
                (conversation_id,),
            )
            connection.commit()
        return task_ids

    @staticmethod
    def _row_to_entity(row) -> ResearchTask:
        return ResearchTask(
            task_id=row["task_id"],
            conversation_id=row["conversation_id"],
            topic=row["topic"],
            status=row["status"],
            trigger_message_id=row["trigger_message_id"],
            mode=row["mode"],
            knowledge_scope=(
                row["knowledge_scope"]
                if "knowledge_scope" in row.keys() and row["knowledge_scope"]
                else "shared"
            ),
            selected_skill_ids=list(
                _load_json(row["selected_skill_ids_json"]) or []
            ) if "selected_skill_ids_json" in row.keys() else [],
            created_at=_load_datetime(row["created_at"]),
            updated_at=_load_datetime(row["updated_at"]),
        )


class SQLiteWorkspaceRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def save(self, workspace: ResearchWorkspace) -> ResearchWorkspace:
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO workspaces (
                    task_id, topic, summary, summary_payload_json, papers_json,
                    taxonomy_json, graph_edges_json, gaps_json, ideas_json,
                    alignment_score, trace_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    topic = excluded.topic,
                    summary = excluded.summary,
                    summary_payload_json = excluded.summary_payload_json,
                    papers_json = excluded.papers_json,
                    taxonomy_json = excluded.taxonomy_json,
                    graph_edges_json = excluded.graph_edges_json,
                    gaps_json = excluded.gaps_json,
                    ideas_json = excluded.ideas_json,
                    alignment_score = excluded.alignment_score,
                    trace_json = excluded.trace_json
                """,
                (
                    workspace.task_id,
                    workspace.topic,
                    workspace.summary,
                    _dump_json(workspace.summary_payload),
                    _dump_json([self._paper_to_dict(item) for item in workspace.papers]),
                    _dump_json(workspace.taxonomy),
                    _dump_json(workspace.graph_edges),
                    _dump_json([self._gap_to_dict(item) for item in workspace.gaps]),
                    _dump_json([self._idea_to_dict(item) for item in workspace.ideas]),
                    workspace.alignment_score,
                    _dump_json(workspace.trace),
                ),
            )
            connection.commit()
        return workspace

    def get_by_task(self, task_id: str) -> ResearchWorkspace | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM workspaces WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_entity(row)

    def delete_by_task_ids(self, task_ids: list[str]) -> int:
        if not task_ids:
            return 0
        placeholders = ",".join("?" for _ in task_ids)
        with self.database.connect() as connection:
            cursor = connection.execute(
                f"DELETE FROM workspaces WHERE task_id IN ({placeholders})",
                tuple(task_ids),
            )
            connection.commit()
        return cursor.rowcount

    @classmethod
    def _row_to_entity(cls, row) -> ResearchWorkspace:
        return ResearchWorkspace(
            task_id=row["task_id"],
            topic=row["topic"],
            summary=row["summary"],
            summary_payload=dict(_load_json(row["summary_payload_json"]) or {}),
            papers=[
                PaperRecord(**item) for item in (_load_json(row["papers_json"]) or [])
            ],
            taxonomy=dict(_load_json(row["taxonomy_json"]) or {}),
            graph_edges=list(_load_json(row["graph_edges_json"]) or []),
            gaps=[
                GapRecord(**item) for item in (_load_json(row["gaps_json"]) or [])
            ],
            ideas=[
                ResearchIdeaRecord(**item) for item in (_load_json(row["ideas_json"]) or [])
            ],
            alignment_score=float(row["alignment_score"]),
            trace=dict(_load_json(row["trace_json"]) or {}),
        )

    @staticmethod
    def _paper_to_dict(paper: PaperRecord) -> dict[str, Any]:
        return {
            "paper_id": paper.paper_id,
            "title": paper.title,
            "abstract": paper.abstract,
            "authors": list(paper.authors),
            "keywords": list(paper.keywords),
            "publish_date": paper.publish_date,
            "source": paper.source,
            "taxonomy_category": paper.taxonomy_category,
            "citation_count": paper.citation_count,
            "url": paper.url,
            "is_new_this_round": bool(getattr(paper, "is_new_this_round", False)),
        }

    @staticmethod
    def _gap_to_dict(gap: GapRecord) -> dict[str, Any]:
        return {
            "gap_id": gap.gap_id,
            "task_id": gap.task_id,
            "summary": gap.summary,
            "severity": gap.severity,
            "evidence": list(gap.evidence),
        }

    @staticmethod
    def _idea_to_dict(idea: ResearchIdeaRecord) -> dict[str, Any]:
        return {
            "idea_id": idea.idea_id,
            "task_id": idea.task_id,
            "title": idea.title,
            "motivation": idea.motivation,
            "approach": idea.approach,
            "feasibility": idea.feasibility,
            "contribution": idea.contribution,
            "related_papers": list(idea.related_papers),
            "derived_from_gaps": list(idea.derived_from_gaps),
            "confidence": idea.confidence,
            "tags": list(idea.tags),
            "raw_text": idea.raw_text,
        }


class SQLiteWorkingMemoryRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def save(self, memory: ConversationWorkingMemory) -> ConversationWorkingMemory:
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO conversation_working_memory (
                    conversation_id, current_focus, summary, stable_findings_json,
                    open_questions_json, active_constraints_json, supporting_task_ids_json,
                    source_task_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(conversation_id) DO UPDATE SET
                    current_focus = excluded.current_focus,
                    summary = excluded.summary,
                    stable_findings_json = excluded.stable_findings_json,
                    open_questions_json = excluded.open_questions_json,
                    active_constraints_json = excluded.active_constraints_json,
                    supporting_task_ids_json = excluded.supporting_task_ids_json,
                    source_task_id = excluded.source_task_id,
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at
                """,
                (
                    memory.conversation_id,
                    memory.current_focus,
                    memory.summary,
                    _dump_json(list(memory.stable_findings)),
                    _dump_json(list(memory.open_questions)),
                    _dump_json(list(memory.active_constraints)),
                    _dump_json(list(memory.supporting_task_ids)),
                    memory.source_task_id,
                    _dump_datetime(memory.created_at),
                    _dump_datetime(memory.updated_at),
                ),
            )
            connection.commit()
        return memory

    def get(self, conversation_id: str) -> ConversationWorkingMemory | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM conversation_working_memory WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_entity(row)

    def delete(self, conversation_id: str) -> bool:
        with self.database.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM conversation_working_memory WHERE conversation_id = ?",
                (conversation_id,),
            )
            connection.commit()
        return cursor.rowcount > 0

    @staticmethod
    def _row_to_entity(row) -> ConversationWorkingMemory:
        return ConversationWorkingMemory(
            conversation_id=row["conversation_id"],
            current_focus=row["current_focus"],
            summary=row["summary"],
            stable_findings=list(_load_json(row["stable_findings_json"]) or []),
            open_questions=list(_load_json(row["open_questions_json"]) or []),
            active_constraints=list(_load_json(row["active_constraints_json"]) or []),
            supporting_task_ids=list(_load_json(row["supporting_task_ids_json"]) or []),
            source_task_id=row["source_task_id"],
            created_at=_load_datetime(row["created_at"]),
            updated_at=_load_datetime(row["updated_at"]),
        )


class SQLiteKnowledgeRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def save(self, document: KnowledgeDocument) -> KnowledgeDocument:
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO knowledge_documents (
                    document_id, title, source_task_id, content, tags_json, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(document_id) DO UPDATE SET
                    title = excluded.title,
                    source_task_id = excluded.source_task_id,
                    content = excluded.content,
                    tags_json = excluded.tags_json,
                    metadata_json = excluded.metadata_json
                """,
                (
                    document.document_id,
                    document.title,
                    document.source_task_id,
                    document.content,
                    _dump_json(document.tags),
                    _dump_json(document.metadata),
                ),
            )
            connection.commit()
        return document

    def list_all(self) -> list[KnowledgeDocument]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM knowledge_documents ORDER BY document_id ASC"
            ).fetchall()
        return [self._row_to_entity(row) for row in rows]

    def get(self, document_id: str) -> KnowledgeDocument | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM knowledge_documents WHERE document_id = ?",
                (document_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_entity(row)

    def list_by_tags(self, tags: list[str], limit: int) -> list[KnowledgeDocument]:
        if not tags:
            return self.list_all()[:limit]

        matched: list[KnowledgeDocument] = []
        for document in self.list_all():
            if any(tag in document.tags for tag in tags):
                matched.append(document)
            if len(matched) >= limit:
                break
        return matched

    def delete(self, document_id: str) -> bool:
        with self.database.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM knowledge_documents WHERE document_id = ?",
                (document_id,),
            )
            connection.commit()
        return cursor.rowcount > 0

    @staticmethod
    def _row_to_entity(row) -> KnowledgeDocument:
        return KnowledgeDocument(
            document_id=row["document_id"],
            title=row["title"],
            source_task_id=row["source_task_id"],
            content=row["content"],
            tags=list(_load_json(row["tags_json"]) or []),
            metadata=dict(_load_json(row["metadata_json"]) or {}),
        )


class SQLiteVectorStore:
    """
    SQLite 持久化向量存储。

    将文档块及其 embedding 向量持久化到 SQLite，
    服务重启后无需重新索引。支持余弦相似度检索和标签过滤。
    """

    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def add(self, chunks: list, vectors: list[list[float]]) -> None:
        """添加文档块及其向量。"""
        with self.database.connect() as connection:
            connection.executemany(
                """
                INSERT OR REPLACE INTO vector_chunks (
                    chunk_id, document_id, source_title, source_task_id,
                    content, start_idx, end_idx, tags_json, metadata_json, vector_blob
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        chunk.chunk_id,
                        chunk.document_id,
                        chunk.source_title,
                        chunk.source_task_id,
                        chunk.content,
                        chunk.start_idx,
                        chunk.end_idx,
                        _dump_json(chunk.tags),
                        _dump_json(chunk.metadata),
                        _dump_json(vector),
                    )
                    for chunk, vector in zip(chunks, vectors)
                ],
            )
            connection.commit()

    def similarity_search(
        self,
        query_vector: list[float],
        top_k: int,
        filter_tags: list[str] | None = None,
    ) -> list[tuple]:
        """向量相似度检索，可选标签过滤。返回 [(chunk, score), ...]。

        当前实现：加载所有向量，在 Python 中计算余弦相似度。
        适合中小规模知识库（<10万 chunks），大规模应换用专用向量库。
        """
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT chunk_id, document_id, source_title, source_task_id,
                       content, start_idx, end_idx, tags_json, metadata_json, vector_blob
                FROM vector_chunks
                """
            ).fetchall()

        scored = []
        for row in rows:
            # Tag filtering
            if filter_tags:
                stored_tags = set(_load_json(row["tags_json"]) or [])
                if not any(tag in stored_tags for tag in filter_tags):
                    continue

            vector_blob = row["vector_blob"]
            if not vector_blob:
                continue

            stored_vector = _load_json(vector_blob)
            sim = _cosine_similarity(query_vector, stored_vector)

            # Reconstruct a lightweight chunk-like object for API compatibility
            chunk = _VectorChunkProxy(
                chunk_id=row["chunk_id"],
                document_id=row["document_id"],
                source_title=row["source_title"],
                source_task_id=row["source_task_id"],
                content=row["content"],
                start_idx=row["start_idx"],
                end_idx=row["end_idx"],
                tags=_load_json(row["tags_json"]) or [],
                metadata=dict(_load_json(row["metadata_json"]) or {}),
            )
            scored.append((chunk, sim))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    def delete_by_document_id(self, document_id: str) -> None:
        """删除指定文档的所有块。"""
        with self.database.connect() as connection:
            connection.execute(
                "DELETE FROM vector_chunks WHERE document_id = ?",
                (document_id,),
            )
            connection.commit()

    def count(self) -> int:
        """返回向量块总数。"""
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS cnt FROM vector_chunks"
            ).fetchone()
            return row["cnt"] if row else 0


def _cosine_similarity(v1: list[float], v2: list[float]) -> float:
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = sum(a * a for a in v1) ** 0.5
    norm2 = sum(b * b for b in v2) ** 0.5
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


class _VectorChunkProxy:
    """轻量级代理，模拟 DocumentChunk 接口用于向上兼容。"""

    def __init__(self, **kwargs) -> None:
        self.chunk_id = kwargs["chunk_id"]
        self.document_id = kwargs["document_id"]
        self.source_title = kwargs["source_title"]
        self.source_task_id = kwargs["source_task_id"]
        self.content = kwargs["content"]
        self.start_idx = kwargs["start_idx"]
        self.end_idx = kwargs["end_idx"]
        self.tags = kwargs["tags"]
        self.metadata = kwargs["metadata"]


class SQLiteSkillRepository:
    """SQLite 持久化 skill 描述符。"""

    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def list_all(self) -> list[SkillDescriptor]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM skills ORDER BY created_at DESC"
            ).fetchall()
        return [self._row_to_entity(row) for row in rows]

    def get(self, skill_id: str) -> SkillDescriptor | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM skills WHERE skill_id = ?",
                (skill_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_entity(row)

    def save(self, descriptor: SkillDescriptor) -> SkillDescriptor:
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO skills (
                    skill_id, display_name, description, required_tools_json,
                    enabled, prompts_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    descriptor.skill_id,
                    descriptor.display_name,
                    descriptor.description,
                    _dump_json(list(descriptor.required_tools)),
                    1 if descriptor.enabled else 0,
                    _dump_json(dict(getattr(descriptor, "prompts", {}))),
                    _dump_datetime(getattr(descriptor, "created_at", datetime.now())),
                    _dump_datetime(getattr(descriptor, "updated_at", datetime.now())),
                ),
            )
            connection.commit()
        return descriptor

    def update(self, descriptor: SkillDescriptor) -> SkillDescriptor:
        return self.save(descriptor)

    def delete(self, skill_id: str) -> bool:
        with self.database.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM skills WHERE skill_id = ?",
                (skill_id,),
            )
            connection.commit()
        return cursor.rowcount > 0

    @staticmethod
    def _row_to_entity(row) -> SkillDescriptor:
        return SkillDescriptor(
            skill_id=row["skill_id"],
            display_name=row["display_name"],
            description=row["description"] or "",
            enabled=bool(row["enabled"]),
            required_tools=list(_load_json(row["required_tools_json"]) or []),
            prompts=dict(_load_json(row["prompts_json"]) or {}),
        )
