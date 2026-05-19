from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

from .metadata import enrich_metadata
from .models import SearchResult
from .source_policy import SourcePolicy


_TOKEN_RE = re.compile(r"[A-Za-zА-Яа-я0-9_./-]+", re.UNICODE)
SECTION_QUERY_RE = re.compile(r"(?<!\d)(\d+(?:\.\d+){1,5})(?:\.|\b)")


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in _TOKEN_RE.findall(text or "") if len(token) > 1]


def extract_query_sections(query: str) -> list[str]:
    seen: set[str] = set()
    sections: list[str] = []
    for match in SECTION_QUERY_RE.finditer(query):
        section = match.group(1)
        if section not in seen:
            seen.add(section)
            sections.append(section)
    return sections


def has_exact_section_in_text(text: str, section: str) -> bool:
    escaped = re.escape(section)
    return re.search(rf"(?<!\d){escaped}(?:\.|\b)", text or "") is not None


@dataclass(slots=True)
class BM25Document:
    row_id: int
    text: str
    metadata: dict[str, Any]
    term_freq: Counter[str]
    length: int


class BM25SearchAdapter:
    def __init__(self, rows: list[dict[str, Any]], source_policy: SourcePolicy | None = None, k1: float = 1.5, b: float = 0.75):
        self.source_policy = source_policy or SourcePolicy()
        self.k1 = k1
        self.b = b
        self.documents: list[BM25Document] = []
        self.doc_freq: Counter[str] = Counter()

        for row_id, row in enumerate(rows):
            text = str(row.get("text") or row.get("document") or "")
            raw_meta = dict(row.get("metadata") or row)
            metadata = enrich_metadata(raw_meta, text)
            tokens = tokenize(text)
            term_freq = Counter(tokens)
            self.documents.append(BM25Document(row_id=row_id, text=text, metadata=metadata, term_freq=term_freq, length=len(tokens)))
            self.doc_freq.update(set(tokens))

        self.doc_count = len(self.documents)
        self.avg_doc_len = sum(doc.length for doc in self.documents) / max(self.doc_count, 1)

    def _idf(self, term: str) -> float:
        df = self.doc_freq.get(term, 0)
        if df <= 0:
            return 0.0
        return math.log(1 + (self.doc_count - df + 0.5) / (df + 0.5))

    def _score_doc(self, query_terms: list[str], doc: BM25Document) -> float:
        if not query_terms or doc.length <= 0:
            return 0.0
        score = 0.0
        for term in query_terms:
            tf = doc.term_freq.get(term, 0)
            if tf <= 0:
                continue
            denom = tf + self.k1 * (1 - self.b + self.b * doc.length / max(self.avg_doc_len, 1e-9))
            score += self._idf(term) * (tf * (self.k1 + 1)) / max(denom, 1e-9)
        return score

    def _exact_section_boost(self, query_sections: list[str], doc: BM25Document) -> tuple[float, list[str]]:
        if not query_sections:
            return 1.0, []
        doc_sections = set(str(section) for section in (doc.metadata.get("sections") or []))
        requirement_id = str(doc.metadata.get("requirement_id") or "")
        matched: list[str] = []
        for section in query_sections:
            if section in doc_sections or section == requirement_id or has_exact_section_in_text(doc.text, section):
                matched.append(section)
        if not matched:
            return 1.0, []
        if any(section == requirement_id for section in matched):
            return 2.1, matched
        if any(section in doc_sections for section in matched):
            return 1.75, matched
        return 1.45, matched

    @staticmethod
    def _is_passport_overview_query(lowered: str) -> bool:
        return "паспорт" in lowered and "ис" in lowered and any(marker in lowered for marker in ["что входит", "состав", "структур", "раздел", "включает", "из чего"])

    @staticmethod
    def _is_passport_software_table(text_lower: str) -> bool:
        return (
            "контекст: программное обеспечение информационной системы" in text_lower
            or "заголовки: наименование по | тип по" in text_lower
            or "строка" in text_lower[:350] and "postgresql" in text_lower
            or "строка" in text_lower[:350] and "kubernetes" in text_lower
            or "строка" in text_lower[:350] and "nginx" in text_lower
        )

    @staticmethod
    def _is_passport_scope_chunk(text_lower: str) -> bool:
        return (
            "настоящий паспорт ис подготовлен" in text_lower
            or "в границы описания включены" in text_lower
            or "общие сведения" in text_lower[:700]
            or "назначение и область применения" in text_lower[:900]
            or "архитектурные и эксплуатационные сведения" in text_lower
            or "сведения по базовым сервисам платформы" in text_lower
        )

    def _intent_boost(self, query: str, doc: BM25Document) -> tuple[float, list[str]]:
        lowered = query.lower()
        document_type = str(doc.metadata.get("document_type") or "")
        text_lower = doc.text.lower()
        boosts: list[tuple[str, float]] = []

        if "паспорт" in lowered and "ис" in lowered:
            boosts.append(("intent:passport", 2.0 if document_type == "Паспорт ИС" else 0.72))
            if self._is_passport_overview_query(lowered):
                if self._is_passport_scope_chunk(text_lower):
                    boosts.append(("intent:passport_overview_scope", 2.6))
                if self._is_passport_software_table(text_lower):
                    boosts.append(("penalty:passport_software_table_for_overview", 0.18))
                if "история изменений" in text_lower[:1000] or "связанные документы" in text_lower[:1200]:
                    boosts.append(("penalty:passport_front_matter_for_overview", 0.35))

        if "фтт" in lowered:
            if document_type == "ФТТ":
                boosts.append(("intent:ftt", 1.85))
            elif document_type == "ПМИ":
                boosts.append(("intent:ftt_penalty_pmi", 0.68))
            elif document_type == "ПР":
                boosts.append(("intent:ftt_penalty_pr", 0.82))

        if "интеграц" in lowered or "взаимодейств" in lowered:
            if document_type in {"ЦТА", "СоИ AD", "СоИ Справочники", "Паспорт ИС", "ФТТ"}:
                boosts.append(("intent:integrations", 1.25))
            elif document_type == "Wiki":
                boosts.append(("intent:integrations_wiki_penalty", 0.72))

        if "глоссарий" not in lowered and (
            "контекст: глоссарий" in text_lower
            or "таблица 5 контекст: глоссарий" in text_lower
            or "таблица 7 контекст: глоссарий" in text_lower
            or "используемые сокращения" in text_lower[:700]
        ):
            boosts.append(("penalty:glossary", 0.25))

        if "история изменений" in text_lower[:800] and "история" not in lowered:
            boosts.append(("penalty:change_history", 0.55))

        multiplier = 1.0
        labels: list[str] = []
        for label, boost in boosts:
            multiplier *= boost
            labels.append(label)
        return multiplier, labels

    def search(self, query: str, top_k: int, include_source_types: list[str] | None = None) -> list[SearchResult]:
        query_terms = tokenize(query)
        query_sections = extract_query_sections(query)
        if not query_terms or top_k <= 0:
            return []

        scored: list[tuple[float, BM25Document, dict[str, Any]]] = []
        for doc in self.documents:
            if not self.source_policy.is_allowed(doc.metadata, query, include_source_types):
                continue
            score = self._score_doc(query_terms, doc)
            if score <= 0:
                continue
            section_boost, matched_sections = self._exact_section_boost(query_sections, doc)
            intent_boost, intent_labels = self._intent_boost(query, doc)
            policy_weight = self.source_policy.weight(doc.metadata)
            final_score = score * policy_weight * section_boost * intent_boost
            if final_score <= 0:
                continue
            scored.append(
                (
                    final_score,
                    doc,
                    {
                        "raw_bm25_score": score,
                        "policy_weight": policy_weight,
                        "section_boost": section_boost,
                        "matched_sections": matched_sections,
                        "intent_boost": intent_boost,
                        "intent_labels": intent_labels,
                    },
                )
            )

        scored.sort(key=lambda item: item[0], reverse=True)
        results: list[SearchResult] = []
        for idx, (score, doc, diagnostics) in enumerate(scored[:top_k], start=1):
            results.append(
                SearchResult(
                    source_id=f"BM25-{idx:03d}",
                    text=doc.text,
                    score=float(score),
                    vector_score=None,
                    bm25_score=float(score),
                    metadata=doc.metadata,
                    matched_by=["bm25"],
                    diagnostics=diagnostics,
                )
            )
        return results
