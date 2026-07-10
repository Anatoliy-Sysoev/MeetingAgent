from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PUBLIC_QUALITY_ALLOWLIST = {
    "docs/quality/MEETING_SUMMARY_BENCHMARK.md",
    "docs/quality/README.md",
    "docs/quality/rag_eval_report_template.md",
    "docs/quality/synthetic_seed_queries.jsonl",
}


def _tracked_existing_paths() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return [
        ROOT / raw.decode("utf-8")
        for raw in result.stdout.split(b"\0")
        if raw and (ROOT / raw.decode("utf-8")).is_file()
    ]


def test_public_quality_directory_contains_only_curated_files() -> None:
    tracked = {
        path.relative_to(ROOT).as_posix()
        for path in _tracked_existing_paths()
        if path.relative_to(ROOT).as_posix().startswith("docs/quality/")
    }

    assert tracked == PUBLIC_QUALITY_ALLOWLIST


def test_tracked_tree_has_no_known_customer_or_real_person_markers() -> None:
    forbidden = (
        "НОВА" + "ТЭК",
        "Ново" + "тэк",
        "Нова" + "тэк",
        "ИТ" + "ЭК",
        "ЦП " + "УПКС",
        "Денис " + "Белецкий",
        "Торбик " + "Виталий",
        "Анатолий " + "Сысоев",
        "Антон " + "Васильев",
    )
    leaks: list[str] = []

    for path in _tracked_existing_paths():
        text = path.read_text(encoding="utf-8", errors="ignore")
        if any(marker in text for marker in forbidden):
            leaks.append(path.relative_to(ROOT).as_posix())

    assert leaks == []


def test_public_docs_have_no_literal_windows_user_profile_paths() -> None:
    roots = [ROOT / "docs", ROOT / "examples"]
    leaks: list[str] = []

    for base in roots:
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if ":\\Users\\" in text or ":/Users/" in text:
                leaks.append(path.relative_to(ROOT).as_posix())

    assert leaks == []
