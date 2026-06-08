from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from asu_june_bot.retrieval.models import SearchResult  # noqa: E402
from asu_june_bot.search.service import SearchService  # noqa: E402


def row(chunk_id: str, text: str, *, title: str = "Требования к интеграции и системным взаимодействиям") -> dict:
    return {
        "chunk_id": chunk_id,
        "db_id": f"db-{chunk_id}",
        "document_type": "ФТТ",
        "relative_path": "ФТТ.docx",
        "title": title,
        "text": text,
    }


def result(chunk_id: str, text: str, *, document_type: str = "ФТТ", score: float = 1.0) -> SearchResult:
    return SearchResult(
        source_id=chunk_id,
        text=text,
        score=score,
        vector_score=None,
        bm25_score=score,
        metadata={
            "chunk_id": chunk_id,
            "document_type": document_type,
            "relative_path": "ФТТ.docx" if document_type == "ФТТ" else "СоИ_AD.docx",
            "title": "Требования к информационной безопасности",
        },
        matched_by=["bm25"],
    )


def test_integration_ftt_auth_query_injects_basic_auth_chunk() -> None:
    service = SearchService(config={"paths": {}})
    raw = [
        result(
            "blitz",
            "Система аутентификации должна работать, используя механизм Windows-аутентификации. Протокол OIDC и Blitz/ADFS.",
            score=20.0,
        )
    ]
    rows = [
        row("basic", "Basic-аутентификация."),
        row(
            "sso",
            "Система аутентификации должна работать, используя механизм Windows-аутентификации. Протокол OIDC и Blitz/ADFS.",
            title="Требования к информационной безопасности",
        ),
    ]

    updated, diagnostics = service._inject_integration_ftt_required_anchor_results(
        "Согласно ФТТ: Какой тип аутентификации указан в ФТТ для системного взаимодействия?",
        raw,
        rows,
    )

    assert diagnostics["applied"] is True
    assert diagnostics["intent"] == "auth_type"
    assert diagnostics["injected_chunk_id"] == "basic"
    assert updated[0].metadata["chunk_id"] == "basic"
    assert "Basic-аутентификация" in updated[0].text
    assert "integration_ftt_required_anchor_selection" in updated[0].matched_by
    assert updated[0].diagnostics["integration_ftt_required_anchor_selection"]["intent"] == "auth_type"


def test_integration_ftt_anchor_intents_cover_q040_q044() -> None:
    cases = {
        "Согласно ФТТ: Какой протокол передачи данных задан для интеграций в ФТТ?": ("protocol", "https"),
        "Согласно ФТТ: Какой формат сообщений является предпочтительным при автоматической интеграции?": ("message_format", "json"),
        "Согласно ФТТ: Какой максимальный размер передаваемого сообщения допускается?": ("message_size", "100 мб"),
        "Согласно ФТТ: Какой тип аутентификации указан в ФТТ для системного взаимодействия?": ("auth_type", "basic"),
        "Согласно ФТТ: Как должна осуществляться идентификация передаваемых объектов?": ("object_identification", "тэг в заголовке вызова"),
    }

    for query, (intent, anchor) in cases.items():
        route = SearchService._integration_ftt_required_anchor_intent(query)
        assert route is not None, query
        assert route["intent"] == intent
        assert anchor in route["anchors"]


def test_heldout_object_identification_query_injects_composite_evidence_chunk() -> None:
    service = SearchService(config={"paths": {}})
    raw = [result("format", "Формат сообщений: JSON/XML.", score=20.0)]
    rows = [
        row("format", "Формат сообщений: JSON/XML."),
        row(
            "object-id",
            "Идентификация передаваемых объектов выполняется с использованием служебного тега в заголовке вызова.",
        ),
    ]

    updated, diagnostics = service._inject_integration_ftt_required_anchor_results(
        "Согласно ФТТ: Как идентифицируются передаваемые объекты в системном взаимодействии по ФТТ?",
        raw,
        rows,
    )

    assert diagnostics["applied"] is True
    assert diagnostics["intent"] == "object_identification"
    assert diagnostics["injected_chunk_id"] == "object-id"
    assert updated[0].metadata["chunk_id"] == "object-id"
    assert "заголовке вызова" in updated[0].text


def test_table_row_cells_participate_in_ftt_anchor_selection() -> None:
    service = SearchService(config={"paths": {}})
    table_row = row("object-id-table", "")
    table_row["block_type"] = "table_row"
    table_row["cells"] = {
        "Требование": "Идентификация передаваемых объектов",
        "Значение": "тег в заголовке вызова",
    }
    table_row["headers"] = ["Требование", "Значение"]

    updated, diagnostics = service._inject_integration_ftt_required_anchor_results(
        "Согласно ФТТ: Как идентифицируются передаваемые объекты?",
        [],
        [table_row],
    )

    assert diagnostics["applied"] is True
    assert diagnostics["injected_chunk_id"] == "object-id-table"
    assert updated[0].metadata["cells"]["Значение"] == "тег в заголовке вызова"


def test_non_ftt_integration_query_does_not_inject_anchor() -> None:
    service = SearchService(config={"paths": {}})

    updated, diagnostics = service._inject_integration_ftt_required_anchor_results(
        "Согласно СоИ AD: Какой тип аутентификации используется?",
        [result("soi", "OIDC и Blitz.", document_type="СоИ AD")],
        [row("basic", "Basic-аутентификация.")],
    )

    assert diagnostics == {"applied": False, "reason": "not_integration_ftt_query"}
    assert updated[0].metadata["chunk_id"] == "soi"
