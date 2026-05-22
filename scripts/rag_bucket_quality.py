from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def norm(text: str) -> str:
    return " ".join(str(text or "").lower().replace("ё", "е").split())


@dataclass(frozen=True)
class RetrievalBucket:
    code: str
    title: str
    doc_types: tuple[str, ...]
    query_markers: tuple[str, ...]
    aliases: tuple[str, ...]
    anchors: tuple[str, ...]
    path_hints: tuple[str, ...]
    boost: float = 0.12


BUCKETS: tuple[RetrievalBucket, ...] = (
    RetrievalBucket(
        code="ftt_missing",
        title="ФТТ не находится",
        doc_types=("ftt",),
        query_markers=("фтт", "функционально-техничес", "требован", "4.1", "4.2", "4.3", "9.6", "10.8", "2520", "600", "120"),
        aliases=("ФТТ", "функционально-технические требования", "задание заказчика", "Таблица 8", "Этап 1", "СМР", "Строительный контроль"),
        anchors=("4.1", "4.2.1", "4.2.2", "4.2.3", "4.2.4", "4.2.5", "4.2.7", "4.2.8", "4.2.10", "4.3", "9.6", "10.8", "инспекционные документы", "ЭЦП", "экспорт", "аналитика", "производительность", "RTO", "RPO"),
        path_hints=("фтт", "функционально-технические", "задание заказчика"),
        boost=0.18,
    ),
    RetrievalBucket(
        code="cta_missing",
        title="ЦТА не находится",
        doc_types=("cta",),
        query_markers=("цта", "архитектур", "postgresql", "minio", "kubernetes", "loki", "grafana", "rto", "rpo", "siem", "контур", "сервер"),
        aliases=("ЦТА", "целевая техническая архитектура", "архитектура", "технические требования", "системный ландшафт", "безопасность", "резервное копирование", "мониторинг"),
        anchors=("PostgreSQL", "MinIO", "S3", "Redis", "RabbitMQ", "Grafana Loki", "Grafana", "Kubernetes", "GitLab CI/CD", "Patroni", "Consul", "RTO", "RPO", "SIEM", "контур разработки", "контур тестирования", "препродуктивный контур", "продуктивный контур"),
        path_hints=("цта", "целевая техническая архитектура", "архитектура"),
        boost=0.18,
    ),
    RetrievalBucket(
        code="pr_missing",
        title="ПР не находится",
        doc_types=("pr",),
        query_markers=("проектное решение", "пр ", "бизнес-процесс", "статус", "сценарии функционирования", "роль", "права", "дашборд", "предписание", "акт проверки"),
        aliases=("ПР", "проектное решение", "модуль СМР", "строительный контроль", "сценарии функционирования", "статусная схема", "роли и полномочия"),
        anchors=("Таблица 8", "Таблица 9", "Таблица 10", "бизнес-процесс", "статусная схема", "карточка замечания", "журнал замечаний", "акт проверки", "акт об устранении", "предписание", "ЭЦП", "Disk API", "Building API", "Core API", "Auth OIDC", "Auth JWT"),
        path_hints=("проектное решение", "пр_смр", "строительный_контроль", "модуль строительный контроль"),
        boost=0.16,
    ),
    RetrievalBucket(
        code="soi_ad_missing",
        title="СоИ AD/LDAPS не находится",
        doc_types=("soi_ad",),
        query_markers=("active directory", "ldaps", "ldap", "групп", "ad", "учетн", "авторизац", "636", "app_ccpm", "dn", "upn"),
        aliases=("СОИ AD", "Active Directory", "LDAP", "LDAPS", "порт 636", "группы AD", "app_ccpm", "учетные записи", "синхронизация AD", "авторизация"),
        anchors=("cloud.novatek.ru", "OU=CCPM", "app_ccpm_*", "DN", "UPN", "member", "memberOf", "UserPrincipalName", "email", "cn", "группы Active Directory", "соответствие групп AD и ролей", "порт 636", "сервисные учетные записи"),
        path_hints=("сои_ad", "active directory", "ad.docx", "ldaps"),
        boost=0.20,
    ),
    RetrievalBucket(
        code="soi_nsi_mdr_bearer",
        title="MDR/НСИ/Bearer Token ломается",
        doc_types=("soi_nsi",),
        query_markers=("mdr", "нси", "кшд", "справоч", "bearer", "rest api", "external_id", "deletion_mark", "is_actual", "контрагент", "организац"),
        aliases=("СОИ Справочники", "MDR", "КШД", "НСИ", "Bearer Token", "REST API", "полный срез", "дельта-изменения", "OpenAPI", "справочники"),
        anchors=("Bearer Token", "срок жизни 100 лет", "один токен на компанию", "REST API", "JSON", "external_id", "code", "name", "deletion_mark", "is_actual", "is_predefined", "parent_external_id", "counterparty_external_id", "organization_external_id", "investment_project_external_id"),
        path_hints=("сои_справочники", "справочники", "mdr", "кшд"),
        boost=0.20,
    ),
    RetrievalBucket(
        code="guard_wrong_refuse_allow",
        title="guard ошибочно refuse/allow",
        doc_types=("ftt", "cta", "soi_ad", "soi_nsi", "pr"),
        query_markers=("guard", "refuse", "allow", "отказ", "доступ", "jwt", "oauth", "oidc", "bearer", "ldaps", "безопасн", "секрет", "токен"),
        aliases=("проектный security-вопрос", "авторизация", "аутентификация", "безопасность", "JWT", "OAuth", "OIDC", "Bearer Token", "LDAPS"),
        anchors=("Blitz IDP", "OAuth", "OIDC", "JWT", "Bearer Token", "LDAPS", "группы AD", "авторизация", "аутентификация", "ИБ", "безопасность", "логирование"),
        path_hints=("цта", "сои", "active directory", "справочники", "проектное решение", "фтт"),
        boost=0.10,
    ),
    RetrievalBucket(
        code="weak_source_hallucination",
        title="hallucination при слабых источниках",
        doc_types=("ftt", "pr", "cta", "soi_ad", "soi_nsi", "pmi", "psi"),
        query_markers=("галлюцинац", "hallucination", "слаб", "не подтверж", "источник"),
        aliases=("grounded answer", "source quality", "подтверждение источниками", "слабые источники", "недостаточно данных"),
        anchors=("lexical_score", "matched_terms", "matched_numbers", "phrase_matches", "doc_type_match", "source quality", "no_answer"),
        path_hints=("docs", "quality", "фтт", "проектное решение", "цта", "сои"),
        boost=0.08,
    ),
)


