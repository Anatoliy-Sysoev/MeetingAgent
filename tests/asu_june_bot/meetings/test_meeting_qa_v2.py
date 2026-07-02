"""Tests for meeting-scoped semantic RAG (MA-MEETING-QA-V2, #111).

A deterministic fake embedder maps known phrases to fixed vectors, so
semantic behavior is provable without Ollama or network access.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from asu_june_bot.llm import LLMResponse  # noqa: E402
from asu_june_bot.llm.ollama_common import OllamaUnavailableError  # noqa: E402
from asu_june_bot.meetings.qa import MeetingQAService  # noqa: E402
from asu_june_bot.meetings.vector_index import (  # noqa: E402
    MeetingVectorRetriever,
    build_meeting_vector_retriever,
)

MEETING_ID = "20260620_team_sync"
OTHER_MEETING_ID = "20260621_other"


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class FakeEmbedder:
    """Deterministic embeddings: related phrases share a dominant axis."""

    #        axes: [decision-passport, integration, leisure, unrelated]
    VECTORS = {
        # query phrasing
        "что решили по паспорту проекта?": [1.0, 0.05, 0.0, 0.0],
        # weak affinity to the decision axis keeps two chunks above threshold
        "кто сказал про интеграцию?": [0.5, 1.0, 0.0, 0.0],
        "какая погода на марсе?": [0.0, 0.0, 1.0, 0.0],
        # orthogonal to every chunk — below MIN_VECTOR_SIMILARITY everywhere
        "какой курс биткоина сегодня?": [0.0, 0.0, 0.0, 1.0],
        # chunk phrasing — no lexical overlap with the queries above
        "сошлись во мнении: оставляем документ как есть, правки не вносим": [0.9, 0.1, 0.0, 0.0],
        "виталий отметил, что стыковка систем через кшд займёт спринт": [0.1, 0.9, 0.0, 0.0],
        "обсудили отпуск и планы на лето": [0.0, 0.0, 0.9, 0.0],
    }

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, text: str) -> list[float]:
        self.calls += 1
        key = " ".join(str(text or "").lower().split())
        for phrase, vector in self.VECTORS.items():
            if phrase in key:
                return list(vector)
        return [0.1, 0.1, 0.1, 0.0]  # neutral, low similarity to everything


class FailingEmbedder:
    def __call__(self, text: str) -> list[float]:
        raise OllamaUnavailableError("Ollama недоступен")


class FakeMeetingsService:
    def get_meeting(self, meeting_id: str):
        return {"meeting_id": meeting_id} if meeting_id in (MEETING_ID, OTHER_MEETING_ID) else None


class FakeLLM:
    def __init__(self, answer: str = "Решение зафиксировано [S1].") -> None:
        self.answer = answer

    def generate(self, request):
        return LLMResponse(text=self.answer)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _chunk(meeting_id: str, chunk_id: str, text: str, **kwargs) -> dict:
    return {
        "meeting_id": meeting_id,
        "chunk_id": chunk_id,
        "source_type": "meeting_chunk",
        "text": text,
        "meeting_title": "Синк команды",
        "topic": kwargs.pop("topic", "проект"),
        "semantic_type": kwargs.pop("semantic_type", "discussion"),
        "speaker_names": kwargs.pop("speaker_names", ["PRIVATE_PERSON_2"]),
        "speakers": kwargs.pop("speakers", ["spk_1"]),
        "start": kwargs.pop("start", 754.0),
        "end": kwargs.pop("end", 810.0),
        "timestamp_start": kwargs.pop("timestamp_start", "00:12:34"),
        "timestamp_end": kwargs.pop("timestamp_end", "00:13:30"),
        "utterance_ids": kwargs.pop("utterance_ids", ["u_101", "u_102"]),
        "relative_path": f"meetings/{meeting_id}/transcript/chunks.jsonl",
        **kwargs,
    }


@pytest.fixture()
def chunks_path(tmp_path: Path) -> Path:
    rows = [
        _chunk(MEETING_ID, "c_dec", "Сошлись во мнении: оставляем документ как есть, правки не вносим"),
        _chunk(
            MEETING_ID,
            "c_int",
            "Виталий отметил, что стыковка систем через КШД займёт спринт",
            timestamp_start="00:25:10",
            utterance_ids=["u_201"],
        ),
        _chunk(MEETING_ID, "c_off", "Обсудили отпуск и планы на лето"),
        _chunk(OTHER_MEETING_ID, "c_leak", "Сошлись во мнении: оставляем документ как есть, правки не вносим"),
    ]
    path = tmp_path / "meeting_chunks.jsonl"
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return path


def _service(
    chunks_path: Path,
    tmp_path: Path,
    embedder=None,
    llm=None,
    retriever=None,
) -> MeetingQAService:
    if retriever is None and embedder is not None:
        retriever = MeetingVectorRetriever(
            embedder, tmp_path / "emb_cache.jsonl", embedding_model="fake-model"
        )
    return MeetingQAService(
        meetings_service=FakeMeetingsService(),
        llm_client=llm,
        meeting_chunks_path=chunks_path,
        vector_retriever=retriever,
    )


# ---------------------------------------------------------------------------
# Semantic retrieval
# ---------------------------------------------------------------------------

def test_semantic_query_finds_paraphrased_decision(chunks_path: Path, tmp_path: Path) -> None:
    """Zero lexical overlap: 'что решили по паспорту' → 'сошлись во мнении…'."""
    svc = _service(chunks_path, tmp_path, embedder=FakeEmbedder())
    result = svc.search(MEETING_ID, "Что решили по паспорту проекта?", top_k=2)
    assert result is not None
    assert result["retrieval_mode"] == "vector"
    assert result["results"], "semantic match expected despite no shared words"
    assert result["results"][0]["chunk_id"] == "c_dec"


def test_semantic_query_speaker_topic(chunks_path: Path, tmp_path: Path) -> None:
    svc = _service(chunks_path, tmp_path, embedder=FakeEmbedder())
    result = svc.search(MEETING_ID, "Кто сказал про интеграцию?", top_k=2)
    assert result["results"][0]["chunk_id"] == "c_int"


def test_irrelevant_chunks_filtered_by_similarity(chunks_path: Path, tmp_path: Path) -> None:
    svc = _service(chunks_path, tmp_path, embedder=FakeEmbedder())
    result = svc.search(MEETING_ID, "Что решили по паспорту проекта?", top_k=5)
    ids = [r["chunk_id"] for r in result["results"]]
    assert "c_off" not in ids  # off-topic chunk below MIN_VECTOR_SIMILARITY


# ---------------------------------------------------------------------------
# Meeting scoping
# ---------------------------------------------------------------------------

def test_vector_retrieval_never_leaks_other_meetings(chunks_path: Path, tmp_path: Path) -> None:
    svc = _service(chunks_path, tmp_path, embedder=FakeEmbedder())
    result = svc.search(MEETING_ID, "Что решили по паспорту проекта?", top_k=10)
    ids = [r["chunk_id"] for r in result["results"]]
    assert "c_leak" not in ids
    assert all(r["source"]["meeting_id"] == MEETING_ID for r in result["results"])


# ---------------------------------------------------------------------------
# Lexical fallback
# ---------------------------------------------------------------------------

def test_fallback_to_lexical_when_ollama_unavailable(chunks_path: Path, tmp_path: Path) -> None:
    svc = _service(chunks_path, tmp_path, embedder=FailingEmbedder())
    result = svc.search(MEETING_ID, "стыковка систем", top_k=3)
    assert result["retrieval_mode"] == "lexical"
    assert result["results"][0]["chunk_id"] == "c_int"


def test_fallback_when_no_vector_retriever(chunks_path: Path, tmp_path: Path) -> None:
    svc = _service(chunks_path, tmp_path, embedder=None, retriever=None)
    result = svc.search(MEETING_ID, "стыковка систем", top_k=3)
    assert result["retrieval_mode"] == "lexical"
    assert result["results"]


def test_chat_reports_retrieval_mode_on_fallback(chunks_path: Path, tmp_path: Path) -> None:
    svc = _service(chunks_path, tmp_path, embedder=FailingEmbedder(), llm=FakeLLM())
    payload = svc.chat(MEETING_ID, "стыковка систем", top_k=3)
    assert payload["retrieval_mode"] == "lexical"
    assert payload["status"] == "answered"


# ---------------------------------------------------------------------------
# Citations
# ---------------------------------------------------------------------------

def test_citations_carry_timestamp_speaker_utterances(chunks_path: Path, tmp_path: Path) -> None:
    svc = _service(chunks_path, tmp_path, embedder=FakeEmbedder(), llm=FakeLLM("Ответ [S1]."))
    payload = svc.chat(MEETING_ID, "Что решили по паспорту проекта?", top_k=2)
    assert payload["status"] == "answered"
    assert payload["citations_basis"] == "cited"
    assert len(payload["citations"]) == 1
    citation = payload["citations"][0]
    assert citation["chunk_id"] == "c_dec"
    assert citation["timestamp_start"] == "00:12:34"
    assert citation["speaker"] == "PRIVATE_PERSON_2"
    assert citation["speakers"] == ["PRIVATE_PERSON_2"]
    assert citation["utterance_ids"] == ["u_101", "u_102"]
    assert citation["citation_label"] == "[00:12:34, PRIVATE_PERSON_2]"


def test_citations_only_for_used_sources(chunks_path: Path, tmp_path: Path) -> None:
    svc = _service(chunks_path, tmp_path, embedder=FakeEmbedder(), llm=FakeLLM("Итог [S2]."))
    payload = svc.chat(MEETING_ID, "Кто сказал про интеграцию?", top_k=2)
    assert payload["citations_basis"] == "cited"
    assert len(payload["citations"]) == 1  # only [S2], not all retrieved


def test_no_absolute_paths_in_payload(chunks_path: Path, tmp_path: Path) -> None:
    svc = _service(chunks_path, tmp_path, embedder=FakeEmbedder(), llm=FakeLLM("Ответ [S1]."))
    payload = svc.chat(MEETING_ID, "Что решили по паспорту проекта?", top_k=2)
    dumped = json.dumps(payload, ensure_ascii=False)
    assert str(tmp_path) not in dumped
    assert "\\\\" not in dumped
    for citation in payload["citations"]:
        artifact = citation.get("artifact")
        if artifact:
            assert not Path(artifact).is_absolute()
            assert ".." not in Path(artifact).parts


def test_no_relevant_fragments_strict_no_context(chunks_path: Path, tmp_path: Path) -> None:
    """No lexical overlap AND all cosine scores below MIN_VECTOR_SIMILARITY → no_context."""
    svc = _service(chunks_path, tmp_path, embedder=FakeEmbedder(), llm=FakeLLM())
    payload = svc.chat(MEETING_ID, "Какой курс биткоина сегодня?", top_k=3)
    assert payload["status"] == "no_context"
    assert payload["retrieval_mode"] == "vector"
    assert "нет фрагментов" in payload["refusal"]
    assert payload["citations"] == []


# ---------------------------------------------------------------------------
# Embeddings cache
# ---------------------------------------------------------------------------

def test_embeddings_cached_and_reused(chunks_path: Path, tmp_path: Path) -> None:
    embedder = FakeEmbedder()
    cache_path = tmp_path / "emb_cache.jsonl"
    retriever = MeetingVectorRetriever(embedder, cache_path, embedding_model="fake-model")
    svc = _service(chunks_path, tmp_path, retriever=retriever)

    svc.search(MEETING_ID, "Что решили по паспорту проекта?", top_k=2)
    calls_first = embedder.calls  # 1 query + 3 chunks
    assert cache_path.exists()
    assert calls_first == 4

    svc.search(MEETING_ID, "Кто сказал про интеграцию?", top_k=2)
    assert embedder.calls == calls_first + 1  # only the new query embedded


def test_cache_survives_new_retriever_instance(chunks_path: Path, tmp_path: Path) -> None:
    cache_path = tmp_path / "emb_cache.jsonl"
    first = FakeEmbedder()
    svc1 = _service(
        chunks_path, tmp_path,
        retriever=MeetingVectorRetriever(first, cache_path, embedding_model="fake-model"),
    )
    svc1.search(MEETING_ID, "Что решили по паспорту проекта?", top_k=2)

    second = FakeEmbedder()
    svc2 = _service(
        chunks_path, tmp_path,
        retriever=MeetingVectorRetriever(second, cache_path, embedding_model="fake-model"),
    )
    svc2.search(MEETING_ID, "Кто сказал про интеграцию?", top_k=2)
    assert second.calls == 1  # chunks loaded from cache; only query embedded


def test_cache_not_shared_across_meetings_with_same_chunk_id(tmp_path: Path) -> None:
    """Identical chunk_id in two meetings must not reuse the other's vector."""
    rows = [
        _chunk(MEETING_ID, "same_id", "Сошлись во мнении: оставляем документ как есть, правки не вносим"),
        _chunk(OTHER_MEETING_ID, "same_id", "Виталий отметил, что стыковка систем через КШД займёт спринт"),
    ]
    path = tmp_path / "meeting_chunks.jsonl"
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    cache_path = tmp_path / "emb_cache.jsonl"
    embedder = FakeEmbedder()
    retriever = MeetingVectorRetriever(embedder, cache_path, embedding_model="fake-model")
    svc = _service(path, tmp_path, retriever=retriever)

    # Populate the cache with meeting 1's chunk under chunk_id "same_id".
    r1 = svc.search(MEETING_ID, "Что решили по паспорту проекта?", top_k=3)
    assert r1["results"] and r1["results"][0]["chunk_id"] == "same_id"
    calls_after_first = embedder.calls

    # Meeting 2 has the same chunk_id but different text: its own text must be
    # embedded (cache miss), and the semantic match must be found.
    r2 = svc.search(OTHER_MEETING_ID, "Кто сказал про интеграцию?", top_k=3)
    assert embedder.calls > calls_after_first + 1  # query AND m2 chunk embedded
    assert r2["retrieval_mode"] == "vector"
    assert r2["results"], "meeting 2 semantic match must not be lost to a stale vector"
    assert r2["results"][0]["source"]["meeting_id"] == OTHER_MEETING_ID


