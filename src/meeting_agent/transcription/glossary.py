from __future__ import annotations

from pathlib import Path


def extract_initial_prompt(glossary_path: Path) -> str:
    if not glossary_path.exists():
        return ""
    text = glossary_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    in_terms = False
    terms: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped == "## Проектные Термины":
            in_terms = True
            continue
        if in_terms and stripped.startswith("## "):
            break
        if not in_terms or not stripped.startswith("|"):
            continue
        if stripped.startswith("| ---") or stripped.startswith("| Термин"):
            continue
        cells = [cell.strip(" `") for cell in stripped.strip("|").split("|")]
        if len(cells) >= 2 and cells[0]:
            terms.append(f"{cells[0]}: {cells[1]}")

    if not terms:
        return ""
    return "Встреча по проекту АСУ. Возможные термины: " + "; ".join(terms)
