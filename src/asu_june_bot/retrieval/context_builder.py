from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from .models import SearchResult
from .parent_expansion import ParentExpander
from .query_intent import QueryIntent, QueryIntentResult
from .source_quality import is_primary_eligible, is_weak_source, source_quality, with_source_quality


@dataclass(slots=True)
class BuiltContext:
    primary_sources: list[SearchResult] = field(default_factory=list)
    supporting_sources: list[SearchResult] = field(default_factory=list)
    excluded_sources: list[SearchResult] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "primary_sources": [source.to_dict(preview_chars=1800) for source in self.primary_sources],
            "supporting_sources": [source.to_dict(preview_chars=1800) for source in self.supporting_sources],
            "excluded_sources": [source.to_dict(preview_chars=240) for source in self.excluded_sources],
            "diagnostics": self.diagnostics,
        }


def doc_type(result: SearchResult) -> str:
    return str(result.metadata.get("document_type") or "")


def text_lower(result: SearchResult) -> str:
    return " ".join((result.text or "").lower().split())


FTT_TABLE_8_STAGE_COLUMNS = {
    "Входит в объём проекта": ("Этапу 1 (ФТ1)", "Этап 1 (ФТ1)"),
    "Входит в объём проекта_2": ("Этапу 2 (ФТ2)", "Этап 2 (ФТ2)"),
    "Входит в объём проекта_3": ("Этапу 3 (ФТ3)", "Этап 3 (ФТ3)"),
    "Входит в объём проекта_4": ("Этапу 4 (ФТ4)", "Этап 4 (ФТ4)"),
    "Развитие ИС": ("Развитию ИС / не входит в текущий проект", "Развитие ИС / не входит в текущий проект"),
}


def _is_marked_cell(value: Any) -> bool:
    return str(value or "").strip().lower() in {"х", "x", "+", "да", "yes", "true", "1"}


def _ftt_table_8_stage_facts(result: SearchResult) -> list[str]:
    if doc_type(result) != "ФТТ":
        return []
    if str(result.metadata.get("table_id") or "") != "Table 8":
        return []

    cells = result.metadata.get("cells") or {}
    if not isinstance(cells, dict):
        return []

    requirement_id = str(result.metadata.get("requirement_id") or cells.get("№") or cells.get("N") or "").strip().rstrip(".")

    facts: list[str] = []
    for column, (phrase, canonical) in FTT_TABLE_8_STAGE_COLUMNS.items():
        if _is_marked_cell(cells.get(column)):
            basis = f" Основание: заполнена колонка «{column}»."
            if requirement_id:
                facts.append(f"Требование {requirement_id} относится к {phrase}. Каноническое значение: {canonical}.{basis}")
            else:
                facts.append(f"Строка таблицы относится к {phrase}. Каноническое значение: {canonical}.{basis}")
    return facts


def is_vector_only(result: SearchResult) -> bool:
    return "vector" in result.matched_by and "bm25" not in result.matched_by


def result_key(result: SearchResult) -> str:
    return str(result.metadata.get("chunk_id") or result.metadata.get("db_id") or result.source_id)


def has_label(result: SearchResult, label: str) -> bool:
    return label in set(result.diagnostics.get("rerank_labels") or [])


def has_noise_label(result: SearchResult) -> bool:
    labels = set(result.diagnostics.get("rerank_labels") or [])
    return any(label.startswith("penalty:software") or label.startswith("penalty:front_matter") for label in labels)


def _has_nsi_regulation_route(query: str) -> bool:
    lowered = " ".join((query or "").lower().split())
    return any(
        marker in lowered
        for marker in (
            "регламент ведения",
            "регламенты ведения",
            "регламентные документы",
            "методика/регламент",
            "методики ведения",
            "методика ведения",
            "правила ведения",
            "мвд",
        )
    )


