from __future__ import annotations

import re

from .models import ChatSource


SOURCE_REF_RE = re.compile(r"\[S\d+\]")


class AnswerValidator:
    def validate_answered(self, answer: str, sources: list[ChatSource]) -> tuple[bool, list[str]]:
        errors: list[str] = []
        text = (answer or "").strip()
        if not text:
            errors.append("empty_answer")
        if not sources:
            errors.append("missing_sources")
        if text and not SOURCE_REF_RE.search(text):
            errors.append("missing_source_references")
        if sources:
            allowed_refs = {f"[{source.source_ref}]" for source in sources}
            used_refs = set(SOURCE_REF_RE.findall(text))
            unknown_refs = sorted(used_refs - allowed_refs)
            if unknown_refs:
                errors.append("unknown_source_references:" + ",".join(unknown_refs))
        return not errors, errors