BUCKET_BY_CODE = {bucket.code: bucket for bucket in BUCKETS}


def detect_buckets(text: str) -> list[RetrievalBucket]:
    lowered = norm(text)
    detected: list[RetrievalBucket] = []
    for bucket in BUCKETS:
        if any(marker in lowered for marker in bucket.query_markers):
            detected.append(bucket)
    return detected


def bucket_doc_types(text: str) -> set[str]:
    out: set[str] = set()
    for bucket in detect_buckets(text):
        out.update(bucket.doc_types)
    return out


def bucket_expansion(text: str) -> list[str]:
    extras: list[str] = []
    seen: set[str] = set()
    for bucket in detect_buckets(text):
        for value in (*bucket.aliases, *bucket.anchors):
            key = norm(value)
            if key and key not in seen:
                seen.add(key)
                extras.append(value)
    return extras


def path_matches_bucket(relative_path: str, bucket: RetrievalBucket) -> bool:
    path = norm(relative_path)
    return any(hint in path for hint in bucket.path_hints)


def bucket_source_signal(question: str, document: str, relative_path: str = "") -> dict[str, Any]:
    text = norm(document + " " + relative_path)
    signals: list[dict[str, Any]] = []
    total_boost = 0.0
    for bucket in detect_buckets(question):
        alias_hits = [value for value in bucket.aliases if norm(value) in text]
        anchor_hits = [value for value in bucket.anchors if norm(value) in text]
        path_hit = path_matches_bucket(relative_path, bucket)
        if alias_hits or anchor_hits or path_hit:
            boost = bucket.boost
            if anchor_hits:
                boost += min(0.08, 0.02 * len(anchor_hits))
            if path_hit:
                boost += 0.08
            total_boost += boost
            signals.append(
                {
                    "bucket": bucket.code,
                    "title": bucket.title,
                    "doc_types": list(bucket.doc_types),
                    "alias_hits": alias_hits[:10],
                    "anchor_hits": anchor_hits[:12],
                    "path_hit": path_hit,
                    "boost": round(boost, 6),
                }
            )
    return {"bucket_boost": round(min(total_boost, 0.35), 6), "bucket_signals": signals}


def classify_failure_bucket(row: dict[str, Any]) -> str:
    query = str(row.get("query") or row.get("question") or "")
    verdict = str(row.get("review_verdict") or "")
    status = str(row.get("status") or "")
    joined = f"{query} {verdict} {status} {row.get('review_comment') or ''}"
    if verdict == "hallucination":
        return "weak_source_hallucination"
    if verdict == "bad_refusal" or "refuse" in norm(joined):
        return "guard_wrong_refuse_allow"
    buckets = detect_buckets(joined)
    return buckets[0].code if buckets else "other_retrieval_quality"
