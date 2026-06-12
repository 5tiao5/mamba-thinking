from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path


SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS conversations (
        conversation_id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        topic TEXT NOT NULL,
        status TEXT NOT NULL,
        message_ids_json TEXT NOT NULL,
        latest_task_id TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS messages (
        message_id TEXT PRIMARY KEY,
        conversation_id TEXT NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        metadata_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS research_tasks (
        task_id TEXT PRIMARY KEY,
        conversation_id TEXT NOT NULL,
        topic TEXT NOT NULL,
        status TEXT NOT NULL,
        trigger_message_id TEXT,
        mode TEXT NOT NULL,
        knowledge_scope TEXT NOT NULL DEFAULT 'shared',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS workspaces (
        task_id TEXT PRIMARY KEY,
        topic TEXT NOT NULL,
        summary TEXT NOT NULL,
        summary_payload_json TEXT NOT NULL,
        papers_json TEXT NOT NULL,
        taxonomy_json TEXT NOT NULL,
        graph_edges_json TEXT NOT NULL,
        gaps_json TEXT NOT NULL,
        ideas_json TEXT NOT NULL,
        alignment_score REAL NOT NULL,
        trace_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS conversation_working_memory (
        conversation_id TEXT PRIMARY KEY,
        current_focus TEXT NOT NULL,
        summary TEXT NOT NULL,
        stable_findings_json TEXT NOT NULL,
        open_questions_json TEXT NOT NULL,
        active_constraints_json TEXT NOT NULL,
        supporting_task_ids_json TEXT NOT NULL,
        source_task_id TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS knowledge_documents (
        document_id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        source_task_id TEXT,
        content TEXT NOT NULL,
        tags_json TEXT NOT NULL,
        metadata_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS conversation_research_papers (
        paper_entry_id TEXT PRIMARY KEY,
        conversation_id TEXT NOT NULL,
        document_id TEXT NOT NULL,
        canonical_key TEXT NOT NULL,
        title TEXT NOT NULL,
        origin TEXT NOT NULL,
        status TEXT NOT NULL,
        source_url TEXT NOT NULL,
        metadata_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(conversation_id, canonical_key),
        FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id),
        FOREIGN KEY (document_id) REFERENCES knowledge_documents(document_id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_conversation_research_papers_conversation
    ON conversation_research_papers(conversation_id, updated_at DESC)
    """,
    """
    CREATE TABLE IF NOT EXISTS vector_chunks (
        chunk_id TEXT PRIMARY KEY,
        document_id TEXT NOT NULL,
        source_title TEXT NOT NULL,
        source_task_id TEXT,
        content TEXT NOT NULL,
        start_idx INTEGER NOT NULL,
        end_idx INTEGER NOT NULL,
        tags_json TEXT NOT NULL,
        metadata_json TEXT NOT NULL,
        vector_blob BLOB
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_vector_chunks_document_id
    ON vector_chunks(document_id)
    """,
    """
    CREATE TABLE IF NOT EXISTS skills (
        skill_id TEXT PRIMARY KEY,
        display_name TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        required_tools_json TEXT NOT NULL DEFAULT '[]',
        enabled INTEGER NOT NULL DEFAULT 1,
        prompts_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
)


class SQLiteDatabase:
    """Lightweight SQLite helper for repository-backed local persistence."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def initialize(self) -> None:
        with self.connect() as connection:
            for statement in SCHEMA_STATEMENTS:
                connection.execute(statement)
            self._ensure_runtime_schema(connection)
            connection.commit()

    @staticmethod
    def _ensure_runtime_schema(connection) -> None:
        task_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(research_tasks)").fetchall()
        }
        if "knowledge_scope" not in task_columns:
            connection.execute(
                "ALTER TABLE research_tasks ADD COLUMN knowledge_scope TEXT NOT NULL DEFAULT 'shared'"
            )
        if "selected_skill_ids_json" not in task_columns:
            connection.execute(
                "ALTER TABLE research_tasks ADD COLUMN selected_skill_ids_json TEXT NOT NULL DEFAULT '[]'"
            )

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, detect_types=sqlite3.PARSE_DECLTYPES)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
        finally:
            connection.close()

