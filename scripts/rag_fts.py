from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from rag_common import jsonl_read
from rag_metadata import enrich_chunk_metadata


SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    chunk_id UNINDEXED,
    relative_path,
    text,
    doc_type,
    source_kind,
    section,
    requirement_id,
    tokenize = 'unicode61 remove_diacritics 2'
);
"""


INSERT_SQL = """
INSERT INTO chunks_fts (
    chunk_id,
    relative_path,
    text,
    doc_type,
    source_kind,
    section,
    requirement_id
)
VALUES (?, ?, ?, ?, ?, ?, ?)
"""


SEARCH_SQL = """
SELECT
    chunk_id,
    relative_path,
    text,
    doc_type,
    source_kind,
    section,
    requirement_id,
    bm25(chunks_fts) AS score
FROM chunks_fts
WHERE chunks_fts MATCH ?
ORDER BY score
LIMIT ?
"""


class FTSIndex:
    def __init__(self, db_path: Path):
        self.db_path = db_path

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def exists(self) -> bool:
        return self.db_path.exists()

    def rebuild(self, chunks_path: Path) -> dict[str, Any]:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = self.connect()
        cur = conn.cursor()
        cur.execute("DROP TABLE IF EXISTS chunks_fts")
        cur.execute(SCHEMA)

        inserted = 0
        for row in jsonl_read(chunks_path):
            enriched = enrich_chunk_metadata(row)
            cur.execute(
                INSERT_SQL,
                (
                    enriched.get("chunk_id"),
                    enriched.get("relative_path"),
                    enriched.get("text"),
                    enriched.get("doc_type"),
                    enriched.get("source_kind"),
                    enriched.get("section"),
                    enriched.get("requirement_id"),
                ),
            )
            inserted += 1

        conn.commit()
        conn.close()

        return {
            "status": "ok",
            "inserted": inserted,
            "db_path": str(self.db_path),
        }

    def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        conn = self.connect()
        cur = conn.cursor()
        rows = cur.execute(SEARCH_SQL, (query, limit)).fetchall()
        conn.close()

        results: list[dict[str, Any]] = []
        for row in rows:
            results.append(
                {
                    "chunk_id": row["chunk_id"],
                    "relative_path": row["relative_path"],
                    "document": row["text"],
                    "score": float(abs(row["score"])),
                    "metadata": {
                        "relative_path": row["relative_path"],
                        "doc_type": row["doc_type"],
                        "source_kind": row["source_kind"],
                        "section": row["section"],
                        "requirement_id": row["requirement_id"],
                        "retrieval": "sqlite_fts5_bm25",
                    },
                }
            )
        return results
