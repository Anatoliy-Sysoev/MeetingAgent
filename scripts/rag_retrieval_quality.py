from __future__ import annotations

import re
from collections import Counter
from typing import Any

from rag_bucket_quality import bucket_doc_types, bucket_expansion, bucket_source_signal


NO_ANSWER_MARKERS = (
    "недостаточно информации",
    "недостаточно данных",
    "не найдено",
    "не удалось найти",
    "не подтверждено",
    "не содержат информации",
    "в найденных фрагментах недостаточно",
    "в источниках отсутств",
)

WEAK_SOURCE_REASON = "weak_source_quality_gate"

STOPWORDS = {
    "что", "как", "какие", "какая", "какой", "каким", "где", "когда", "и", "или",
    "в", "во", "на", "по", "про", "для", "с", "со", "из", "от", "до", "при",
    "это", "есть", "сказано", "указано", "описано", "относятся", "относится",
    "требования", "требований", "проект", "система", "системы", "реализовано", "реализована",
}

DOMAIN_TERMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("ftt", ("фтт", "функционально-технические требования", "требования", "таблица 8")),
    ("pr", ("проектное решение", "пр", "сценарии функционирования", "бизнес-процесс", "статусная схема", "таблица соответствия")),
    ("cta", ("цта", "целевая техническая архитектура", "архитектура", "kubernetes", "postgresql", "minio", "loki", "grafana", "siem", "rto", "rpo")),
    ("soi_ad", ("сои ad", "active directory", "ad", "ldaps", "группы ad", "авторизация", "синхронизация", "учетные записи", "порт 636")),
    ("soi_nsi", ("сои справочники", "нси", "mdr", "кшд", "справочники", "справочник", "bearer token", "rest api")),
    ("construction_control", ("смр", "строительный контроль", "замечания", "предписание", "инспекционные документы", "акт проверки", "акт устранения")),
    ("edms", ("новадок", "эдо", "документооборот")),
    ("signature", ("эцп", "электронная подпись", "подписание")),
    ("analytics", ("аналитика", "дашборд", "дашборды", "витрина", "отчет", "отчёт")),
    ("performance", ("производительность", "нагрузочное", "2520", "600", "120", "пользователей")),
    ("export", ("экспорт", "выгрузка", "pdf", "excel", "csv", "xml", "печатные формы")),
    ("pmi", ("пми", "сфт", "снт", "сценарии", "испытания", "программа и методика")),
    ("psi", ("пси", "протокол испытаний", "рекомендации", "открытые вопросы")),
    ("passport", ("паспорт ис", "паспорт информационной системы")),
)

FTT_SECTION_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("4.1", ("инспекционные документы", "формирования, ведения и подписания", "строительный контроль", "эцп")),
    ("4.2.1", ("результаты проведения инспекционной деятельности", "проверки", "замечания", "создание замечания")),
    ("4.2.2", ("автоматическая генерации инспекционных документов", "акт проверки", "предписания")),
    ("4.2.3", ("фото", "видео", "фотофиксация", "видеофиксация", "недостатков")),
    ("4.2.4", ("актов об устранении", "устранении недостатков", "акт устранения")),
    ("4.2.5", ("новадок", "эцп", "электронная подпись", "подписание", "предписание", "акты проверки", "акты устранения")),
    ("4.2.6", ("уведомление контрагенту", "вызова инспектора", "приемки работ", "приёмки работ", "рассылки уведомления")),
    ("4.2.7", ("статусы карточек", "статусы документов", "статусы недостатков", "статусная модель")),
    ("4.2.8", ("аналитической информации", "недостаткам", "замечаниям", "срок", "оповещении")),
    ("4.2.9", ("типовых нарушений", "нормативные правовые акты", "нормативных правовых актов", "нтд")),
    ("4.2.10", ("назначение", "замещение", "инспектора ск", "ответственный инспектор")),
    ("4.3", ("аналитика", "дашборд", "дашборды", "прогресс", "контроль устранения")),
    ("9.6", ("сквозное кодирование", "связи между модулями", "тэгирование", "тегирование")),
    ("10.8", ("экспорт", "pdf", "xml", "excel", "csv", "отфильтрованных данных", "печатные формы")),
)