def _has_nsi_reference_route(query: str) -> bool:
    lowered = " ".join((query or "").lower().split())
    return any(
        marker in lowered
        for marker in (
            "какие справочники нси",
            "справочники нси",
            "справочник нси",
            "реестр нси",
            "реестр объектов нси",
            "атрибутные составы",
            "атрибутный состав",
            "модель данных нси",
            "маппинг справочников",
            "маппинг атрибутов",
            "свок рд",
        )
    )


def _has_passport_route(query: str) -> bool:
    lowered = " ".join((query or "").lower().split())
    return any(marker in lowered for marker in ("паспорт ис", "паспорте ис", "паспорта ис", "паспорт информационной системы"))


def _has_passport_related_docs_route(query: str) -> bool:
    lowered = " ".join((query or "").lower().split())
    return _has_passport_route(lowered) and "связанн" in lowered and "документ" in lowered


def _has_passport_appendices_route(query: str) -> bool:
    lowered = " ".join((query or "").lower().split())
    return _has_passport_route(lowered) and any(
        marker in lowered for marker in ("какие приложения", "приложения перечислены", "приложения в паспорте", "приложения паспорта")
    )


def _has_passport_system_purpose_route(query: str) -> bool:
    lowered = " ".join((query or "").lower().split())
    return _has_passport_route(lowered) and any(
        marker in lowered
        for marker in (
            "сведения о системе",
            "назначение ис",
            "назначении ис",
            "назначение системы",
            "описание системы",
            "область применения",
        )
    )


def _is_passport_related_docs_evidence(result: SearchResult) -> bool:
    txt = text_lower(result)
    return (
        "таблица: table 2" in txt
        and "название документа" in txt
        and ("номер версии" in txt or "имя файла" in txt)
    ) or "связанные документы (этот документ должен читаться вместе с)" in txt


def _is_passport_appendices_evidence(result: SearchResult) -> bool:
    txt = text_lower(result)
    return (
        "таблица: table 3" in txt
        and ("приложение №" in txt or "план послеаварийного восстановления" in txt or "список источников" in txt)
    ) or "приложения (являются неотъемлемой частью документа)" in txt


def _is_passport_system_purpose_evidence(result: SearchResult) -> bool:
    txt = text_lower(result)
    return any(
        marker in txt
        for marker in (
            "полное наименование описываемой системы",
            "краткое наименование описываемой системы",
            "основное назначение системы",
            "система предназначена для формирования единой информационной среды",
            "описание системы и область применения",
            "описание и область применения",
            "область применения: пао",
            "настоящий паспорт ис подготовлен",
            "в границы описания включены",
        )
    )


def _is_nsi_reference_evidence(result: SearchResult) -> bool:
    txt = text_lower(result)
    metadata_text = " ".join(
        str(result.metadata.get(key) or "").lower()
        for key in ("document_type", "relative_path", "title", "table_id", "table_title", "row_header")
    )
    dictionary_names = (
        "единицы измерения",
        "должности",
        "отделы",
        "контрагенты",
        "организации",
        "объекты строительства",
        "виды прикрепляемых документов",
        "договоры",
        "инвестиционные проекты",
    )
    return (
        ("справочники:" in txt and any(name in txt for name in dictionary_names))
        or "атрибутный состав" in txt
        or "атрибутивный состав" in txt
        or "модель данных нси" in txt
        or "реестр объектов нси" in txt
        or "реестр используемых объектов нси" in txt
        or "корпоративный реестр нси" in txt
        or ("table 8" in metadata_text and "справочник" in txt)
    )


def _is_nsi_regulation_evidence(result: SearchResult) -> bool:
    metadata_text = " ".join(
        str(result.metadata.get(key) or "").lower()
        for key in ("relative_path", "title", "document_name")
    )
    if "реестр замечаний" in metadata_text:
        return False
    txt = text_lower(result)
    return any(
        marker in metadata_text or marker in txt
        for marker in (
            "регламент_ведения",
            "регламент ведения",
            "мвд_",
            "мвд ",
            "методика ведения",
            "методика ведения данных справочника",
        )
    )


