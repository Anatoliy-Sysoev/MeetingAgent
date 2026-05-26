from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from asu_june_bot.retrieval.metadata import infer_document_type  # noqa: E402


def load_script_module(name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


extractor = load_script_module("asu_june_bot_extract_text_v2_for_tests", "scripts/asu_june_bot_extract_text_v2.py")
chunker = load_script_module("asu_june_bot_build_chunks_v2_for_tests", "scripts/asu_june_bot_build_chunks_v2.py")


def test_excel_rows_remove_fully_empty_columns_before_capping() -> None:
    rows = [
        ["Наименование", "", "Код", "", ""] + [""] * 200,
        ["Работа", "", "R-1", "", ""] + [""] * 200,
    ]

    trimmed = extractor.trim_empty_columns(rows, hard_limit=120)

    assert trimmed == [["Наименование", "Код"], ["Работа", "R-1"]]


def test_excel_rows_are_hard_capped_when_sheet_has_far_non_empty_cells() -> None:
    row = [f"value-{idx}" for idx in range(300)]

    trimmed = extractor.trim_empty_columns([row], hard_limit=120)

    assert len(trimmed[0]) == 120


def test_table_row_text_uses_meaningful_cells_without_header_bloat() -> None:
    text = chunker.block_text(
        {
            "block_type": "table_row",
            "relative_path": "Этап 1.1/Справочники/4 СВОК РД.xlsx",
            "sheet": "ЛМНП",
            "row_index": 12,
            "headers": ["Наименование"] + [f"col_{idx}" for idx in range(2, 500)],
            "cells": {"Наименование": "Раздел РД", "col_2": "", "col_3": "Марка РД"},
            "text": "Заголовки: " + " | ".join(f"col_{idx}" for idx in range(500)),
        }
    )

    assert "Заголовки:" not in text
    assert "Наименование: Раздел РД" in text
    assert "col_3: Марка РД" in text
    assert len(text) < 500


def test_table_row_long_text_can_be_split_and_noise_is_filtered() -> None:
    parts = chunker.split_long_text("x" * 5500, max_chars=2000)

    assert [len(part) for part in parts] == [2000, 2000, 1500]
    assert chunker.is_noise_text("}")
    assert chunker.is_noise_text("end")
    assert not chunker.is_noise_text("ЗАДАНИЕ ЗАКАЗЧИКА")


def test_document_type_covers_ntk_excel_and_wip_inputs() -> None:
    assert (
        infer_document_type({"relative_path": "Этап 1.1/Справочники/4 СВОК РД.xlsx", "extension": ".xlsx"})
        == "Справочник НСИ"
    )
    assert (
        infer_document_type({"relative_path": "WIP результаты/Результаты 12 (16-20) недели.pptx", "extension": ".pptx"})
        == "Статус/Презентация"
    )
