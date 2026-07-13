from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
SCRIPTS = ROOT / "scripts"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from asu_june_bot.meetings.vector_cache import (  # noqa: E402
    CacheEmbeddingRequest,
    MeetingEmbeddingCache,
    rebuild_meeting_embedding_cache,
)
from asu_june_bot.meetings.vector_index import MeetingVectorRetriever  # noqa: E402


MODEL = "synthetic-bge"
MEETING_ID = "2026-07-13__vector-cache-test"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _row(
    text: str,
    *,
    chunk_id: str = "chunk-1",
    meeting_id: str = MEETING_ID,
    model: str = MODEL,
    embedding: list[float] | None = None,
) -> dict[str, object]:
    return {
        "meeting_id": meeting_id,
        "chunk_id": chunk_id,
        "text_sha256": _sha(text),
        "embedding_model": model,
        "embedding": embedding or [1.0, 2.0, 3.0],
    }


def _chunk(text: str, chunk_id: str = "chunk-1") -> dict[str, object]:
    return {"meeting_id": MEETING_ID, "chunk_id": chunk_id, "text": text}


def _write_lines(path: Path, values: list[object]) -> None:
    with path.open("wb") as handle:
        for value in values:
            if isinstance(value, bytes):
                handle.write(value)
            else:
                handle.write((json.dumps(value, ensure_ascii=False) + "\n").encode("utf-8"))


def _read_rows(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


class CountingEmbedder:
    def __init__(self) -> None:
        self.calls: Counter[str] = Counter()
        self._lock = threading.Lock()

    def __call__(self, text: str) -> list[float]:
        with self._lock:
            self.calls[text] += 1
        if text.startswith("chunk"):
            time.sleep(0.03)
        return [float(len(text) + 1), 2.0, 3.0]


def test_rebuild_dry_run_reports_damage_without_mutation(tmp_path: Path) -> None:
    cache_path = tmp_path / "cache.jsonl"
    first = _row("chunk alpha", embedding=[1.0, 0.0])
    duplicate = _row("chunk alpha", embedding=[0.0, 1.0])
    other_model = _row("chunk beta", chunk_id="chunk-2", model="other-model")
    invalid = {"meeting_id": MEETING_ID, "embedding": [1.0]}
    _write_lines(cache_path, [first, duplicate, other_model, invalid, b'{"truncated":'])
    before = cache_path.read_bytes()

    report = rebuild_meeting_embedding_cache(cache_path, dry_run=True)

    assert report.rows_read == 5
    assert report.rows_written == 2
    assert report.duplicate_rows == 1
    assert report.invalid_rows == 1
    assert report.malformed_rows == 1
    assert report.rewritten is False
    assert cache_path.read_bytes() == before


def test_rebuild_atomically_deduplicates_and_preserves_models(tmp_path: Path) -> None:
    cache_path = tmp_path / "cache.jsonl"
    _write_lines(
        cache_path,
        [
            _row("chunk alpha", embedding=[1.0, 0.0]),
            _row("chunk alpha", embedding=[0.0, 1.0]),
            _row("chunk beta", chunk_id="chunk-2", model="other-model"),
            b'{"truncated":',
        ],
    )

    report = rebuild_meeting_embedding_cache(cache_path)
    rows = _read_rows(cache_path)

    assert report.rows_written == 2
    assert report.rewritten is True
    assert {str(row["embedding_model"]) for row in rows} == {MODEL, "other-model"}
    assert next(row for row in rows if row["embedding_model"] == MODEL)["embedding"] == [0.0, 1.0]
    assert list(tmp_path.glob(".cache.jsonl.*.tmp")) == []


def test_cache_read_repairs_malformed_tail_without_reembedding(tmp_path: Path) -> None:
    cache_path = tmp_path / "cache.jsonl"
    text = "chunk alpha"
    _write_lines(cache_path, [_row(text), b'{"truncated":'])
    embedder = CountingEmbedder()
    retriever = MeetingVectorRetriever(embedder, cache_path, embedding_model=MODEL)

    scores = retriever.score_rows("query", [_chunk(text)])

    assert scores is not None and len(scores) == 1
    assert embedder.calls == Counter({"query": 1})
    assert _read_rows(cache_path) == [_row(text)]


def test_wrong_dimension_cache_row_is_reembedded_and_replaced(tmp_path: Path) -> None:
    cache_path = tmp_path / "cache.jsonl"
    text = "chunk alpha"
    _write_lines(cache_path, [_row(text, embedding=[1.0, 2.0])])
    embedder = CountingEmbedder()
    retriever = MeetingVectorRetriever(embedder, cache_path, embedding_model=MODEL)

    scores = retriever.score_rows("query", [_chunk(text)])

    assert scores is not None and len(scores) == 1
    assert embedder.calls == Counter({"query": 1, text: 1})
    assert len(_read_rows(cache_path)[0]["embedding"]) == 3


def test_concurrent_threads_embed_each_chunk_once(tmp_path: Path) -> None:
    cache_path = tmp_path / "cache.jsonl"
    embedder = CountingEmbedder()
    retriever = MeetingVectorRetriever(embedder, cache_path, embedding_model=MODEL)
    rows = [_chunk("chunk alpha", "chunk-1"), _chunk("chunk beta", "chunk-2")]

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: retriever.score_rows("query", rows), range(8)))

    assert all(result is not None and len(result) == 2 for result in results)
    assert embedder.calls == Counter({"query": 8, "chunk alpha": 1, "chunk beta": 1})
    assert len(_read_rows(cache_path)) == 2


