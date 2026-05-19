from __future__ import annotations

from dataclasses import replace
from typing import Iterable

from .models import SearchResult
from .source_quality import is_weak_source


DEFAULT_PARENT_MAX_CHARS = 1800


def result_chunk_index(result: SearchResult) -> int | None:
    value = result.metadata.get("chunk_index")
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def result_path(result: SearchResult) -> str:
    return str(result.metadata.get("relative_path") or result.metadata.get("path") or "")


def parent_group_key(result: SearchResult) -> tuple[str, str]:
    metadata = result.metadata or {}
    parent_id = str(
        metadata.get("parent_chunk_id")
        or metadata.get("parent_id")
        or metadata.get("block_id")
        or metadata.get("section")
        or ""
    )
    return result_path(result), parent_id


def result_key(result: SearchResult) -> str:
    return str(result.metadata.get("chunk_id") or f"{result_path(result)}#{result.metadata.get('chunk_index')}")


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(" ", 1)[0].rstrip() + "…"


class ParentExpander:
    """Limited parent/neighbor expansion for weak but useful chunks.

    This expander does not touch the index and does not create new retrieval hits.
    It only enriches a selected SearchResult with adjacent same-document context when
    the selected result is weak and a nearby result is already present in reranked output.
    """

    def __init__(self, max_parent_chars: int = DEFAULT_PARENT_MAX_CHARS) -> None:
        self.max_parent_chars = max_parent_chars

    def expand(self, selected: list[SearchResult], candidates: Iterable[SearchResult]) -> tuple[list[SearchResult], dict]:
        candidate_list = list(candidates)
        by_key = {result_key(item): item for item in candidate_list}
        expanded: list[SearchResult] = []
        expanded_count = 0
        skipped_not_weak = 0
        skipped_no_parent = 0
        skipped_no_neighbor = 0

        for result in selected:
            if not is_weak_source(result):
                skipped_not_weak += 1
                expanded.append(result)
                continue

            neighbors = self._find_neighbors(result, candidate_list, by_key)
            if not neighbors:
                skipped_no_neighbor += 1
                expanded.append(result)
                continue

            combined_parts = [result.text]
            for neighbor in neighbors:
                if neighbor.text and neighbor.text not in combined_parts:
                    combined_parts.append(neighbor.text)
            combined_text = _truncate("\n\n".join(part for part in combined_parts if part), self.max_parent_chars)
            if combined_text == result.text:
                skipped_no_parent += 1
                expanded.append(result)
                continue

            diagnostics = dict(result.diagnostics or {})
            diagnostics["parent_expansion"] = {
                "applied": True,
                "neighbors": [result_key(neighbor) for neighbor in neighbors],
                "original_chars": len(result.text or ""),
                "expanded_chars": len(combined_text),
                "max_parent_chars": self.max_parent_chars,
            }
            expanded.append(replace(result, text=combined_text, diagnostics=diagnostics))
            expanded_count += 1

        return expanded, {
            "parent_expansion": "ParentExpander",
            "expanded_count": expanded_count,
            "skipped_not_weak": skipped_not_weak,
            "skipped_no_neighbor": skipped_no_neighbor,
            "skipped_no_parent": skipped_no_parent,
            "max_parent_chars": self.max_parent_chars,
        }

    def _find_neighbors(self, result: SearchResult, candidates: list[SearchResult], by_key: dict[str, SearchResult]) -> list[SearchResult]:
        neighbors: list[SearchResult] = []
        path = result_path(result)
        group_key = parent_group_key(result)
        own_key = result_key(result)

        # Prefer same explicit parent/section group.
        if group_key[1]:
            for candidate in candidates:
                if result_key(candidate) == own_key:
                    continue
                if parent_group_key(candidate) == group_key:
                    neighbors.append(candidate)
                if len(neighbors) >= 2:
                    return neighbors

        # Fallback to adjacent chunks from the same document if candidate list already contains them.
        index = result_chunk_index(result)
        if index is None:
            return neighbors
        for neighbor_index in (index - 1, index + 1):
            key_suffix = f"#{neighbor_index}"
            for key, candidate in by_key.items():
                if key == own_key:
                    continue
                if result_path(candidate) == path and (key.endswith(key_suffix) or candidate.metadata.get("chunk_index") == neighbor_index):
                    neighbors.append(candidate)
                    break
            if len(neighbors) >= 2:
                break
        return neighbors
