from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any


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

STOPWORDS = {
    "что", "как", "какие", "какая", "какой", "каким", "где", "когда", "и", "или",
    "в", "во", "на", "по", "про", "для", "с", "со", "из", "от", "до", "при",
    "это", "есть", "сказано", "указано", "описано", "относятся", "относится",
    "требования", "требований", "проект", "система", "системы",
}

DOMAIN_TERMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("ftt", ("фтт", "функционально-технические требования", "требования")),
    ("construction_control", ("смр", "строительный контроль", "замечания", "предписание", "инспекционные документы")),
    ("edms", ("новадок", "эдо", "документооборот")),
    ("signature", ("эцп", "электронная подпись", "подписание")),
    ("analytics", ("аналитика", "дашборд", "витрина", "отчет", "отчёт")),
    ("performance", ("производительность", "нагрузочное", "2520", "600", "120", "пользователей")),
    ("pmi", ("пми", "сфт", "снт", "сценарии", "испытания")),
    ("psi", ("пси", "протокол испытаний", "рекомендации", "открытые вопросы")),
    ("ad", ("active directory", "ad", "ldaps", "группы ad", "авторизация")),
    ("nsi", ("нси", "mdr", "кшд", "справочники", "справочник")),
    ("cta", ("цта", "архитектура", "kubernetes", "postgresql", "minio", "loki", "grafana")),
)

FTT_SECTION_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("4.1", ("инспекционные документы", "результаты инспекционной деятельности", "строительный контроль")),
    ("4.2.1", ("замечания", "создание замечания", "устранение замечания")),
    ("4.2.5", ("новадок", "эцп", "электронная подпись", "подписание", "предписание")),
    ("4.3", ("аналитика", "дашборд", "отчет", "отчёт")),
    ("9.6", ("сквозное кодирование", "связи между модулями", "тэгирование", "тегирование")),
    ("10.8", ("производительность", "нагрузочное", "2520", "600", "120", "пользователей")),
)


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


def extract_domain_terms(text: str) -> set[str]:
    lowered = normalize_text(text)
    terms: set[str] = set()
    for label, variants in DOMAIN_TERMS:
        if any(variant in lowered for variant in variants):
            terms.add(label)
    for section, hints in FTT_SECTION_HINTS:
        if section in lowered or any(hint in lowered for hint in hints):
            terms.add(f"ftt_section:{section}")
    return terms


def build_quality_expansion(question: str) -> str:
    lowered = normalize_text(question)
    extras: list[str] = []

    if "фтт" in lowered or "требован" in lowered:
        extras.extend(["ФТТ", "функционально-технические требования", "требования", "Этап 1"])

    for section, hints in FTT_SECTION_HINTS:
        if section in lowered or any(hint in lowered for hint in hints):
            extras.append(section)
            extras.extend(hints)

    if "инспекцион" in lowered or "эцп" in lowered or "новадок" in lowered:
        extras.extend(["инспекционные документы", "ЭЦП", "электронная подпись", "НОВАДОК", "4.2.5"])
    if "пользовател" in lowered or "производитель" in lowered or "нагруз" in lowered:
        extras.extend(["2520", "600", "120", "нагрузочное тестирование", "производительность", "10.8"])
    if "сквоз" in lowered or "кодирован" in lowered or "тэг" in lowered or "тег" in lowered:
        extras.extend(["9.6", "сквозное кодирование", "связи между модулями", "тэгирование", "тегирование"])
    if "аналит" in lowered or "дашборд" in lowered:
        extras.extend(["4.3", "аналитика", "дашборды", "отчеты", "отчёты"])
    if "замечан" in lowered or "предписан" in lowered:
        extras.extend(["4.2.1", "замечания", "предписания", "строительный контроль"])
    if "пми" in lowered or "пси" in lowered or "сфт" in lowered or "снт" in lowered:
        extras.extend(["ПМИ", "ПСИ", "СФТ", "СНТ", "сценарии испытаний", "протокол испытаний"])

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

    has_ftt_path = "фтт" in path_norm or "функционально" in path_norm
    asks_ftt = "фтт" in question_norm or "требован" in question_norm
    path_boost = 0.08 if asks_ftt and has_ftt_path else 0.0

    phrase_bonus = min(0.25, 0.05 * len(set(phrase_matches)))
    number_bonus = 0.25 * number_overlap
    term_bonus = 0.30 * term_overlap
    token_bonus = 0.25 * token_overlap

    score = min(1.0, token_bonus + term_bonus + number_bonus + phrase_bonus + path_boost)

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
    }


def rerank_contexts(question: str, contexts: list[dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
    reranked: list[dict[str, Any]] = []
    for ctx in contexts:
        meta = dict(ctx.get("metadata", {}))
        vector_score = float(ctx.get("score", 0.0))
        q = lexical_score(question, str(ctx.get("document", "")), str(meta.get("relative_path", "")))
        lexical = float(q["lexical_score"])
        final_score = min(1.0, 0.65 * vector_score + 0.35 * lexical)
        if lexical >= 0.35:
            final_score = min(1.0, final_score + 0.08)
        if q.get("matched_numbers"):
            final_score = min(1.0, final_score + 0.07)
        meta["retrieval"] = "hybrid_vector_lexical"
        meta["quality"] = {
            **q,
            "vector_score": round(vector_score, 6),
            "final_score": round(final_score, 6),
        }
        reranked.append({**ctx, "metadata": meta, "score": final_score, "distance": 1.0 - final_score})

    reranked.sort(key=lambda item: float(item.get("score", 0.0)), reverse=True)
    return reranked[:top_k]


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

    base = min(0.92, max(0.0, (top_score - threshold) / max(1.0 - threshold, 1e-6)))
    if lexical < 0.15:
        base *= 0.55
    elif lexical < 0.30:
        base *= 0.75
    else:
        base = min(0.95, base + 0.10)

    if matched_terms:
        base = min(0.96, base + 0.05 * min(len(matched_terms), 3))
    if matched_numbers:
        base = min(0.97, base + 0.08 * min(len(matched_numbers), 2))
    if term_overlap >= 0.75 or number_overlap >= 0.75:
        base = min(0.98, base + 0.08)

    if answer and has_no_answer_marker(answer):
        base = min(base, 0.25)
    return round(max(0.0, min(base, 0.98)), 4)


def has_no_answer_marker(answer: str) -> bool:
    lowered = normalize_text(answer)
    return any(marker in lowered for marker in NO_ANSWER_MARKERS)