def result_sections(result: SearchResult) -> set[str]:
    sections: set[str] = set()
    raw_sections = result.metadata.get("sections") or []
    if isinstance(raw_sections, list):
        sections.update(str(section).strip().rstrip(".") for section in raw_sections if str(section).strip())
    raw_section = result.metadata.get("section")
    if raw_section:
        sections.add(str(raw_section).strip().rstrip("."))
    cells = result.metadata.get("cells") or {}
    if isinstance(cells, dict):
        for key in ("№", "N", "Номер", "Требование ФТТ"):
            value = cells.get(key)
            if value:
                sections.add(str(value).strip().rstrip("."))
    return {section for section in sections if section}


def has_exact_mentioned_section(result: SearchResult, intent: QueryIntentResult) -> bool:
    mentioned = {str(section).strip().rstrip(".") for section in intent.mentioned_sections if str(section).strip()}
    if not mentioned:
        return False
    return bool(result_sections(result) & mentioned)


def _quality_summary(results: list[SearchResult]) -> dict[str, Any]:
    weak = [result for result in results if is_weak_source(result)]
    reasons: dict[str, int] = {}
    for result in weak:
        for reason in source_quality(result).get("reasons") or []:
            reasons[str(reason)] = reasons.get(str(reason), 0) + 1
    return {
        "assessed_count": len(results),
        "weak_count": len(weak),
        "weak_reasons": reasons,
    }


def _remove_result_by_key(results: list[SearchResult], key: str) -> list[SearchResult]:
    return [result for result in results if result_key(result) != key]


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _passport_table_id_for_query(query: str) -> str | None:
    if _has_passport_related_docs_route(query):
        return "Table 2"
    if _has_passport_appendices_route(query):
        return "Table 3"
    return None


def _is_passport_table_item(result: SearchResult, table_id: str) -> bool:
    return doc_type(result) == "Паспорт ИС" and str(result.metadata.get("table_id") or "") == table_id


def _passport_table_sort_key(result: SearchResult) -> tuple[int, int]:
    row_index = result.metadata.get("row_index")
    if row_index is None:
        return (0, _safe_int(result.metadata.get("chunk_index")))
    return (1, _safe_int(row_index))


