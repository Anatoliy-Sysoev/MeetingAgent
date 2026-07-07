from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERSION_RE = re.compile(r"^##\s+v(?P<version>\d+\.\d+\.\d+)\s*$", re.MULTILINE)
SECTION_RE = re.compile(r"^###\s+(?P<title>.+?)\s*$", re.MULTILINE)


class ReleaseNotesError(RuntimeError):
    pass


def read_text(path: Path) -> str:
    if not path.exists():
        raise ReleaseNotesError(f"File not found: {path}")
    return path.read_text(encoding="utf-8")


def project_version() -> str:
    data = tomllib.loads(read_text(ROOT / "pyproject.toml"))
    version = data.get("project", {}).get("version")
    if not isinstance(version, str) or not version:
        raise ReleaseNotesError("pyproject.toml does not contain project.version")
    return version


def versions_in(text: str) -> list[str]:
    return [match.group("version") for match in VERSION_RE.finditer(text)]


def release_block(text: str, version: str) -> str:
    marker = f"## v{version}"
    start = text.find(marker)
    if start < 0:
        raise ReleaseNotesError(f"Missing release heading: {marker}")
    next_start = text.find("\n## v", start + len(marker))
    return text[start:] if next_start < 0 else text[start:next_start]


def require_sections(block: str, *, required: set[str], label: str) -> None:
    titles = {match.group("title").strip().lower() for match in SECTION_RE.finditer(block)}
    missing = {item.lower() for item in required} - titles
    if missing:
        raise ReleaseNotesError(f"{label} release notes missing sections: {', '.join(sorted(missing))}")


def reject_placeholders(block: str, *, label: str) -> None:
    lowered = block.lower()
    bad = ["tbd", "todo", "coming soon", "заполнить", "уточнить"]
    found = [item for item in bad if item in lowered]
    if found:
        raise ReleaseNotesError(f"{label} release notes contain placeholders: {', '.join(found)}")


def validate(version: str) -> None:
    en = read_text(ROOT / "CHANGELOG.md")
    ru = read_text(ROOT / "CHANGELOG.ru.md")
    en_versions = versions_in(en)
    ru_versions = versions_in(ru)
    if en_versions != ru_versions:
        raise ReleaseNotesError(
            "CHANGELOG.md and CHANGELOG.ru.md version lists differ: "
            f"en={en_versions}, ru={ru_versions}"
        )
    if version not in en_versions:
        raise ReleaseNotesError(f"Version v{version} is missing from changelogs")

    en_block = release_block(en, version)
    ru_block = release_block(ru, version)
    require_sections(en_block, required={"Added"}, label="English")
    require_sections(ru_block, required={"Добавлено"}, label="Russian")
    reject_placeholders(en_block, label="English")
    reject_placeholders(ru_block, label="Russian")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate bilingual MeetingAgent release notes.")
    parser.add_argument("--version", default=None, help="Version to validate. Defaults to pyproject project.version.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        version = args.version or project_version()
        validate(version)
    except ReleaseNotesError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"release notes ok: v{version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