DOC_TYPE_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("ftt", ("фтт", "функционально-технические", "задание заказчика", "таблица 8")),
    ("pr", ("проектное решение", "пр_смр", "строительный_контроль", "сценарии функционирования", "статусная схема", "модуль строительный контроль")),
    ("cta", ("цта", "целевая техническая архитектура", "архитектура", "kubernetes", "postgresql", "minio", "loki", "grafana")),
    ("soi_ad", ("сои_ad", "active directory", "ad.docx", "ldaps", "группы ad", "учетные записи")),
    ("soi_nsi", ("сои_справочники", "справочники", "mdr", "кшд", "bearer", "нси")),
    ("pmi", ("пми", "программа и методика", "сценарии испытаний", "сфт", "снт")),
    ("psi", ("пси", "протокол испытаний")),
    ("passport", ("паспорт ис", "паспорт_ис")),
)

QUERY_TO_DOC_TYPE: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("ftt", ("фтт", "требован", "4.1", "4.2", "4.3", "9.6", "10.8", "2520", "600 одновременно")),
    ("pr", ("проектное решение", "как реализовано", "статус", "бизнес-процесс", "сценарии функционирования", "роль", "дашборд", "предписание", "акт проверки")),
    ("cta", ("цта", "архитектур", "postgresql", "minio", "kubernetes", "loki", "grafana", "siem", "rto", "rpo", "контур", "сервер")),
    ("soi_ad", ("active directory", "ldaps", "ldap", "групп", "учетн", "авторизац", "ad", "app_ccpm", "dn", "upn", "636")),
    ("soi_nsi", ("mdr", "кшд", "справоч", "нси", "bearer", "rest api", "external_id", "deletion_mark", "is_actual", "контрагент", "организац")),
    ("pmi", ("пми", "сфт", "снт", "сценар", "методик")),
    ("psi", ("пси", "протокол испыт", "открытые вопросы", "рекомендац")),
)

TIER1_DOC_TYPES = {"ftt", "pr", "cta", "soi_ad", "soi_nsi"}
TIER2_DOC_TYPES = {"pmi", "psi", "passport"}
TIER3_PATH_HINTS = (
    "transcript", "транскрип", "subtitles", ".srt", ".vtt", "макет", "макеты", "инструкции сайта",
    "_analysis", "site_review", "site export", "docs_html", "docs_text", "pages_html", "pages_text",
)
TIER4_PATH_HINTS = (
    "api-", "raw", "dump", "json", "har", "network", "console", "dom.html", "ui-inventory", "mutating-requests",
)
LOW_PRIORITY_EXTENSIONS = {".json", ".har", ".html", ".htm", ".srt", ".vtt", ".tsv", ".log"}


def normalize_text(text: str) -> str:
    return " ".join(str(text or "").lower().replace("ё", "е").split())


def tokenize(text: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[a-zа-я0-9]+(?:[.-][a-zа-я0-9]+)*", normalize_text(text), flags=re.IGNORECASE)
        if len(token) >= 2 and token not in STOPWORDS
    ]


def extract_numbers_and_sections(text: str) -> set[str]:
    lowered = normalize_text(text)
    return set(re.findall(r"\b\d+(?:\.\d+)+\b|\b\d{2,5}\b", lowered))


def extract_ftt_sections(text: str) -> set[str]:
    numbers = extract_numbers_and_sections(text)
    known = {section for section, _ in FTT_SECTION_HINTS}
    return {number for number in numbers if number in known}


def extension_from_path(relative_path: str) -> str:
    path = str(relative_path or "").lower()
    match = re.search(r"(\.[a-z0-9]+)$", path)
    return match.group(1) if match else ""


