from __future__ import annotations

from .models import ChatResponse


class ResponseFormatter:
    def to_text(self, response: ChatResponse) -> str:
        if response.answer:
            text = response.answer.strip()
        else:
            text = f"Статус: {response.status}"

        if response.sources:
            lines = [text, "", "Источники:"]
            for source in response.sources:
                label = source.title or source.path or source.source_id or source.chunk_id or "Источник"
                detail = source.section or source.requirement_id or source.source_type or ""
                suffix = f" — {detail}" if detail else ""
                lines.append(f"[{source.source_ref}] {label}{suffix}")
                if source.source_url:
                    lines.append(f"    {source.source_url}")
            return "\n".join(lines).strip()
        return text
