from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DOCS_EN = ROOT / "docs" / "en"
DOCS_RU = ROOT / "docs" / "ru"


def _markdown_names(path: Path) -> set[str]:
    return {item.name for item in path.glob("*.md")}


def _has_language_switch(text: str) -> bool:
    head = "\n".join(text.splitlines()[:6])
    return "[English]" in head and "[Русский]" in head


def test_docs_en_ru_have_matching_markdown_files() -> None:
    assert _markdown_names(DOCS_EN) == _markdown_names(DOCS_RU)


def test_public_docs_have_language_switches() -> None:
    public_docs = [
        ROOT / "README.md",
        ROOT / "README.ru.md",
        *sorted(DOCS_EN.glob("*.md")),
        *sorted(DOCS_RU.glob("*.md")),
    ]

    missing = [
        str(path.relative_to(ROOT))
        for path in public_docs
        if not _has_language_switch(path.read_text(encoding="utf-8"))
    ]

    assert missing == []


def test_public_examples_have_matching_language_sets() -> None:
    examples_en = ROOT / "examples" / "en"
    examples_ru = ROOT / "examples" / "ru"

    assert {item.name for item in examples_en.iterdir() if item.is_file()} == {
        item.name for item in examples_ru.iterdir() if item.is_file()
    }
