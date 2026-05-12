from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class SourceDocument:
    source_id: str
    source_path: str
    relative_path: str
    extension: str
    sha256: str
    mtime: float
    size_bytes: int
    source_type: str | None = None
    document_type: str | None = None
    stage: str | None = None
    module: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ExtractedBlock:
    block_id: str
    source_id: str
    block_index: int
    block_type: str
    text: str
    source_path: str
    relative_path: str
    extension: str
    sha256: str
    mtime: float
    document_name: str
    source_type: str | None = None
    document_type: str | None = None
    stage: str | None = None
    module: str | None = None
    page: int | None = None
    slide: int | None = None
    sheet: str | None = None
    paragraph_index: int | None = None
    heading_level: int | None = None
    style_name: str | None = None
    section: str | None = None
    sections: list[str] = field(default_factory=list)
    table_id: str | None = None
    table_index: int | None = None
    row_id: str | None = None
    row_index: int | None = None
    col_count: int | None = None
    headers: list[str] = field(default_factory=list)
    cells: dict[str, str] = field(default_factory=dict)
    title: str | None = None
    parent_hint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
