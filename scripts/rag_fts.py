from __future__ import annotations

import sqlite3
import re
import time
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


def build_match_query(query: str) -> str | None:
    terms = re.findall(r"[0-9A-Za-zА-Яа-яЁё]+", str(query or "").lower())
    unique_terms: list[str] = []
    seen: set[str] = set()
    for term in terms:
        if not term or term in seen:
            continue
        seen.add(term)
        unique_terms.append(term)
    if not unique_terms:
        return None
    return " OR ".join(f'"{term}"' for term in unique_terms)


class FTSIndex:
    def __init__(self, db_path: Path):
        self.db_path = db_path

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def exists(self) -> bool:
        return self.db_path.exists()

    def rebuild(self, chunks_path: Path, progress_every: int = 1000) -> dict[str, Any]:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.db_path.with_name(f"{self.db_path.name}.tmp")
        if tmp_path.exists():
            tmp_path.unlink()

        started = time.perf_counter()
        conn = sqlite3.connect(str(tmp_path))
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("PRAGMA journal_mode=OFF")
        cur.execute("PRAGMA synchronous=OFF")
        cur.execute("PRAGMA temp_store=MEMORY")
        cur.execute(SCHEMA)

        inserted = 0
        try:
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
                if progress_every > 0 and inserted % progress_every == 0:
                    elapsed = time.perf_counter() - started
                    print(f"FTS rebuild: inserted={inserted}, elapsed={elapsed:.1f}s", flush=True)

            conn.commit()
        finally:
            conn.close()

        tmp_path.replace(self.db_path)
        elapsed = time.perf_counter() - started

        return {
            "status": "ok",
            "inserted": inserted,
            "db_path": str(self.db_path),
            "elapsed_sec": round(elapsed, 3),
        }

    def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        match_query = build_match_query(query)
        if not match_query:
            return []

        conn = self.connect()
        cur = conn.cursor()
        rows = cur.execute(SEARCH_SQL, (match_query, limit)).fetchall()
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
