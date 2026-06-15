"""Meeting-scoped search and Q&A.

Self-contained retrieval + grounded answering over a single meeting's chunks.

This service is intentionally independent of the project-corpus ``SearchService``
and ``ChatService``: those run the project-only ``ProjectGuard`` and search the
project corpus, which would both reject meeting questions and risk leaking
project/global chunks.  Here retrieval is strictly scoped to one ``meeting_id``
within ``data/meeting_chunks.jsonl`` (lexical MVP, mirroring
``scripts/31_meeting_search.py``), and chat answers only from those scoped
chunks.  No filesystem paths are ever placed in responses.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from asu_june_bot.core.config import resolve_work_path
from asu_june_bot.llm import LLMClient, LLMError, LLMRequest
from asu_june_bot.meetings.service import MeetingsService, _safe_meeting_id

DEFAULT_MEETING_CHUNKS_PATH = "data/meeting_chunks.jsonl"

# Only meeting-derived chunk types are searchable; project/global chunks never
# appear in this file, but we filter defensively regardless.
MEETING_SOURCE_TYPES = frozenset(
    {
        "meeting_chunk",
        "meeting_decision",
        "meeting_action_item",
        "meeting_risk",
        "meeting_open_question",
    }
)

_TOKEN_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9]{2,}")

_SYSTEM_PROMPT = (
    "Ты ассистент по конкретной встрече. Отвечай ТОЛЬКО на основе переданных "
    "фрагментов встречи. Не используй внешние знания. Если фрагментов "
    "недостаточно для ответа, прямо скажи, что в материалах встречи нет ответа. "
    "Ссылайся на источники в формате [S1], [S2] по номеру фрагмента."
)

# Generic, user-safe refusal/error messages (no backend internals).
_REFUSAL_NO_CONTEXT = (
    "В материалах этой встречи нет фрагментов, релевантных вопросу. "
    "Ответ не сформирован."
)
_REFUSAL_NO_ANSWER = (
    "В найденных фрагментах встречи нет достаточной информации для ответа."
)
_REFUSAL_LLM_UNAVAILABLE = (
    "Модель ответа сейчас недоступна. Попробуйте позже или используйте поиск по встрече."
)


def _tokenize(text: str) -> list[str]:
    return [token.lower().replace("ё", "е") for token in _TOKEN_RE.findall(text or "")]


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _make_preview(text: str, max_chars: int = 280) -> str:
    collapsed = " ".join(str(text or "").split())
    if len(collapsed) <= max_chars:
        return collapsed
    return collapsed[: max_chars - 3].rstrip() + "..."


class MeetingQAService:
    """Lexical search + grounded chat scoped to a single meeting."""

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        meetings_service: MeetingsService | None = None,
        llm_client: LLMClient | None = None,
        meeting_chunks_path: Path | str | None = None,
    ) -> None:
        self.config = config
        self.meetings_service = meetings_service or MeetingsService()
        self.llm_client = llm_client
        self._explicit_chunks_path = (
            Path(meeting_chunks_path) if meeting_chunks_path is not None else None
        )

    # -- chunk loading ------------------------------------------------------

    def _chunks_path(self) -> Path:
        if self._explicit_chunks_path is not None:
            return self._explicit_chunks_path
        raw = (self.config or {}).get("paths", {}) if isinstance(self.config, dict) else {}
        configured = raw.get("meeting_chunks") if isinstance(raw, dict) else None
        path_value = configured or DEFAULT_MEETING_CHUNKS_PATH
        if self.config:
            return resolve_work_path(self.config, path_value)
        return Path(path_value)

    def _load_meeting_rows(self, meeting_id: str) -> list[dict[str, Any]]:
        """Return only this meeting's searchable chunks (empty if none/no file)."""
        path = self._chunks_path()
        if not path.exists():
            return []
        rows: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue  # skip malformed line; never surface parse details
                if row.get("meeting_id") != meeting_id:
                    continue  # strict per-meeting scoping
                if row.get("source_type") not in MEETING_SOURCE_TYPES:
                    continue
                if not str(row.get("text") or "").strip():
                    continue
                rows.append(row)
        return rows

    # -- scoring ------------------------------------------------------------

    @staticmethod
    def _row_haystack(row: dict[str, Any]) -> str:
        values = [
            str(row.get("text") or ""),
            str(row.get("meeting_title") or ""),
            str(row.get("topic") or ""),
            str(row.get("semantic_type") or ""),
        ]
        speakers = row.get("speaker_names") or row.get("speakers") or []
        if isinstance(speakers, list):
            values.extend(str(item) for item in speakers)
        return "\n".join(values)

    @classmethod
    def _lexical_score(cls, query: str, row: dict[str, Any]) -> float:
        query_tokens = _tokenize(query)
        if not query_tokens:
            return 0.0
        haystack = cls._row_haystack(row)
        haystack_lower = haystack.lower().replace("ё", "е")
        haystack_set = set(_tokenize(haystack))
        overlap = sum(1 for token in set(query_tokens) if token in haystack_set)
        score = overlap / max(len(set(query_tokens)), 1)
        query_lower = query.lower().replace("ё", "е").strip()
        if query_lower and query_lower in haystack_lower:
            score += 1.0
        return round(score, 6)

    # -- source / citation shaping -----------------------------------------

    def _artifact_ref(self, row: dict[str, Any], meeting_id: str) -> str | None:
        """Meeting-relative artifact key — never an absolute/local fs path."""
        explicit = row.get("artifact_id") or row.get("artifact_type")
        if explicit:
            return str(explicit)
        rel = row.get("relative_path")
        if not rel:
            return None
        prefix = f"meetings/{meeting_id}/"
        rel = str(rel)
        return rel[len(prefix):] if rel.startswith(prefix) else rel

    @staticmethod
    def _speaker(row: dict[str, Any]) -> str | None:
        speakers = row.get("speaker_names") or row.get("speakers") or []
        if isinstance(speakers, list) and speakers:
            return str(speakers[0])
        return None

    def _source_ref(self, row: dict[str, Any], meeting_id: str) -> dict[str, Any]:
        return {
            "meeting_id": meeting_id,
            "artifact": self._artifact_ref(row, meeting_id),
            "segment_id": None,  # chunks are windows, not transcript segments
            "speaker": self._speaker(row),
            "start_sec": _coerce_float(row.get("start")),
            "end_sec": _coerce_float(row.get("end")),
        }

    def _ranked_rows(
        self, meeting_id: str, query: str, top_k: int
    ) -> list[tuple[float, dict[str, Any]]]:
        rows = self._load_meeting_rows(meeting_id)
        scored: list[tuple[float, dict[str, Any]]] = []
        for row in rows:
            score = self._lexical_score(query, row)
            if score <= 0:
                continue
            scored.append((score, row))
        scored.sort(
            key=lambda item: (
                -item[0],
                str(item[1].get("timestamp_start") or ""),
                str(item[1].get("chunk_id") or ""),
            )
        )
        return scored[:top_k]

    # -- public API ---------------------------------------------------------

    def search(self, meeting_id: str, query: str, top_k: int = 5) -> dict[str, Any] | None:
        """Meeting-scoped search. Returns None when meeting is unsafe/unknown."""
        if not _safe_meeting_id(meeting_id):
            return None
        if self.meetings_service.get_meeting(meeting_id) is None:
            return None

        path_exists = self._chunks_path().exists()
        ranked = self._ranked_rows(meeting_id, query, top_k)
        results = [
            {
                "chunk_id": str(row.get("chunk_id") or ""),
                "score": round(float(score), 6),
                "text": str(row.get("text") or ""),
                "source": self._source_ref(row, meeting_id),
            }
            for score, row in ranked
        ]
        return {
            "meeting_id": meeting_id,
            "query": query,
            "available": path_exists,
            "results": results,
        }

    def chat(self, meeting_id: str, query: str, top_k: int = 5) -> dict[str, Any] | None:
        """Meeting-scoped grounded chat. Returns None when meeting unsafe/unknown."""
        if not _safe_meeting_id(meeting_id):
            return None
        if self.meetings_service.get_meeting(meeting_id) is None:
            return None

        ranked = self._ranked_rows(meeting_id, query, top_k)
        if not ranked:
            return self._chat_payload(meeting_id, status="no_context", refusal=_REFUSAL_NO_CONTEXT)

        prompt = self._build_prompt(query, ranked)
        if self.llm_client is None:
            return self._chat_payload(
                meeting_id, status="llm_unavailable", refusal=_REFUSAL_LLM_UNAVAILABLE
            )
        try:
            llm_response = self.llm_client.generate(
                LLMRequest(prompt=prompt, system_prompt=_SYSTEM_PROMPT)
            )
        except LLMError:
            return self._chat_payload(
                meeting_id, status="llm_error", refusal=_REFUSAL_LLM_UNAVAILABLE
            )

        answer = (llm_response.text or "").strip()
        if not answer or _has_no_answer_marker(answer):
            return self._chat_payload(meeting_id, status="no_answer", refusal=_REFUSAL_NO_ANSWER)

        citations = [self._citation(row, meeting_id) for _score, row in ranked]
        return self._chat_payload(
            meeting_id, status="answered", answer=answer, citations=citations
        )

    # -- helpers ------------------------------------------------------------

    def _build_prompt(self, query: str, ranked: list[tuple[float, dict[str, Any]]]) -> str:
        blocks = []
        for idx, (_score, row) in enumerate(ranked, start=1):
            ts_start = row.get("timestamp_start") or "??:??:??"
            ts_end = row.get("timestamp_end") or "??:??:??"
            speaker = self._speaker(row) or "спикер неизвестен"
            blocks.append(
                f"[S{idx}] ({ts_start}-{ts_end}, {speaker})\n{str(row.get('text') or '').strip()}"
            )
        context = "\n\n".join(blocks)
        return (
            f"Фрагменты встречи:\n\n{context}\n\n"
            f"Вопрос: {query}\n\n"
            "Ответь только на основе фрагментов выше и сошлись на источники [S#]."
        )

    def _citation(self, row: dict[str, Any], meeting_id: str) -> dict[str, Any]:
        return {
            "chunk_id": str(row.get("chunk_id") or ""),
            "excerpt": _make_preview(str(row.get("text") or "")),
            "artifact": self._artifact_ref(row, meeting_id),
            "segment_id": None,
            "speaker": self._speaker(row),
            "start_sec": _coerce_float(row.get("start")),
            "end_sec": _coerce_float(row.get("end")),
        }

    @staticmethod
    def _chat_payload(
        meeting_id: str,
        status: str,
        answer: str | None = None,
        refusal: str | None = None,
        citations: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return {
            "meeting_id": meeting_id,
            "status": status,
            "answer": answer,
            "refusal": refusal,
            "citations": citations or [],
        }


def _has_no_answer_marker(text: str) -> bool:
    # Local import keeps the project chat package optional at import time.
    from asu_june_bot.chat.answer_validator import has_no_answer_marker

    return has_no_answer_marker(text)
