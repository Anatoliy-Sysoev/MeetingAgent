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
        matched = [section for section in query_sections if section in doc_sections]
        if not matched:
            return 1.0, []
        return 1.45, matched

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
            policy_weight = self.source_policy.weight(doc.metadata)
            final_score = score * policy_weight * section_boost
            scored.append(
                (
                    final_score,
                    doc,
                    {
                        "raw_bm25_score": score,
                        "policy_weight": policy_weight,
                        "section_boost": section_boost,
                        "matched_sections": matched_sections,
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
