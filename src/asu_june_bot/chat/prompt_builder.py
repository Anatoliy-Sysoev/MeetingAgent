from __future__ import annotations

from typing import Any

from .models import ChatSource


SYSTEM_PROMPT = """Ты — проектный ассистент системного аналитика по проекту ЦП УПКС.
Отвечай только на основании переданного контекста.
Не используй внешние знания и не додумывай факты.
Если данных недостаточно, прямо напиши: "В переданных источниках данных недостаточно для ответа".
Отвечай на русском языке.
Каждое фактическое утверждение подкрепляй ссылкой на источник вида [S1], [S2].
Не используй ссылки на источники, которых нет в контексте.
""".strip()


def _stringify(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _text_from_source(source: dict[str, Any]) -> str:
    for key in ("text", "content", "chunk_text", "body", "preview", "text_preview"):
        value = _stringify(source.get(key))
        if value:
            return value
    return ""


def _metadata_value(source: dict[str, Any], *keys: str) -> str | None:
    metadata = source.get("metadata") or {}
    for key in keys:
        value = _stringify(source.get(key))
        if value:
            return value
        value = _stringify(metadata.get(key)) if isinstance(metadata, dict) else None
        if value:
            return value
    return None


def _truncate_on_word_boundary(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    truncated = text[:limit].rsplit(" ", 1)[0].strip()
    return (truncated or text[:limit]).rstrip() + "…"


def source_to_chat_source(source: dict[str, Any], source_ref: str, bucket: str) -> ChatSource:
    text = _text_from_source(source)
    preview = _truncate_on_word_boundary(text, 500) if text else None
    score_raw = source.get("score") or source.get("hybrid_score") or source.get("rerank_score")
    try:
        score = float(score_raw) if score_raw is not None else None
    except (TypeError, ValueError):
        score = None
    return ChatSource(
        source_ref=source_ref,
        source_id=_metadata_value(source, "source_id", "document_id"),
        chunk_id=_metadata_value(source, "chunk_id", "id"),
        title=_metadata_value(source, "title", "document_title", "file_name", "filename", "document"),
        path=_metadata_value(source, "path", "source_path", "file_path", "relative_path"),
        section=_metadata_value(source, "section", "section_title", "section_path"),
        requirement_id=_metadata_value(source, "requirement_id"),
        source_type=_metadata_value(source, "source_type"),
        score=score,
        text_preview=preview,
        bucket=bucket,
    )


class PromptBuilder:
    def __init__(self, max_sources: int = 6, max_context_chars: int = 9000, max_chars_per_source: int = 1800) -> None:
        self.max_sources = max_sources
        self.max_context_chars = max_context_chars
        self.max_chars_per_source = max_chars_per_source

    def build_sources(self, context: dict[str, Any], max_sources: int | None = None) -> tuple[list[ChatSource], str, dict[str, Any]]:
        source_limit = max_sources or self.max_sources
        ordered: list[tuple[str, dict[str, Any]]] = []
        for bucket in ("primary_sources", "supporting_sources"):
            for item in context.get(bucket) or []:
                if isinstance(item, dict):
                    ordered.append((bucket, item))

        sources: list[ChatSource] = []
        blocks: list[str] = []
        seen: set[str] = set()
        used_chars = 0
        skipped_by_budget = 0
        skipped_duplicate = 0
        skipped_empty = 0

        for bucket, item in ordered:
            source_key = str(item.get("chunk_id") or item.get("id") or item.get("source_id") or repr(item))
            if source_key in seen:
                skipped_duplicate += 1
                continue
            seen.add(source_key)
            text = _text_from_source(item)
            if not text:
                skipped_empty += 1
                continue

            ref = f"S{len(sources) + 1}"
            chat_source = source_to_chat_source(item, ref, bucket)
            text = _truncate_on_word_boundary(text, self.max_chars_per_source)
            meta_parts = [part for part in [chat_source.title, chat_source.section, chat_source.requirement_id] if part]
            meta_line = " | ".join(meta_parts) if meta_parts else "metadata unavailable"
            bucket_label = "ОСНОВНОЙ ИСТОЧНИК" if bucket == "primary_sources" else "ДОПОЛНИТЕЛЬНЫЙ ИСТОЧНИК"
            block = f"[{ref}] {bucket_label}\n{meta_line}\n{text}"

            if used_chars + len(block) > self.max_context_chars and sources:
                skipped_by_budget += 1
                continue

            sources.append(chat_source)
            blocks.append(block)
            used_chars += len(block)
            if len(sources) >= source_limit:
                break

        diagnostics = {
            "max_sources": source_limit,
            "max_context_chars": self.max_context_chars,
            "max_chars_per_source": self.max_chars_per_source,
            "used_context_chars": used_chars,
            "selected_sources": len(sources),
            "skipped_by_budget": skipped_by_budget,
            "skipped_duplicate": skipped_duplicate,
            "skipped_empty": skipped_empty,
        }
        return sources, "\n\n".join(blocks), diagnostics

    def build_prompt(self, query: str, context: dict[str, Any]) -> tuple[str, list[ChatSource], dict[str, Any]]:
        sources, source_text, diagnostics = self.build_sources(context)
        prompt = f"""Вопрос пользователя:
{query}

Контекст из проектной документации:
{source_text}

Сформируй ответ строго по контексту.

Правила ответа:
1. Отвечай только фактами из источников выше.
2. Каждое фактическое утверждение заверши ссылкой [Sx].
3. Не используй excluded sources и внешние знания.
4. Если данных недостаточно, напиши: "В переданных источниках данных недостаточно для ответа".

Формат:
Краткий ответ
<1-3 предложения со ссылками [Sx]>

Обоснование
<2-5 пунктов, каждый пункт со ссылкой [Sx]>
""".strip()
        return prompt, sources, diagnostics
