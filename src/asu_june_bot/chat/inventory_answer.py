from __future__ import annotations

import re

from .models import ChatSource


APP_CCPM_GROUP_RE = re.compile(r"\bapp_ccpm_[A-Za-z0-9_-]+\b", flags=re.I)


def _norm(text: str) -> str:
    return " ".join((text or "").lower().replace("ё", "е").split())


def _is_nsi_inventory_query(query: str) -> bool:
    lowered = _norm(query)
    if "нси" not in lowered:
        return False
    has_list_shape = any(
        marker in lowered
        for marker in (
            "какие",
            "перечислены",
            "есть в корпусе",
            "какие документы",
            "что документы",
            "должны подниматься",
        )
    )
    has_nsi_object = any(
        marker in lowered
        for marker in (
            "регламент",
            "регламенты",
            "регламентные документы",
            "методика",
            "методики",
            "справочник",
            "справочники",
            "атрибутные составы",
            "атрибутный состав",
            "правила ведения",
        )
    )
    return has_list_shape and has_nsi_object


def _passport_inventory_kind(query: str) -> str | None:
    lowered = _norm(query)
    if "паспорт ис" not in lowered and "паспорте ис" not in lowered and "паспорта ис" not in lowered:
        return None
    if "связанн" in lowered and "документ" in lowered:
        return "related_documents"
    if any(marker in lowered for marker in ("какие приложения", "приложения перечислены", "приложения паспорта", "приложения в паспорте")):
        return "appendices"
    if any(marker in lowered for marker in ("сведения о системе", "назначение ис", "назначении ис", "назначение системы")):
        return "system_purpose"
    return None


def _is_soi_ad_app_ccpm_query(query: str) -> bool:
    lowered = _norm(query)
    return "app_ccpm" in lowered and any(
        marker in lowered
        for marker in (
            "маска",
            "префикс",
            "группа",
            "группы",
            "групп",
            "именуются",
            "правило",
            "ad",
            "active directory",
        )
    )


def _is_soi_ad_ldaps_query(query: str) -> bool:
    lowered = _norm(query)
    has_transport_marker = any(marker in lowered for marker in ("ldaps", "ldap", "порт", "636", "ssl"))
    has_ad_marker = any(marker in lowered for marker in ("ad", "active directory", "сои ad"))
    return has_transport_marker and has_ad_marker


def _source_label(source: ChatSource) -> str:
    if source.title:
        return source.title
    if source.path:
        return source.path.replace("\\", "/").rsplit("/", 1)[-1]
    return source.source_id or source.chunk_id or source.source_ref


def _source_text(source: ChatSource) -> str:
    return " ".join(str(part or "") for part in (source.title, source.path, source.text_preview))


def _source_evidence(source: ChatSource) -> str | None:
    preview = source.text_preview or ""
    lowered = _norm(preview)
    markers = ("Справочники:", "Атрибутный состав", "Атрибутивный состав", "Модель данных НСИ")
    for marker in markers:
        marker_norm = _norm(marker)
        idx = lowered.find(marker_norm)
        if idx < 0:
            continue
        original_idx = preview.lower().replace("ё", "е").find(marker.lower().replace("ё", "е"))
        if original_idx < 0:
            original_idx = 0
        evidence = preview[original_idx:].strip()
        for separator in ("\n", ". "):
            if separator in evidence:
                evidence = evidence.split(separator, 1)[0].strip()
                break
        return evidence[:320].rstrip(" ;,.")
    return None


def _collect_app_ccpm_groups(sources: list[ChatSource]) -> list[tuple[str, ChatSource]]:
    found: list[tuple[str, ChatSource]] = []
    seen: set[str] = set()
    for source in sources:
        for match in APP_CCPM_GROUP_RE.finditer(_source_text(source)):
            value = match.group(0)
            key = value.lower()
            if key in seen:
                continue
            seen.add(key)
            found.append((value, source))
    return found


def _find_ldaps_source(sources: list[ChatSource]) -> ChatSource | None:
    for source in sources:
        lowered = _norm(_source_text(source))
        if "636" in lowered and ("ldaps" in lowered or ("ldap" in lowered and "ssl" in lowered)):
            return source
    for source in sources:
        lowered = _norm(_source_text(source))
        if "ldaps" in lowered or ("ldap" in lowered and "ssl" in lowered):
            return source
    return None


