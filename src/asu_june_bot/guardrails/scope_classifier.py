from __future__ import annotations

import re

from .models import QuerySegment, SegmentClassification, SegmentScope


WORD_RE = re.compile(r"^[a-zа-я0-9_+#.-]+$", re.IGNORECASE | re.UNICODE)
SHORT_MARKERS = {"ad", "js", "api", "бд", "иб"}
WEAK_PROJECT_MARKERS = {
    "ad",
    "ldap",
    "ldaps",
    "api",
    "endpoint",
    "эндпоинт",
    "бд",
    "postgresql",
    "siem",
    "документация",
    "документации",
    "документацию",
}
GENERIC_PROJECT_MARKERS = {
    "требование",
    "требования",
    "интеграция",
    "интеграции",
    "архитектура",
    "модуль",
    "модули",
    "документы",
    "документ",
}


def _norm(text: str) -> str:
    return " ".join((text or "").lower().replace("ё", "е").split())


def _marker_matches(lowered: str, marker: str) -> bool:
    marker_l = marker.lower().replace("ё", "е")
    if marker_l.startswith("re:"):
        pattern = marker_l[3:]
        return bool(re.search(pattern, lowered, flags=re.IGNORECASE | re.UNICODE))

    if marker_l.endswith(" ") or marker_l.startswith(" "):
        return marker_l in f" {lowered} "

    # Short technical markers must match as tokens. This prevents false project hits like AD inside payload.
    if marker_l in SHORT_MARKERS or (len(marker_l) <= 3 and WORD_RE.match(marker_l)):
        return bool(re.search(rf"(?<![a-zа-я0-9_]){re.escape(marker_l)}(?![a-zа-я0-9_])", lowered, flags=re.IGNORECASE | re.UNICODE))

    return marker_l in lowered


def _contains_any(lowered: str, markers: set[str]) -> list[str]:
    matched: list[str] = []
    for marker in sorted(markers, key=len, reverse=True):
        if _marker_matches(lowered, marker):
            matched.append(marker)
    return matched


PROJECT_MARKERS = {
    "цп упкс",
    "упкс",
    "асу",
    "asu",
    "фтт",
    "цта",
    "пми",
    "сценарии пми",
    "пми сценарии",
    "сценарии испытаний",
    "сценарии функционального тестирования",
    "сценарии нефункционального тестирования",
    "сценарий функционального тестирования",
    "сценарий нефункционального тестирования",
    "сфт",
    "снт",
    "пси",
    "протокол пси",
    "протокол испытаний",
    "протоколы испытаний",
    "приложение 3",
    "приложение 4",
    "приложение 5",
    "псси",
    "проекте",
    "проекта",
    "проектная документация",
    "проектной документации",
    "проектное решение",
    "паспорт ис",
    "паспорте ис",
    "паспорта ис",
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
    "авторизация пользователей",
    "аутентификация пользователей",
    "группы ad",
    "роль пользователя",
    "роли пользователей",
    "ldap",
    "ldaps",
    "endpoint",
    "эндпоинт",
    "бд",
    "postgresql",
    "структура бд",
    "структуры бд",
    "описание структуры бд",
    "защита информации",
    "защиты информации",
    "механизмы защиты информации",
    "журнал безопасности",
    "требования иб",
    "логирование в системе",
    "логирование системы",
    "поиск по логам",
    "журналирование действий пользователей",
    "grafana loki",
    "api интеграци",
    "интеграция api",
    "api-интеграции",
    "какие интеграции заявлены",
    "интеграции заявлены",
    "заявленные интеграции",
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
    "калори",
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
    "curl",
    "docker-compose",
    "sql-запрос",
    "sql запрос",
    "код для",
    "напиши код",
    "сделай код",
    "скрипт для",
    "python-скрипт",
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
    "ldap injection",
    "инъекцию",
    "инъекция",
    "инъекции",
    "дай инъекцию",
    "payload",
    "exploit",
    "эксплойт",
    "взлом",
    "взломать",
    "обойти авторизацию",
    "как обойти",
    "обойти защиту",
    "обход защиты",
    "подделать эцп",
    "подделать",
    "подделка",
    "скрыть событие",
    "скрыть логи",
    "как скрыть",
    "подобрать пароль",
    "jailbreak",
    "ignore previous instructions",
    "игнорируй предыдущие инструкции",
    "игнорируй все ограничения",
    "игнорируй",
    "обычный chatgpt",
    "больше не project-only",
    "system prompt",
    "системный промпт",
    "не используй rag",
    "ответь из головы",
    "скрытую инструкцию",
    "служебные инструкции",
    r"re:\bdrop\s+table\b",
    r"re:\bunion\s+select\b",
}