class ContextBuilder:
    def __init__(
        self,
        primary_limit: int = 5,
        supporting_limit: int = 5,
        enable_source_quality_filter: bool = True,
        enable_parent_expansion: bool = True,
        parent_expander: ParentExpander | None = None,
    ):
        self.primary_limit = primary_limit
        self.supporting_limit = supporting_limit
        self.enable_source_quality_filter = enable_source_quality_filter
        self.enable_parent_expansion = enable_parent_expansion
        self.parent_expander = parent_expander or ParentExpander()

    def build(self, query: str, intent: QueryIntentResult, results: list[SearchResult], excluded: list[SearchResult] | None = None) -> BuiltContext:
        assessed_results = [with_source_quality(result, intent) for result in results] if self.enable_source_quality_filter else list(results)
        assessed_excluded = [with_source_quality(result, intent) for result in (excluded or [])] if self.enable_source_quality_filter else list(excluded or [])

        primary: list[SearchResult] = []
        supporting: list[SearchResult] = []
        excluded_sources: list[SearchResult] = []
        used_keys: set[str] = set()
        source_quality_excluded_primary = 0

        for result in assessed_results:
            key = result_key(result)
            if key in used_keys:
                continue
            bucket = self._bucket(query, intent, result)
            if bucket == "primary" and self.enable_source_quality_filter and not is_primary_eligible(result):
                bucket = "supporting" if len(supporting) < self.supporting_limit else "excluded"
                source_quality_excluded_primary += 1

            if bucket == "primary" and len(primary) < self.primary_limit:
                primary.append(result)
                used_keys.add(key)
            elif bucket == "supporting" and len(supporting) < self.supporting_limit:
                supporting.append(result)
                used_keys.add(key)
            else:
                excluded_sources.append(result)
                used_keys.add(key)

        primary_fallback_weak = False
        primary_fallback_promoted = False

        # Fallback: promote the best already bucketed candidate to primary.
        # The first pass intentionally marks every candidate as used, so fallback must not search for unused keys.
        if not primary and assessed_results:
            promoted = self._find_primary_fallback(assessed_results, require_primary_eligible=True)
            if promoted is not None:
                key = result_key(promoted)
                primary.append(promoted)
                supporting = _remove_result_by_key(supporting, key)
                excluded_sources = _remove_result_by_key(excluded_sources, key)
                primary_fallback_promoted = True
                primary_fallback_weak = is_weak_source(promoted)

        # Last resort: if all candidates are weak/non-eligible, keep the best non-noise result as primary
        # but keep the warning in diagnostics. This prevents no_sources for answerable but sparse project facts.
        if not primary and assessed_results:
            promoted = self._find_primary_fallback(assessed_results, require_primary_eligible=False)
            if promoted is not None:
                key = result_key(promoted)
                primary.append(promoted)
                supporting = _remove_result_by_key(supporting, key)
                excluded_sources = _remove_result_by_key(excluded_sources, key)
                primary_fallback_promoted = True
                primary_fallback_weak = is_weak_source(promoted)

        if self.enable_parent_expansion:
            candidate_pool = assessed_results + assessed_excluded
            primary, primary_parent_diag = self.parent_expander.expand(primary, candidate_pool)
            supporting, supporting_parent_diag = self.parent_expander.expand(supporting, candidate_pool)
        else:
            candidate_pool = assessed_results + assessed_excluded
            primary_parent_diag = {"parent_expansion": "disabled"}
            supporting_parent_diag = {"parent_expansion": "disabled"}

        primary, supporting, passport_table_diag = self._expand_passport_table_context(query, primary, supporting, candidate_pool)
        primary, supporting, table_header_semantics_diag = self._apply_table_header_semantics(primary, supporting)

        for result in assessed_excluded:
            key = result_key(result)
            if key not in used_keys:
                excluded_sources.append(result)
                used_keys.add(key)

        return BuiltContext(
            primary_sources=primary,
            supporting_sources=supporting,
            excluded_sources=excluded_sources,
            diagnostics={
                "builder": "ContextBuilder",
                "intent": intent.intent.value,
                "primary_count": len(primary),
                "supporting_count": len(supporting),
                "excluded_count": len(excluded_sources),
                "source_quality_filter": {
                    "enabled": self.enable_source_quality_filter,
                    "source_quality_excluded_primary": source_quality_excluded_primary,
                    "primary_fallback_promoted": primary_fallback_promoted,
                    "primary_fallback_weak": primary_fallback_weak,
                    "results": _quality_summary(assessed_results),
                    "excluded": _quality_summary(assessed_excluded),
                },
                "parent_expansion": {
                    "enabled": self.enable_parent_expansion,
                    "primary": primary_parent_diag,
                    "supporting": supporting_parent_diag,
                },
                "passport_table_expansion": passport_table_diag,
                "table_header_semantics": table_header_semantics_diag,
            },
        )

    def _find_primary_fallback(self, results: list[SearchResult], require_primary_eligible: bool) -> SearchResult | None:
        for result in results:
            if has_noise_label(result):
                continue
            if require_primary_eligible and self.enable_source_quality_filter and not is_primary_eligible(result):
                continue
            return result
        return None

    def _expand_passport_table_context(
        self,
        query: str,
        primary: list[SearchResult],
        supporting: list[SearchResult],
        candidates: list[SearchResult],
    ) -> tuple[list[SearchResult], list[SearchResult], dict[str, Any]]:
        table_id = _passport_table_id_for_query(query)
        if not table_id:
            return primary, supporting, {"applied": False, "reason": "not_passport_table_route"}

        table_items = sorted(
            [item for item in candidates if _is_passport_table_item(item, table_id)],
            key=_passport_table_sort_key,
        )
        if len(table_items) < 2:
            return primary, supporting, {"applied": False, "reason": "insufficient_table_items", "table_id": table_id, "items": len(table_items)}

        anchor = next((item for item in primary if _is_passport_table_item(item, table_id)), None)
        if anchor is None:
            anchor = next((item for item in supporting if _is_passport_table_item(item, table_id)), None)
        if anchor is None:
            return primary, supporting, {"applied": False, "reason": "no_selected_table_anchor", "table_id": table_id, "items": len(table_items)}

        seen_texts: set[str] = set()
        parts: list[str] = []
        expanded_keys: list[str] = []
        for item in table_items:
            text = " ".join((item.text or "").split())
            if not text or text in seen_texts:
                continue
            seen_texts.add(text)
            parts.append(text)
            expanded_keys.append(result_key(item))

        if len(parts) < 2:
            return primary, supporting, {"applied": False, "reason": "insufficient_unique_table_text", "table_id": table_id, "items": len(table_items)}

        combined_text = "\n\n".join(parts)
        diagnostics = dict(anchor.diagnostics or {})
        diagnostics["passport_table_expansion"] = {
            "applied": True,
            "table_id": table_id,
            "expanded_count": len(parts),
            "expanded_keys": expanded_keys,
        }
        labels = list(diagnostics.get("rerank_labels") or [])
        if "boost:passport_table_expanded" not in labels:
            labels.append("boost:passport_table_expanded")
        diagnostics["rerank_labels"] = labels
        metadata = dict(anchor.metadata or {})
        metadata["passport_table_expanded"] = True
        metadata["passport_table_expanded_count"] = len(parts)
        expanded_anchor = replace(anchor, text=combined_text, metadata=metadata, diagnostics=diagnostics)
        expanded_key_set = set(expanded_keys)

        replaced = False
        new_primary: list[SearchResult] = []
        for item in primary:
            if not replaced and result_key(item) == result_key(anchor):
                new_primary.append(expanded_anchor)
                replaced = True
            elif result_key(item) in expanded_key_set:
                continue
            else:
                new_primary.append(item)
        new_supporting: list[SearchResult] = []
        for item in supporting:
            if not replaced and result_key(item) == result_key(anchor):
                new_supporting.append(expanded_anchor)
                replaced = True
            elif result_key(item) in expanded_key_set:
                continue
            else:
                new_supporting.append(item)
        if not replaced:
            new_primary.insert(0, expanded_anchor)

        return new_primary, new_supporting, {
            "applied": True,
            "table_id": table_id,
            "expanded_count": len(parts),
            "expanded_keys": expanded_keys,
        }

    def _apply_table_header_semantics(
        self,
        primary: list[SearchResult],
        supporting: list[SearchResult],
    ) -> tuple[list[SearchResult], list[SearchResult], dict[str, Any]]:
        applied = 0

        def enrich(result: SearchResult) -> SearchResult:
            nonlocal applied
            facts = _ftt_table_8_stage_facts(result)
            if not facts:
                return result

            normalized_block = "Нормализованная семантика таблицы:\n" + "\n".join(f"- {fact}" for fact in facts)
            if normalized_block in result.text:
                return result

            metadata = dict(result.metadata or {})
            metadata["table_header_semantics_applied"] = True
            metadata["table_header_semantics_facts"] = facts

            diagnostics = dict(result.diagnostics or {})
            diagnostics["table_header_semantics"] = {
                "applied": True,
                "facts": facts,
                "table_id": result.metadata.get("table_id"),
                "requirement_id": result.metadata.get("requirement_id"),
            }

            applied += 1
            return replace(
                result,
                text=f"{result.text}\n\n{normalized_block}",
                metadata=metadata,
                diagnostics=diagnostics,
            )

        return [enrich(item) for item in primary], [enrich(item) for item in supporting], {
            "applied": applied > 0,
            "enriched_count": applied,
        }

    def _bucket(self, query: str, intent: QueryIntentResult, result: SearchResult) -> str:
        dt = doc_type(result)
        txt = text_lower(result)

        if has_noise_label(result):
            return "excluded"

        if _has_passport_related_docs_route(query):
            if dt == "Паспорт ИС" and _is_passport_related_docs_evidence(result):
                return "primary"
            if dt == "Паспорт ИС":
                return "supporting"
            return "excluded" if is_vector_only(result) else "supporting"

        if _has_passport_appendices_route(query):
            if dt == "Паспорт ИС" and _is_passport_appendices_evidence(result):
                return "primary"
            if dt == "Паспорт ИС":
                return "supporting"
            return "excluded" if is_vector_only(result) else "supporting"

        if _has_passport_system_purpose_route(query):
            if dt == "Паспорт ИС" and _is_passport_system_purpose_evidence(result):
                return "primary"
            if dt == "Паспорт ИС":
                return "supporting"
            return "excluded" if is_vector_only(result) else "supporting"

        if intent.intent == QueryIntent.DOCUMENT_OVERVIEW:
            if dt == "Паспорт ИС" and any(marker in txt for marker in ["в границы описания включены", "настоящий паспорт ис подготовлен", "архитектурные и эксплуатационные сведения"]):
                return "primary"
            if dt == "Паспорт ИС" and not is_vector_only(result):
                return "supporting"
            return "excluded" if is_vector_only(result) else "supporting"

        if intent.intent == QueryIntent.INTEGRATION_OVERVIEW:
            if dt in {"ЦТА", "Паспорт ИС", "СоИ AD", "СоИ Справочники", "ФТТ"}:
                return "primary" if not is_vector_only(result) else "supporting"
            if dt == "ПР":
                return "supporting"
            return "excluded" if is_vector_only(result) else "supporting"

        if intent.intent == QueryIntent.CTA_RECOVERY_RTO_RPO:
            if dt == "ЦТА" and any(marker in txt for marker in ["rto", "rpo", "время восстановления", "резервное копирование", "аварийный режим", "восстановление данных"]):
                return "primary"
            if dt == "ЦТА":
                return "supporting"
            if dt in {"ФТТ", "Паспорт ИС"}:
                return "supporting"
            return "excluded" if is_vector_only(result) else "supporting"

        if intent.intent == QueryIntent.REQUIREMENT_LOOKUP:
            # Если пользователь указал конкретный пункт, primary должен содержать только точное попадание
            # в этот пункт. Смежные ФТТ/ПР/ПМИ/встречи нужны как supporting context, но не как primary.
            if intent.mentioned_sections:
                if dt == "ФТТ" and has_exact_mentioned_section(result, intent):
                    return "primary"
                if dt in {"ФТТ", "ПР", "ПМИ"}:
                    return "supporting"
                return "excluded" if is_vector_only(result) else "supporting"

            if dt == "ФТТ" and (has_label(result, "boost:exact_section_mention") or not is_vector_only(result)):
                return "primary"
            if dt in {"ПР", "ПМИ"}:
                return "supporting"
            return "excluded" if is_vector_only(result) else "supporting"

        if _has_nsi_regulation_route(query):
            if dt == "Методика/Регламент НСИ" and _is_nsi_regulation_evidence(result):
                return "primary"
            if dt in {"Реестр НСИ", "Справочник НСИ", "СоИ Справочники", "ФТТ"}:
                return "supporting"
            return "excluded" if is_vector_only(result) else "supporting"

        if _has_nsi_reference_route(query):
            if dt in {"Реестр НСИ", "Справочник НСИ", "СоИ Справочники"} and _is_nsi_reference_evidence(result):
                return "primary"
            if dt == "Методика/Регламент НСИ" and _is_nsi_reference_evidence(result):
                return "supporting"
            if dt == "ФТТ":
                return "supporting"
            return "excluded" if is_vector_only(result) else "supporting"

        if intent.intent == QueryIntent.GENERAL_PROJECT_QUESTION:
            return "primary" if not is_vector_only(result) else "supporting"

        return "excluded"