def is_low_priority_question(question: str) -> bool:
    lowered = normalize_text(question)
    return any(term in lowered for term in ("макет", "инструкция сайта", "транскрип", "лог", "json", "api dump", "har", "dom"))


def source_tier(relative_path: str, actual_doc_type: str | None, question: str = "") -> dict[str, Any]:
    path = normalize_text(relative_path)
    ext = extension_from_path(relative_path)
    explicit_low_priority_question = is_low_priority_question(question)
    if actual_doc_type in TIER1_DOC_TYPES:
        return {"source_tier": 1, "source_tier_reason": f"tier1_doc_type:{actual_doc_type}", "source_tier_penalty": 0.0}
    if actual_doc_type in TIER2_DOC_TYPES:
        return {"source_tier": 2, "source_tier_reason": f"tier2_doc_type:{actual_doc_type}", "source_tier_penalty": 0.0}
    if any(hint in path for hint in TIER4_PATH_HINTS) or ext in LOW_PRIORITY_EXTENSIONS:
        penalty = 0.02 if explicit_low_priority_question else 0.22
        return {"source_tier": 4, "source_tier_reason": "tier4_raw_export_or_low_priority_extension", "source_tier_penalty": penalty}
    if any(hint in path for hint in TIER3_PATH_HINTS):
        penalty = 0.02 if explicit_low_priority_question else 0.16
        return {"source_tier": 3, "source_tier_reason": "tier3_transcript_mockup_or_analysis", "source_tier_penalty": penalty}
    return {"source_tier": 2, "source_tier_reason": "tier2_default_project_artifact", "source_tier_penalty": 0.0}


def doc_type_routing_signal(question: str, actual_doc_type: str | None, relative_path: str) -> dict[str, Any]:
    expected_docs = expected_doc_types(question)
    tier = source_tier(relative_path, actual_doc_type, question)
    doc_type_match = bool(actual_doc_type and actual_doc_type in expected_docs)
    doc_type_mismatch = bool(expected_docs and actual_doc_type and actual_doc_type not in expected_docs)
    unknown_when_expected = bool(expected_docs and not actual_doc_type)
    hard_route_penalty = 0.0
    hard_route_boost = 0.0
    if doc_type_match:
        hard_route_boost += 0.14
    if doc_type_mismatch:
        hard_route_penalty += 0.18
    if unknown_when_expected and int(tier["source_tier"]) >= 3:
        hard_route_penalty += 0.18
    elif unknown_when_expected:
        hard_route_penalty += 0.08
    hard_route_penalty += float(tier["source_tier_penalty"])
    return {
        "expected_doc_types": sorted(expected_docs),
        "actual_doc_type": actual_doc_type,
        "doc_type_match": doc_type_match,
        "doc_type_mismatch": doc_type_mismatch,
        "unknown_doc_type_when_expected": unknown_when_expected,
        "hard_route_boost": round(hard_route_boost, 6),
        "hard_route_penalty": round(min(hard_route_penalty, 0.45), 6),
        **tier,
    }


def ftt_section_signal(question: str, document: str, relative_path: str = "") -> dict[str, Any]:
    question_norm = normalize_text(question)
    document_norm = normalize_text(document)
    path_norm = normalize_text(relative_path)
    query_sections = extract_ftt_sections(question_norm)
    document_sections = extract_ftt_sections(document_norm + " " + path_norm)
    exact_matches = sorted(query_sections & document_sections)

    hint_matches: dict[str, list[str]] = {}
    for section, hints in FTT_SECTION_HINTS:
        if section not in query_sections:
            continue
        hits = [hint for hint in hints if hint in document_norm]
        if hits:
            hint_matches[section] = hits[:10]

    has_ftt_path = path_doc_type(path_norm) == "ftt"
    boost = 0.0
    if exact_matches and has_ftt_path:
        boost += 0.28
    elif exact_matches:
        boost += 0.18
    if hint_matches:
        boost += min(0.18, 0.06 * sum(len(v) for v in hint_matches.values()))
    if query_sections and has_ftt_path:
        boost += 0.08

    return {
        "query_ftt_sections": sorted(query_sections),
        "document_ftt_sections": sorted(document_sections),
        "exact_ftt_section_matches": exact_matches,
        "ftt_section_hint_matches": hint_matches,
        "ftt_section_boost": round(min(boost, 0.42), 6),
        "ftt_path_match": has_ftt_path,
    }