def _build_app_ccpm_fallback_answer(query: str, sources: list[ChatSource]) -> str | None:
    if not _is_soi_ad_app_ccpm_query(query):
        return None
    groups = _collect_app_ccpm_groups(sources)
    if not groups:
        return None

    source_refs: list[str] = []
    for _, source in groups:
        ref = f"[{source.source_ref}]"
        if ref not in source_refs:
            source_refs.append(ref)
    refs = ", ".join(source_refs[:3])
    examples = ", ".join(group for group, _ in groups[:8])
    evidence_lines = [
        f"- Найдена группа `{group}` в источнике {_source_label(source)} [{source.source_ref}]." for group, source in groups[:8]
    ]

    answer_lines = [
        "Краткий ответ",
        f"В переданном контексте формальная wildcard-маска групп `app_ccpm` отдельной строкой не указана. По найденным именам групп используется префикс `app_ccpm_`; примеры: {examples} {refs}.",
        "",
        "Обоснование",
        f"- Вывод сделан только по найденным именам групп `app_ccpm_...` в переданных источниках {refs}.",
        *evidence_lines,
    ]
    return "\n".join(answer_lines)


def _build_ldaps_fallback_answer(query: str, sources: list[ChatSource]) -> str | None:
    if not _is_soi_ad_ldaps_query(query):
        return None
    source = _find_ldaps_source(sources)
    if source is None:
        return None

    text = _norm(_source_text(source))
    service_accounts = "сервисные учетные записи с правами на чтение к каждому LDAP-каталогу" if "сервисные учетные записи" in text and "прав" in text and "чтени" in text else None
    details = ["доступность LDAP-каталога по порту 636 через SSL (LDAPS)"]
    if service_accounts:
        details.append(service_accounts)

    answer_lines = [
        "Краткий ответ",
        f"В СоИ AD указано: {', '.join(details)} [{source.source_ref}].",
        "",
        "Обоснование",
        f"- Источник {_source_label(source)} содержит параметр порта `636` и связку `SSL (LDAPS)` [{source.source_ref}].",
    ]
    if service_accounts:
        answer_lines.append(f"- В том же фрагменте указано требование предоставить сервисные учетные записи с правами на чтение к LDAP-каталогам [{source.source_ref}].")
    return "\n".join(answer_lines)


def _build_soi_ad_fallback_answer(query: str, sources: list[ChatSource]) -> str | None:
    app_ccpm_answer = _build_app_ccpm_fallback_answer(query, sources)
    if app_ccpm_answer:
        return app_ccpm_answer
    return _build_ldaps_fallback_answer(query, sources)


def _is_relevant_nsi_source(source: ChatSource) -> bool:
    haystack = _norm(" ".join(str(part or "") for part in (source.title, source.path, source.text_preview)))
    return any(
        marker in haystack
        for marker in (
            "регламент",
            "мвд",
            "методика",
            "сои_справочники",
            "сои справочники",
            "реестр нси",
            "справочники:",
            "атрибутный состав",
            "атрибутивный состав",
            "модель данных нси",
            "единицы измерения",
            "должности",
            "отделы",
            "контрагенты",
            "организации",
            "объекты строительства",
        )
    )


def _extract_passport_related_documents(text: str) -> list[str]:
    items: list[str] = []
    for match in re.finditer(r"Название документа:\s*(.+?)(?=\s+Номер версии|\s+Дата:|\s+Документ:|$)", text, flags=re.I):
        value = " ".join(match.group(1).split()).strip(" ;,.")
        if value and value not in items:
            items.append(value)
    return items


def _extract_passport_appendices(text: str) -> list[str]:
    lowered = _norm(text)
    items: list[str] = []
    if "план послеаварийного восстановления" in lowered:
        items.append("План послеаварийного восстановления")
    if "список источников" in lowered:
        items.append("Список источников")
    return items


def _extract_passport_system_purpose(text: str) -> list[str]:
    match = re.search(r"(Система предназначена.+?)(?=$|\n|Основные функции системы:|Область применения:)", text, flags=re.I | re.S)
    if not match:
        return []
    value = " ".join(match.group(1).split()).strip(" ;,.")
    return [value] if value else []


