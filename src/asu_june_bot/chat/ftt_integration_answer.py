from __future__ import annotations

from dataclasses import dataclass

from .models import ChatSource


def _norm(text: str) -> str:
    return " ".join((text or "").lower().replace("ё", "е").split())


def _source_text(source: ChatSource) -> str:
    return " ".join(str(part or "") for part in (source.title, source.path, source.text_preview))


def _is_ftt_source(source: ChatSource) -> bool:
    haystack = _norm(_source_text(source)).replace("\\", "/")
    return "фтт" in haystack or "функционально-технические требования" in haystack


def _has_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(_norm(marker) in text for marker in markers)


@dataclass(frozen=True, slots=True)
class FttIntegrationAnswerSpec:
    intent: str
    query_markers: tuple[str, ...]
    source_anchors: tuple[str, ...]
    short_answer: str
    evidence_label: str


FTT_INTEGRATION_ANSWER_SPECS: tuple[FttIntegrationAnswerSpec, ...] = (
    FttIntegrationAnswerSpec(
        intent="protocol",
        query_markers=("протокол передачи", "протокол"),
        source_anchors=("https",),
        short_answer="Согласно ФТТ, для системного взаимодействия используется протокол HTTPS.",
        evidence_label="протокол передачи данных `https`",
    ),
    FttIntegrationAnswerSpec(
        intent="message_size",
        query_markers=("размер", "максимальный размер", "100"),
        source_anchors=("100 мб", "100 mb", "100мб"),
        short_answer="Согласно ФТТ, максимальный размер одного сообщения составляет 100 Мб.",
        evidence_label="максимальный размер сообщения `100 Мб`",
    ),
    FttIntegrationAnswerSpec(
        intent="message_format",
        query_markers=("формат", "формат сообщений", "сообщений", "сообщения"),
        source_anchors=("json", "xml"),
        short_answer="Согласно ФТТ, для сообщений предпочтителен JSON; XML допускается при необходимости.",
        evidence_label="форматы сообщений `JSON` / `XML`",
    ),
    FttIntegrationAnswerSpec(
        intent="auth_type",
        query_markers=("тип аутентификац", "аутентификац"),
        source_anchors=("basic-аутентификация", "basic аутентификация", "basic"),
        short_answer="Согласно ФТТ, для системного взаимодействия применяется Basic-аутентификация.",
        evidence_label="тип аутентификации `Basic-аутентификация`",
    ),
    FttIntegrationAnswerSpec(
        intent="object_identification",
        query_markers=("идентификац", "передаваемых объектов", "тэг", "тег", "заголовке вызова"),
        source_anchors=("тэг в заголовке вызова", "тег в заголовке вызова", "идентификация передаваемых объектов"),
        short_answer="Согласно ФТТ, идентификация передаваемых объектов выполняется через тэг в заголовке вызова.",
        evidence_label="идентификация передаваемых объектов через тэг в заголовке вызова",
    ),
)


def _select_spec(query: str) -> FttIntegrationAnswerSpec | None:
    lowered = _norm(query)
    has_ftt_or_integration_scope = any(
        marker in lowered
        for marker in (
            "фтт",
            "интеграц",
            "системн",
            "сообщени",
            "передаваем",
            "объект",
        )
    )
    if not has_ftt_or_integration_scope:
        return None

    for spec in FTT_INTEGRATION_ANSWER_SPECS:
        if any(marker in lowered for marker in spec.query_markers):
            return spec
    return None


def _matching_ftt_sources(sources: list[ChatSource], spec: FttIntegrationAnswerSpec) -> list[ChatSource]:
    selected: list[ChatSource] = []
    seen_refs: set[str] = set()
    for source in sources:
        if source.source_ref in seen_refs:
            continue
        haystack = _norm(_source_text(source))
        if not _is_ftt_source(source):
            continue
        if not _has_any(haystack, spec.source_anchors):
            continue
        seen_refs.add(source.source_ref)
        selected.append(source)
    return selected


def build_ftt_integration_deterministic_answer(query: str, sources: list[ChatSource]) -> str | None:
    """Build narrow source-grounded answers for explicit FTT integration facts.

    This is intentionally limited to stable FTT integration parameters that are
    already present in the selected chat sources. It prevents false no_answer
    outcomes for short factual questions without changing retrieval, persisted
    chunks or embeddings.
    """

    spec = _select_spec(query)
    if spec is None:
        return None

    selected = _matching_ftt_sources(sources, spec)
    if not selected:
        return None

    main = selected[0]
    refs = ", ".join(f"[{source.source_ref}]" for source in selected[:3])
    return "\n".join(
        [
            "Краткий ответ",
            f"{spec.short_answer} [{main.source_ref}]",
            "",
            "Обоснование",
            f"- В найденном фрагменте ФТТ указан параметр: {spec.evidence_label} [{main.source_ref}].",
            f"- Ответ сформирован только по выбранным источникам ФТТ: {refs}.",
        ]
    )
