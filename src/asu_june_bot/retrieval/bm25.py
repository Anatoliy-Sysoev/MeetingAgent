from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

from .metadata import enrich_metadata
from .models import SearchResult
from .ranking_policies import (
    DEFAULT_POLICIES,
    RankingContext,
    RankingPolicy,
    RankingStage,
    adjustment_multiplier,
    adjustment_trace,
    evaluate_policies,
)
from .ranking_profile import RankingProfile, default_ranking_profile
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
    def __init__(
        self,
        rows: list[dict[str, Any]],
        source_policy: SourcePolicy | None = None,
        k1: float = 1.5,
        b: float = 0.75,
        ranking_profile: RankingProfile | None = None,
        ranking_policies: tuple[RankingPolicy, ...] = DEFAULT_POLICIES,
    ) -> None:
        self.source_policy = source_policy or SourcePolicy()
        self.k1 = k1
        self.b = b
        self.ranking_profile = ranking_profile or default_ranking_profile()
        self.ranking_policies = ranking_policies
        self.documents: list[BM25Document] = []
        self.doc_freq: Counter[str] = Counter()

        for row_id, row in enumerate(rows):
            text = str(row.get("text") or row.get("document") or "")
            raw_meta = dict(row.get("metadata") or row)
            metadata = enrich_metadata(raw_meta, text)
            tokens = tokenize(text)
            term_freq = Counter(tokens)
            self.documents.append(
                BM25Document(
                    row_id=row_id,
                    text=text,
                    metadata=metadata,
                    term_freq=term_freq,
                    length=len(tokens),
                )
            )
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

    def _exact_section_boost(
        self,
        query_sections: list[str],
        doc: BM25Document,
    ) -> tuple[float, list[str]]:
        if not query_sections:
            return 1.0, []
        doc_sections = {str(section) for section in (doc.metadata.get("sections") or [])}
        requirement_id = str(doc.metadata.get("requirement_id") or "")
        matched = [
            section
            for section in query_sections
            if section in doc_sections
            or section == requirement_id
            or has_exact_section_in_text(doc.text, section)
        ]
        if not matched:
            return 1.0, []
        if any(section == requirement_id for section in matched):
            return 2.1, matched
        if any(section in doc_sections for section in matched):
            return 1.75, matched
        return 1.45, matched

    def _intent_evaluation(
        self,
        query: str,
        doc: BM25Document,
    ) -> tuple[float, list[str], list[dict[str, Any]]]:
        context = RankingContext(
            stage=RankingStage.BM25,
            query=query,
            original_query=query.split("\n", 1)[0],
            text=doc.text,
            metadata=doc.metadata,
            document_type=str(doc.metadata.get("document_type") or ""),
            matched_by=("bm25",),
            profile=self.ranking_profile,
        )
        adjustments = evaluate_policies(context, self.ranking_policies)
        return (
            adjustment_multiplier(adjustments),
            [item.label for item in adjustments],
            adjustment_trace(RankingStage.BM25, 1.0, adjustments),
        )

    def _intent_boost(self, query: str, doc: BM25Document) -> tuple[float, list[str]]:
        multiplier, labels, _ = self._intent_evaluation(query, doc)
        return multiplier, labels

    def search(
        self,
        query: str,
        top_k: int,
        include_source_types: list[str] | None = None,
    ) -> list[SearchResult]:
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
            intent_boost, intent_labels, intent_trace = self._intent_evaluation(query, doc)
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
                        "intent_trace": intent_trace,
                        "ranking_profile_version": self.ranking_profile.version,
                    },
                )
            )

        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            SearchResult(
                source_id=f"BM25-{index:03d}",
                text=doc.text,
                score=float(score),
                vector_score=None,
                bm25_score=float(score),
                metadata=doc.metadata,
                matched_by=["bm25"],
                diagnostics=diagnostics,
            )
            for index, (score, doc, diagnostics) in enumerate(scored[:top_k], start=1)
        ]
