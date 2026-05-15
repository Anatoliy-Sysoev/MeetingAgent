from __future__ import annotations

from typing import Any

from .models import ChatSource


SYSTEM_PROMPT = """Ты — проектный ассистент системного аналитика по проекту ЦП УПКС.
Отвечай только на основании переданного контекста.
Не используй внешние знания и не додумывай факты.
Если данных недостаточно, прямо напиши, что в переданных источниках данных недостаточно.
Отвечай на русском языке.
В ответе обязательно используй ссылки на источники вида [S1], [S2].
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


def source_to_chat_source(source: dict[str, Any], source_ref: str) -> ChatSource:
    text = _text_from_source(source)
    preview = text[:500] if text else None
    score_raw = source.get("score") or source.get("hybrid_score") or source.get("rerank_score")
    try:
        score = float(score_raw) if score_raw is not None else None
    except (TypeError, ValueError):
        score = None
    return ChatSource(
        source_ref=source_ref,
        source_id=_metadata_value(source, "source_id", "document_id"),
        chunk_id=_metadata_value(source, "chunk_id", "id"),
        title=_metadata_value(source, "title", "document_title", "file_name", "filename"),
        path=_metadata_value(source, "path", "source_path", "file_path"),
        section=_metadata_value(source, "section", "section_title", "section_path"),
        requirement_id=_metadata_value(source, "requirement_id"),
        source_type=_metadata_value(source, "source_type"),
        score=score,
        text_preview=preview,
    )


class PromptBuilder:
    def build_sources(self, context: dict[str, Any], max_sources: int = 6) -> tuple[list[ChatSource], str]:
        raw_sources: list[dict[str, Any]] = []
        for bucket in ("primary_sources", "supporting_sources"):
            for item in context.get(bucket) or []:
                if isinstance(item, dict):
                    raw_sources.append(item)

        sources: list[ChatSource] = []
        blocks: list[str] = []
        seen: set[str] = set()
        for item in raw_sources:
            source_key = str(item.get("chunk_id") or item.get("id") or item.get("source_id") or repr(item))
            if source_key in seen:
                continue
            seen.add(source_key)
            ref = f"S{len(sources) + 1}"
            chat_source = source_to_chat_source(item, ref)
            text = _text_from_source(item)
            if not text:
                continue
            sources.append(chat_source)
            meta_parts = [part for part in [chat_source.title, chat_source.section, chat_source.requirement_id] if part]
            meta_line = " | ".join(meta_parts) if meta_parts else "metadata unavailable"
            blocks.append(f"[{ref}] {meta_line}\n{text[:2500]}")
            if len(sources) >= max_sources:
                break

        return sources, "\n\n".join(blocks)

    def build_prompt(self, query: str, context: dict[str, Any]) -> tuple[str, list[ChatSource]]:
        sources, source_text = self.build_sources(context)
        prompt = f"""Вопрос пользователя:
{query}

Контекст из проектной документации:
{source_text}

Сформируй ответ строго по контексту.

Формат:
Краткий ответ
<1-3 предложения>

Обоснование
<2-5 пунктов, каждый пункт со ссылкой [Sx]>

Источники
<перечисли использованные [Sx]>
""".strip()
        return prompt, sources