def extract_domain_terms(text: str) -> set[str]:
    lowered = normalize_text(text)
    terms: set[str] = set()
    for label, variants in DOMAIN_TERMS:
        if any(variant in lowered for variant in variants):
            terms.add(label)
    for section, hints in FTT_SECTION_HINTS:
        if section in lowered or any(hint in lowered for hint in hints):
            terms.add(f"ftt_section:{section}")
    for doc_type, hints in QUERY_TO_DOC_TYPE:
        if any(hint in lowered for hint in hints):
            terms.add(f"doc_type:{doc_type}")
    terms.update(f"doc_type:{doc_type}" for doc_type in bucket_doc_types(text))
    return terms


def expected_doc_types(question: str) -> set[str]:
    lowered = normalize_text(question)
    out: set[str] = set()
    for doc_type, hints in QUERY_TO_DOC_TYPE:
        if any(hint in lowered for hint in hints):
            out.add(doc_type)
    out.update(bucket_doc_types(question))
    return out


def path_doc_type(relative_path: str) -> str | None:
    path = normalize_text(relative_path)
    for doc_type, hints in DOC_TYPE_HINTS:
        if any(hint in path for hint in hints):
            return doc_type
    return None


def build_quality_expansion(question: str) -> str:
    lowered = normalize_text(question)
    extras: list[str] = []

    docs = expected_doc_types(question)
    if "ftt" in docs:
        extras.extend(["ФТТ", "функционально-технические требования", "Таблица 8", "Этап 1", "СМР Строительный контроль"])
    if "pr" in docs:
        extras.extend(["Проектное решение", "сценарии функционирования", "статусная схема", "роли", "права доступа", "Core API", "Disk API", "Building API"])
    if "cta" in docs:
        extras.extend(["ЦТА", "целевая техническая архитектура", "PostgreSQL", "MinIO", "Kubernetes", "Grafana Loki", "SIEM", "RTO", "RPO", "контур"])
    if "soi_ad" in docs:
        extras.extend(["СОИ AD", "Active Directory", "LDAPS", "порт 636", "группы AD", "учетные записи", "авторизация", "DN", "UPN", "app_ccpm"])
    if "soi_nsi" in docs:
        extras.extend(["СОИ Справочники", "MDR", "КШД", "НСИ", "справочники", "Bearer Token", "REST API", "external_id", "deletion_mark"])
    if "pmi" in docs:
        extras.extend(["ПМИ", "СФТ", "СНТ", "сценарии испытаний", "программа и методика испытаний"])
    if "psi" in docs:
        extras.extend(["ПСИ", "протокол испытаний", "открытые вопросы", "рекомендации", "результаты испытаний"])

    extras.extend(bucket_expansion(question))

    for section, hints in FTT_SECTION_HINTS:
        if section in lowered or any(hint in lowered for hint in hints):
            extras.append(section)
            extras.extend(hints)

    if "инспекцион" in lowered or "эцп" in lowered or "новадок" in lowered:
        extras.extend(["инспекционные документы", "ЭЦП", "электронная подпись", "НОВАДОК", "4.1", "4.2.5"])
    if "пользовател" in lowered or "производитель" in lowered or "нагруз" in lowered:
        extras.extend(["2520", "600", "120", "нагрузочное тестирование", "производительность", "Таблица 9", "Таблица 10"])
    if "сквоз" in lowered or "кодирован" in lowered or "тэг" in lowered or "тег" in lowered:
        extras.extend(["9.6", "сквозное кодирование", "связи между модулями", "тэгирование", "тегирование"])
    if "аналит" in lowered or "дашборд" in lowered:
        extras.extend(["4.3", "4.2.8", "аналитика", "дашборды", "отчеты", "отчёты"])
    if "замечан" in lowered or "предписан" in lowered:
        extras.extend(["4.2.1", "4.2.2", "4.2.5", "4.2.8", "замечания", "предписания", "строительный контроль"])
    if "экспорт" in lowered or "выгруз" in lowered or "pdf" in lowered or "excel" in lowered or "csv" in lowered:
        extras.extend(["10.8", "экспорт", "выгрузка", "PDF", "Excel", "CSV", "XML", "печатные формы"])

    seen: set[str] = set()
    unique = []
    for item in extras:
        key = normalize_text(item)
        if key and key not in seen:
            seen.add(key)
            unique.append(item)
    if not unique:
        return question
    return question + "\n" + " ".join(unique)


