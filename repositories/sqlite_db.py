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
    CREATE TABLE IF NOT EXISTS knowledge_documents (
        document_id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        source_task_id TEXT,
        content TEXT NOT NULL,
        tags_json TEXT NOT NULL,
        metadata_json TEXT NOT NULL
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
            connection.commit()

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, detect_types=sqlite3.PARSE_DECLTYPES)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
        finally:
            connection.close()