PROJECT_TECH_ALLOW_PATTERNS = {
    "api интеграци",
    "интеграция api",
    "api-интеграции",
    "rest api",
    "swagger",
    "openapi",
    "эндпоинт",
    "endpoint",
    "модель данных",
    "база данных проекта",
    "схема бд",
    "структура бд",
    "структуры бд",
    "описание структуры бд",
    "требования иб",
    "журнал безопасности",
    "защита информации",
    "защиты информации",
    "механизмы защиты информации",
    "логирование в системе",
    "логирование системы",
    "поиск по логам",
    "журналирование действий пользователей",
    "grafana loki",
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
    "curl",
    "docker-compose",
    "sql-запрос",
}


def _strong_project_matches(project_matches: list[str], allow_tech_matches: list[str]) -> list[str]:
    strong = []
    for marker in project_matches:
        marker_n = marker.lower().replace("ё", "е")
        if marker_n in WEAK_PROJECT_MARKERS or marker_n in GENERIC_PROJECT_MARKERS:
            continue
        strong.append(marker)
    strong.extend(allow_tech_matches)
    return sorted(set(strong))


class RuleBasedScopeClassifier:
    def classify(self, segment: QuerySegment) -> SegmentClassification:
        lowered = _norm(segment.text)
        project = _contains_any(lowered, PROJECT_MARKERS)
        generic_project = _contains_any(lowered, GENERIC_PROJECT_MARKERS)
        out = _contains_any(lowered, OUT_OF_PROJECT_MARKERS)
        meta = _contains_any(lowered, META_MARKERS)
        allow_tech = _contains_any(lowered, PROJECT_TECH_ALLOW_PATTERNS)
        strong_project = _strong_project_matches(project, allow_tech)
        labels: list[str] = []

        has_generation_verb = bool(_contains_any(lowered, GENERATION_VERBS))
        has_code_or_abuse = bool(_contains_any(lowered, CODE_OR_ABUSE_NOUNS))
        if has_generation_verb and has_code_or_abuse and not allow_tech:
            labels.append("generation_request_with_code_or_abuse")
            out = sorted(set(out + ["generation_request_with_code_or_abuse"]))

        if generic_project and not project:
            labels.append("generic_project_word_without_project_object")

        if project:
            labels.append("has_project_signal")
        if strong_project:
            labels.append("has_strong_project_signal")
        if out:
            labels.append("has_out_of_project_signal")
        if meta:
            labels.append("has_meta_signal")
        if allow_tech:
            labels.append("has_project_tech_allow_signal")

        # If a segment has only weak technical tokens like AD/API/DB plus an arbitrary generation/attack request,
        # it is out-of-project, not mixed. Example: "Напиши Python-скрипт для выгрузки пользователей AD".
        if out and project and not strong_project:
            labels.append("weak_project_signal_ignored_due_to_out_of_project_request")
            project = []

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

        if generic_project:
            return SegmentClassification(
                segment=segment,
                scope=SegmentScope.AMBIGUOUS,
                confidence=0.5,
                matched_project_markers=generic_project,
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