def test_changed_text_reembedded_same_meeting_chunk_id(tmp_path: Path) -> None:
    """Same meeting_id/chunk_id with changed text re-embeds (new text_sha256)."""
    path = tmp_path / "meeting_chunks.jsonl"
    cache_path = tmp_path / "emb_cache.jsonl"

    def write_rows(text: str) -> None:
        with path.open("w", encoding="utf-8") as fh:
            fh.write(json.dumps(_chunk(MEETING_ID, "c_1", text), ensure_ascii=False) + "\n")

    write_rows("Сошлись во мнении: оставляем документ как есть, правки не вносим")
    embedder = FakeEmbedder()
    retriever = MeetingVectorRetriever(embedder, cache_path, embedding_model="fake-model")
    svc = _service(path, tmp_path, retriever=retriever)
    r1 = svc.search(MEETING_ID, "Что решили по паспорту проекта?", top_k=3)
    assert r1["results"]  # decision text matches
    calls_after_first = embedder.calls

    # Re-chunk: same chunk_id, new text. Old vector must not be reused.
    write_rows("Виталий отметил, что стыковка систем через КШД займёт спринт")
    r2 = svc.search(MEETING_ID, "Кто сказал про интеграцию?", top_k=3)
    assert embedder.calls > calls_after_first + 1  # changed text re-embedded
    assert r2["results"], "match on the NEW text expected"
    # Cache now holds two distinct rows for (meeting, c_1): old and new text_sha256.
    cache_rows = [
        json.loads(line)
        for line in cache_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    shas = {row["text_sha256"] for row in cache_rows if row["chunk_id"] == "c_1"}
    assert len(shas) == 2  # changed text produced a new cache identity


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def test_factory_returns_none_without_ollama_config() -> None:
    assert build_meeting_vector_retriever(None) is None
    assert build_meeting_vector_retriever({}) is None
    assert build_meeting_vector_retriever({"ollama": {}}) is None


def test_factory_builds_from_config(tmp_path: Path) -> None:
    config = {
        "ollama": {"base_url": "http://localhost:11434", "embedding_model": "bge-m3"},
    }
    retriever = build_meeting_vector_retriever(config, cache_path=tmp_path / "cache.jsonl")
    assert retriever is not None
    assert retriever.embedding_model == "bge-m3"