def lexical_score(question: str, document: str, relative_path: str = "") -> dict[str, Any]:
    question_norm = normalize_text(question)
    document_norm = normalize_text(document)
    path_norm = normalize_text(relative_path)

    q_tokens = tokenize(question_norm)
    d_tokens = set(tokenize(document_norm + " " + path_norm))
    q_counter = Counter(q_tokens)

    matched_tokens = sorted({token for token in q_counter if token in d_tokens})
    token_overlap = len(matched_tokens) / max(len(set(q_tokens)), 1)

    q_numbers = extract_numbers_and_sections(question_norm)
    d_numbers = extract_numbers_and_sections(document_norm + " " + path_norm)
    matched_numbers = sorted(q_numbers & d_numbers)
    number_overlap = len(matched_numbers) / max(len(q_numbers), 1) if q_numbers else 0.0

    q_terms = extract_domain_terms(question_norm)
    d_terms = extract_domain_terms(document_norm + " " + path_norm)
    matched_terms = sorted(q_terms & d_terms)
    term_overlap = len(matched_terms) / max(len(q_terms), 1) if q_terms else 0.0

    phrase_matches: list[str] = []
    for section, hints in FTT_SECTION_HINTS:
        if section in question_norm and section in document_norm:
            phrase_matches.append(section)
        for hint in hints:
            if hint in question_norm and hint in document_norm:
                phrase_matches.append(hint)

    bucket_signal = bucket_source_signal(question_norm, document_norm, path_norm)
    bucket_boost = float(bucket_signal.get("bucket_boost", 0.0) or 0.0)
    ftt_signal = ftt_section_signal(question_norm, document_norm, path_norm)
    ftt_section_boost = float(ftt_signal.get("ftt_section_boost", 0.0) or 0.0)

    actual_doc = path_doc_type(path_norm)
    routing = doc_type_routing_signal(question_norm, actual_doc, relative_path)
    doc_type_match = bool(routing["doc_type_match"])
    doc_type_mismatch = bool(routing["doc_type_mismatch"])
    path_boost = 0.16 if doc_type_match else 0.0
    hard_route_boost = float(routing.get("hard_route_boost", 0.0) or 0.0)
    hard_route_penalty = float(routing.get("hard_route_penalty", 0.0) or 0.0)

    phrase_bonus = min(0.30, 0.06 * len(set(phrase_matches)))
    number_bonus = 0.30 * number_overlap
    term_bonus = 0.34 * term_overlap
    token_bonus = 0.24 * token_overlap
    mismatch_penalty = 0.10 if doc_type_mismatch else 0.0

    score = max(0.0, min(1.0, token_bonus + term_bonus + number_bonus + phrase_bonus + path_boost + hard_route_boost + bucket_boost + ftt_section_boost - mismatch_penalty - hard_route_penalty))

    return {
        "lexical_score": round(score, 6),
        "token_overlap": round(token_overlap, 6),
        "term_overlap": round(term_overlap, 6),
        "number_overlap": round(number_overlap, 6),
        "matched_tokens": matched_tokens[:20],
        "matched_terms": matched_terms,
        "matched_numbers": matched_numbers,
        "phrase_matches": sorted(set(phrase_matches)),
        "path_boost": path_boost,
        "bucket_boost": bucket_boost,
        "bucket_signals": bucket_signal.get("bucket_signals", []),
        **routing,
        **ftt_signal,
    }


