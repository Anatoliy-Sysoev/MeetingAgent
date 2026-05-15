from __future__ import annotations

import re

from .models import QuerySegment, SegmentClassification, SegmentScope


def _norm(text: str) -> str:
    return " ".join((text or "").lower().replace("ё", "е").split())


def _contains_any(lowered: str, markers: set[str]) -> list[str]:
    padded = f" {lowered} "
    matched: list[str] = []
    for marker in sorted(markers, key=len, reverse=True):
        marker_l = marker.lower().replace("ё", "е")
        if marker_l.startswith("re:"):
            pattern = marker_l[3:]
            if re.search(pattern, lowered, flags=re.IGNORECASE | re.UNICODE):
                matched.append(marker)
            continue
        if marker_l.endswith(" "):
            if marker_l in padded:
                matched.append(marker.strip())
            continue
        if marker_l in lowered:
            matched.append(marker)
    return matched


PROJECT_MARKERS = {
    "цп упкс",
    "упкс",
    "асу",
    "фтт",
    "цта",
    "пми",
    "пси",
    "псси",
    "проектное решение",
    "паспорт ис",
    "паспорт информационной системы",
    "сои",
    "соглашение об интеграции",
    "mdr",
    "мдр",
    "кшд",
    "ad",
    "active directory",
    "blitz",
    "blitz idp",
    "siem",
    "новадок",
    "эцп",
    "смр",
    "мто",
    "нси",
    "справочник",
    "справочники",
    "строительный контроль",
    "исполнительная документация",
    "проектная документация",
    "интеграция",
    "интеграции",
    "требование",
    "требования",
    "архитектура",
    "модуль",
    "модули",
    "авторизация пользователей",
    "аутентификация пользователей",
    "группы ad",
    "роль пользователя",
    "роли пользователей",
    "ldap",
    "ldaps",
}

META_MARKERS = {
    "найди",
    "покажи",
    "дай ссылку",
    "какие документы",
    "все документы",
    "по документам",
    "по проекту",
    "из документации",
    "по материалам",
}

OUT_OF_PROJECT_MARKERS = {
    # consumer/general topics
    "погода",
    "курс доллара",
    "курс евро",
    "курс валют",
    "биткоин",
    "акции",
    "новости",
    "рецепт",
    "калории",
    "тренировка",
    "здоровье",
    "болит",
    "врач",
    "лекарство",
    "кино",
    "фильм",
    "музыка",
    "песня",
    "путешествие",
    "отель",
    "билет",
    "купить",
    "цена",
    "скидка",
    "президент",
    "политика",
    "выборы",
    "анекдот",
    "шутка",
    # arbitrary code / games
    "питон",
    "python",
    "javascript",
    " js ",
    "html",
    "css",
    "код для",
    "напиши код",
    "сделай код",
    "скрипт для",
    "программа для",
    "игра",
    "игры",
    "игру",
    "игровой",
    "крестики",
    "нолики",
    "крестики нолики",
    "tic tac toe",
    "в браузере",
    "браузерная игра",
    # security/offensive/prompt-injection
    "sql инъекц",
    "sql-инъекц",
    "sqli",
    "sql injection",
    "инъекцию",
    "инъекция",
    "инъекции",
    "дай инъекцию",
    "payload",
    "exploit",
    "эксплойт",
    "взлом",
    "взломать",
    "обойти защиту",
    "обход защиты",
    "jailbreak",
    "ignore previous instructions",
    "игнорируй предыдущие инструкции",
    "system prompt",
    "re:\bdrop\s+table\b",
    "re:\bunion\s+select\b",
}

PROJECT_TECH_ALLOW_PATTERNS = {
    "api интеграци",
    "интеграция api",
    "rest api",
    "swagger",
    "openapi",
    "эндпоинт",
    "endpoint",
    "модель данных",
    "база данных проекта",
    "схема бд",
    "структура бд",
    "требования иб",
    "журнал безопасности",
    "защита информации",
}

GENERATION_VERBS = {
    "напиши",
    "сгенерируй",
    "сделай",
    "создай",
    "дай",
    "подготовь",
}

CODE_OR_ABUSE_NOUNS = {
    "код",
    "скрипт",
    "программу",
    "инъекц",
    "payload",
    "exploit",
    "эксплойт",
    "jailbreak",
}


class RuleBasedScopeClassifier:
    def classify(self, segment: QuerySegment) -> SegmentClassification:
        lowered = _norm(segment.text)
        project = _contains_any(lowered, PROJECT_MARKERS)
        out = _contains_any(lowered, OUT_OF_PROJECT_MARKERS)
        meta = _contains_any(lowered, META_MARKERS)
        allow_tech = _contains_any(lowered, PROJECT_TECH_ALLOW_PATTERNS)
        labels: list[str] = []

        has_generation_verb = bool(_contains_any(lowered, GENERATION_VERBS))
        has_code_or_abuse = bool(_contains_any(lowered, CODE_OR_ABUSE_NOUNS))
        if has_generation_verb and has_code_or_abuse and not allow_tech:
            labels.append("generation_request_with_code_or_abuse")
            out = sorted(set(out + ["generation_request_with_code_or_abuse"]))

        if project:
            labels.append("has_project_signal")
        if out:
            labels.append("has_out_of_project_signal")
        if meta:
            labels.append("has_meta_signal")
        if allow_tech:
            labels.append("has_project_tech_allow_signal")

        if project and out:
            return SegmentClassification(
                segment=segment,
                scope=SegmentScope.MIXED,
                confidence=0.95,
                matched_project_markers=project,
                matched_out_of_scope_markers=out,
                matched_meta_markers=meta,
                labels=labels,
            )

        if out:
            return SegmentClassification(
                segment=segment,
                scope=SegmentScope.OUT_OF_PROJECT,
                confidence=0.94,
                matched_project_markers=project,
                matched_out_of_scope_markers=out,
                matched_meta_markers=meta,
                labels=labels,
            )

        if project:
            return SegmentClassification(
                segment=segment,
                scope=SegmentScope.IN_PROJECT,
                confidence=0.88,
                matched_project_markers=project,
                matched_out_of_scope_markers=out,
                matched_meta_markers=meta,
                labels=labels,
            )

        if meta:
            return SegmentClassification(
                segment=segment,
                scope=SegmentScope.META,
                confidence=0.58,
                matched_project_markers=project,
                matched_out_of_scope_markers=out,
                matched_meta_markers=meta,
                labels=labels,
            )

        return SegmentClassification(
            segment=segment,
            scope=SegmentScope.AMBIGUOUS,
            confidence=0.45,
            matched_project_markers=project,
            matched_out_of_scope_markers=out,
            matched_meta_markers=meta,
            labels=labels + ["no_clear_scope_signal"],
        )