def test_concurrent_retriever_instances_share_thread_lock(tmp_path: Path) -> None:
    cache_path = tmp_path / "cache.jsonl"
    embedder = CountingEmbedder()
    retrievers = [
        MeetingVectorRetriever(embedder, cache_path, embedding_model=MODEL)
        for _ in range(4)
    ]
    rows = [_chunk("chunk alpha")]

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(
            pool.map(lambda retriever: retriever.score_rows("query", rows), retrievers)
        )

    assert all(result is not None for result in results)
    assert embedder.calls == Counter({"query": 4, "chunk alpha": 1})
    assert len(_read_rows(cache_path)) == 1


_PROCESS_SCRIPT = r"""
import json
import os
import sys
import time
from pathlib import Path
from asu_june_bot.meetings.vector_index import MeetingVectorRetriever

calls = []
def embed(text):
    calls.append(text)
    if text.startswith("chunk"):
        time.sleep(0.1)
    return [float(len(text) + 1), 2.0, 3.0]

rows = [
    {"meeting_id": "2026-07-13__process", "chunk_id": "chunk-1", "text": "chunk alpha"},
    {"meeting_id": "2026-07-13__process", "chunk_id": "chunk-2", "text": "chunk beta"},
]
scores = MeetingVectorRetriever(embed, Path(sys.argv[1]), "process-model").score_rows("query", rows)
Path(sys.argv[2], f"{os.getpid()}.json").write_text(json.dumps(calls), encoding="utf-8")
raise SystemExit(0 if scores is not None and len(scores) == 2 else 9)
"""


def test_concurrent_processes_leave_one_valid_row_per_identity(tmp_path: Path) -> None:
    cache_path = tmp_path / "cache.jsonl"
    calls_dir = tmp_path / "calls"
    calls_dir.mkdir()
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join((str(SRC), env.get("PYTHONPATH", ""))).rstrip(
        os.pathsep
    )
    processes = [
        subprocess.Popen(
            [sys.executable, "-c", _PROCESS_SCRIPT, str(cache_path), str(calls_dir)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for _ in range(4)
    ]
    results = [process.communicate(timeout=20) for process in processes]

    assert [process.returncode for process in processes] == [0, 0, 0, 0], results
    rows = _read_rows(cache_path)
    assert len(rows) == 2
    identities = {
        (row["meeting_id"], row["chunk_id"], row["text_sha256"], row["embedding_model"])
        for row in rows
    }
    calls = Counter(
        text
        for path in calls_dir.glob("*.json")
        for text in json.loads(path.read_text(encoding="utf-8"))
    )
    assert len(identities) == 2
    assert calls == Counter({"query": 4, "chunk alpha": 1, "chunk beta": 1})


def test_atomic_rebuild_failure_preserves_previous_file(tmp_path: Path, monkeypatch) -> None:
    cache_path = tmp_path / "cache.jsonl"
    _write_lines(cache_path, [_row("chunk alpha"), b'{"truncated":'])
    before = cache_path.read_bytes()
    monkeypatch.setattr("asu_june_bot.meetings.vector_cache.os.replace", lambda *_: (_ for _ in ()).throw(OSError("replace failed")))

    with pytest.raises(OSError, match="replace failed"):
        rebuild_meeting_embedding_cache(cache_path)

    assert cache_path.read_bytes() == before
    assert list(tmp_path.glob(".cache.jsonl.*.tmp")) == []


def test_cache_storage_failure_returns_lexical_fallback_signal(tmp_path: Path) -> None:
    blocked_parent = tmp_path / "not-a-directory"
    blocked_parent.write_text("file", encoding="utf-8")
    retriever = MeetingVectorRetriever(
        lambda text: [1.0, 2.0, 3.0],
        blocked_parent / "cache.jsonl",
        embedding_model=MODEL,
    )

    assert retriever.score_rows("query", [_chunk("chunk alpha")]) is None


def test_invalid_embedding_does_not_create_cache_row(tmp_path: Path) -> None:
    cache_path = tmp_path / "cache.jsonl"
    cache = MeetingEmbeddingCache(cache_path)
    request = CacheEmbeddingRequest(MEETING_ID, "chunk-1", _sha("chunk alpha"), "chunk alpha")

    result = cache.ensure_embeddings(MODEL, [request], lambda text: [0.0, 0.0])

    assert result == {}
    assert not cache_path.exists()


def test_invalid_cache_identity_is_not_embedded_or_written(tmp_path: Path) -> None:
    cache_path = tmp_path / "cache.jsonl"
    cache = MeetingEmbeddingCache(cache_path)
    embedder = CountingEmbedder()
    request = CacheEmbeddingRequest(MEETING_ID, "chunk-1", "not-a-sha", "chunk alpha")

    result = cache.ensure_embeddings(MODEL, [request], embedder)

    assert result == {}
    assert embedder.calls == Counter()
    assert not cache_path.exists()


def test_rebuild_cli_compacts_cache(tmp_path: Path) -> None:
    cache_path = tmp_path / "cache.jsonl"
    _write_lines(cache_path, [_row("chunk alpha"), _row("chunk alpha"), b'{"truncated":'])
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join((str(SRC), str(SCRIPTS)))
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "49_rebuild_meeting_vector_cache.py"),
            "--cache-path",
            str(cache_path),
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["rows_read"] == 3
    assert payload["rows_written"] == 1
    assert payload["duplicate_rows"] == 1
    assert payload["malformed_rows"] == 1
    assert len(_read_rows(cache_path)) == 1