def rerank_contexts(question: str, contexts: list[dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
    reranked: list[dict[str, Any]] = []
    for ctx in contexts:
        meta = dict(ctx.get("metadata", {}))
        vector_score = float(ctx.get("score", 0.0))
        q = lexical_score(question, str(ctx.get("document", "")), str(meta.get("relative_path", "")))
        lexical = float(q["lexical_score"])
        final_score = min(1.0, 0.55 * vector_score + 0.45 * lexical)
        if lexical >= 0.35:
            final_score = min(1.0, final_score + 0.10)
        if q.get("matched_numbers"):
            final_score = min(1.0, final_score + 0.09)
        if q.get("doc_type_match"):
            final_score = min(1.0, final_score + 0.10)
        if q.get("exact_ftt_section_matches"):
            final_score = min(1.0, final_score + 0.14)
        if q.get("ftt_section_hint_matches"):
            final_score = min(1.0, final_score + 0.08)
        if q.get("bucket_signals"):
            final_score = min(1.0, final_score + min(0.12, float(q.get("bucket_boost", 0.0) or 0.0)))
        final_score = min(1.0, final_score + float(q.get("hard_route_boost", 0.0) or 0.0))
        final_score = max(0.0, final_score - float(q.get("hard_route_penalty", 0.0) or 0.0))
        if q.get("doc_type_mismatch"):
            final_score = max(0.0, final_score - 0.10)
        meta["retrieval"] = "hybrid_vector_lexical_bucket_section_tiered"
        meta["quality"] = {
            **q,
            "vector_score": round(vector_score, 6),
            "final_score": round(final_score, 6),
        }
        reranked.append({**ctx, "metadata": meta, "score": final_score, "distance": 1.0 - final_score})

    reranked.sort(key=lambda item: float(item.get("score", 0.0)), reverse=True)
    return reranked[:top_k]


def source_quality_decision(sources: list[dict[str, Any]], min_lexical: float = 0.20) -> dict[str, Any]:
    if not sources:
        return {"ok": False, "reason": "no_sources"}
    top = sources[0]
    quality = top.get("quality") or {}
    lexical = float(quality.get("lexical_score", 0.0) or 0.0)
    matched_terms = quality.get("matched_terms") or []
    matched_numbers = quality.get("matched_numbers") or []
    phrase_matches = quality.get("phrase_matches") or []
    path_boost = float(quality.get("path_boost", 0.0) or 0.0)
    bucket_boost = float(quality.get("bucket_boost", 0.0) or 0.0)
    ftt_section_boost = float(quality.get("ftt_section_boost", 0.0) or 0.0)
    hard_route_boost = float(quality.get("hard_route_boost", 0.0) or 0.0)
    bucket_signals = quality.get("bucket_signals") or []
    doc_type_match = bool(quality.get("doc_type_match"))
    ftt_section_match = bool(quality.get("exact_ftt_section_matches") or quality.get("ftt_section_hint_matches"))
    source_tier_value = int(quality.get("source_tier") or 2)
    strong_anchor = bool(matched_terms or matched_numbers or phrase_matches or path_boost > 0 or bucket_boost > 0 or ftt_section_boost > 0 or hard_route_boost > 0 or bucket_signals or doc_type_match or ftt_section_match)
    ok = (lexical >= min_lexical or strong_anchor) and not (source_tier_value >= 4 and not doc_type_match and lexical < 0.35)
    return {
        "ok": ok,
        "reason": None if ok else WEAK_SOURCE_REASON,
        "lexical_score": lexical,
        "matched_terms": matched_terms,
        "matched_numbers": matched_numbers,
        "phrase_matches": phrase_matches,
        "path_boost": path_boost,
        "bucket_boost": bucket_boost,
        "ftt_section_boost": ftt_section_boost,
        "hard_route_boost": hard_route_boost,
        "hard_route_penalty": quality.get("hard_route_penalty"),
        "source_tier": quality.get("source_tier"),
        "source_tier_reason": quality.get("source_tier_reason"),
        "bucket_signals": bucket_signals,
        "doc_type_match": doc_type_match,
        "doc_type_mismatch": quality.get("doc_type_mismatch"),
        "ftt_section_match": ftt_section_match,
        "expected_doc_types": quality.get("expected_doc_types") or [],
        "actual_doc_type": quality.get("actual_doc_type"),
        "exact_ftt_section_matches": quality.get("exact_ftt_section_matches") or [],
        "ftt_section_hint_matches": quality.get("ftt_section_hint_matches") or {},
    }


def quality_confidence(sources: list[dict[str, Any]], threshold: float, answer: str | None = None) -> float:
    if not sources:
        return 0.0
    top = sources[0]
    top_score = float(top.get("score", 0.0))
    quality = top.get("quality") or {}
    lexical = float(quality.get("lexical_score", 0.0) or 0.0)
    term_overlap = float(quality.get("term_overlap", 0.0) or 0.0)
    number_overlap = float(quality.get("number_overlap", 0.0) or 0.0)
    matched_terms = quality.get("matched_terms") or []
    matched_numbers = quality.get("matched_numbers") or []
    doc_type_match = bool(quality.get("doc_type_match"))
    bucket_signals = quality.get("bucket_signals") or []
    ftt_section_match = bool(quality.get("exact_ftt_section_matches") or quality.get("ftt_section_hint_matches"))
    source_tier_value = int(quality.get("source_tier") or 2)

    base = min(0.90, max(0.0, (top_score - threshold) / max(1.0 - threshold, 1e-6)))
    if lexical < 0.15:
        base *= 0.45
    elif lexical < 0.30:
        base *= 0.70
    else:
        base = min(0.94, base + 0.10)

    if matched_terms:
        base = min(0.96, base + 0.04 * min(len(matched_terms), 3))
    if matched_numbers:
        base = min(0.97, base + 0.08 * min(len(matched_numbers), 2))
    if doc_type_match:
        base = min(0.97, base + 0.08)
    if ftt_section_match:
        base = min(0.98, base + 0.10)
    if bucket_signals:
        base = min(0.97, base + 0.06)
    if term_overlap >= 0.75 or number_overlap >= 0.75:
        base = min(0.98, base + 0.08)
    if source_tier_value >= 3 and not doc_type_match:
        base *= 0.65
    if source_tier_value >= 4 and not doc_type_match:
        base *= 0.45

    if answer and has_no_answer_marker(answer):
        base = min(base, 0.25)
    return round(max(0.0, min(base, 0.98)), 4)


def answer_sections(answer: str) -> dict[str, str]:
    text = str(answer or "")
    first_pos: int | None = None
    for marker in ("Ограничения:", "Источники:", "Обоснование:"):
        pos = text.lower().find(marker.lower())
        if pos >= 0 and (first_pos is None or pos < first_pos):
            first_pos = pos
    if first_pos is None:
        return {"main": text, "tail": ""}
    return {"main": text[:first_pos], "tail": text[first_pos:]}


def has_no_answer_marker(answer: str) -> bool:
    sections = answer_sections(answer)
    lowered_main = normalize_text(sections["main"])
    return any(marker in lowered_main for marker in NO_ANSWER_MARKERS)
