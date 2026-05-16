from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from asu_june_bot.chat.models import ChatRequest, ChatResponse


@dataclass(slots=True)
class ChatRunsLogger:
    """Append-only JSONL logger for ChatService calls.

    The logger is intentionally best-effort: logging failures must not break /chat.
    Runtime data is local and should not be committed to git.
    """

    path: Path
    enabled: bool = True

    def __post_init__(self) -> None:
        if self.enabled:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, request: ChatRequest, response: ChatResponse, latency_ms: int | None = None) -> None:
        if not self.enabled:
            return
        try:
            record = self._build_record(request=request, response=response, latency_ms=latency_ms)
            with self.path.open("a", encoding="utf-8") as file:
                file.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
        except Exception:
            # Observability must never change ChatService behavior.
            return

    def _build_record(self, request: ChatRequest, response: ChatResponse, latency_ms: int | None = None) -> dict[str, Any]:
        diagnostics = response.diagnostics or {}
        request_id = diagnostics.get("request_id")
        run_id = str(request_id or uuid.uuid4())
        prompt_diag = diagnostics.get("prompt") if isinstance(diagnostics.get("prompt"), dict) else {}
        validation_errors = diagnostics.get("validation_errors") or []

        sources = []
        for source in response.sources:
            sources.append(
                {
                    "source_ref": source.source_ref,
                    "source_id": source.source_id,
                    "chunk_id": source.chunk_id,
                    "title": source.title,
                    "path": source.path,
                    "section": source.section,
                    "requirement_id": source.requirement_id,
                    "source_type": source.source_type,
                    "score": source.score,
                    "bucket": source.bucket,
                    "text_preview": source.text_preview,
                }
            )

        answer = response.answer or ""
        return {
            "run_id": run_id,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "query": request.query,
            "mode": request.mode,
            "top_k": request.top_k,
            "status": response.status,
            "answer_preview": answer[:500],
            "answer_chars": len(answer),
            "sources": sources,
            "search_status": diagnostics.get("search_status") or response.search.get("status"),
            "guard_decision": _get_nested(response.search, "guard", "decision"),
            "llm_model": diagnostics.get("llm_model"),
            "llm_called": bool(diagnostics.get("llm_called")),
            "llm_finish_reason": diagnostics.get("llm_finish_reason"),
            "validation_errors": validation_errors,
            "prompt_sources": diagnostics.get("prompt_sources"),
            "used_context_chars": prompt_diag.get("used_context_chars"),
            "max_context_chars": prompt_diag.get("max_context_chars"),
            "latency_ms": latency_ms,
            "manual_label": None,
            "manual_issue": None,
        }


def _get_nested(data: dict[str, Any], *keys: str) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current