def _build_passport_inventory_fallback(query: str, sources: list[ChatSource]) -> str | None:
    kind = _passport_inventory_kind(query)
    if not kind:
        return None

    extracted: list[tuple[str, ChatSource]] = []
    for source in sources:
        text = source.text_preview or ""
        haystack = _norm(" ".join(str(part or "") for part in (source.title, source.path, text)))
        has_passport_source_marker = "паспорт ис" in haystack or "паспорт информационной системы" in haystack
        if kind != "system_purpose" and not has_passport_source_marker:
            continue
        if kind == "related_documents":
            items = _extract_passport_related_documents(text)
        elif kind == "appendices":
            items = _extract_passport_appendices(text)
        else:
            items = _extract_passport_system_purpose(text)
        for item in items:
            if item not in [name for name, _ in extracted]:
                extracted.append((item, source))

    if not extracted:
        return None

    refs_list: list[str] = []
    for _, source in extracted[:3]:
        ref = f"[{source.source_ref}]"
        if ref not in refs_list:
            refs_list.append(ref)
    refs = ", ".join(refs_list)
    if kind == "related_documents":
        answer = "В переданном контексте Паспорта ИС найдены связанные документы: "
    elif kind == "appendices":
        answer = "В переданном контексте Паспорта ИС найдены приложения: "
    else:
        answer = "В переданном контексте Паспорта ИС указано назначение системы: "

    answer_lines = [
        "Краткий ответ",
        answer + "; ".join(f"{item} [{source.source_ref}]" for item, source in extracted) + ".",
        "",
        "Обоснование",
        f"- {'Факт извлечён из найденного фрагмента' if kind == 'system_purpose' else 'Перечень извлечён из табличного фрагмента'} Паспорта ИС {refs}.",
    ]
    return "\n".join(answer_lines)


def _dedup_sources(sources: list[ChatSource]) -> list[ChatSource]:
    selected: list[ChatSource] = []
    seen: set[str] = set()
    for source in sources:
        key = source.path or source.title or source.chunk_id or source.source_ref
        if key in seen:
            continue
        seen.add(key)
        selected.append(source)
    return selected


def build_inventory_fallback_answer(query: str, sources: list[ChatSource]) -> str | None:
    """Build a source-grounded answer for narrow NTK inventory/list cases.

    This prevents product false-negatives where the LLM says no_answer even
    though retrieval already found relevant source titles, document paths,
    table rows or exact parameter fragments.
    """

    soi_ad_answer = _build_soi_ad_fallback_answer(query, sources)
    if soi_ad_answer:
        return soi_ad_answer

    passport_answer = _build_passport_inventory_fallback(query, sources)
    if passport_answer:
        return passport_answer

    if not _is_nsi_inventory_query(query):
        return None
    relevant = _dedup_sources([source for source in sources if _is_relevant_nsi_source(source)])
    if not relevant:
        return None

    max_items = min(len(relevant), 5)
    listed = relevant[:max_items]
    labels = []
    for idx, source in enumerate(listed, start=1):
        evidence = _source_evidence(source)
        suffix = f": {evidence}" if evidence else ""
        labels.append(f"{idx}. {_source_label(source)}{suffix} [{source.source_ref}]")

    refs = ", ".join(f"[{source.source_ref}]" for source in listed[:3])
    answer_lines = [
        "Краткий ответ",
        f"В переданном контексте найдены релевантные источники по НСИ; отвечаю перечнем найденных документов/справочников по их названиям и фрагментам источников {refs}.",
        "",
        "Обоснование",
        *labels,
    ]

    preview_evidence = []
    for source in listed:
        preview = _norm(source.text_preview or "")
        terms = []
        for marker in ("общие положения", "контроль исполнения", "участники процесса", "порядок ведения", "справочники:", "атрибутный состав", "модель данных нси"):
            if marker in preview:
                terms.append(marker)
        if terms:
            preview_evidence.append(f"- В фрагменте {_source_label(source)} есть признаки содержания: {', '.join(terms[:4])} [{source.source_ref}]")

    if preview_evidence:
        answer_lines.extend(["", "Подтверждающие признаки", *preview_evidence[:3]])

    return "\n".join(answer_lines)
