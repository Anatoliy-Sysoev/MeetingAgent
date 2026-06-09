from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class HotwordsConfigError(ValueError):
    """Raised when asr_hotwords.yaml has invalid structure."""


class HotwordsConfig:
    """Parsed and validated hotwords configuration."""

    def __init__(
        self,
        enabled: bool,
        terms: list[str],
        max_terms: int,
        max_prompt_chars: int,
    ) -> None:
        self.enabled = enabled
        self.terms = terms
        self.max_terms = max_terms
        self.max_prompt_chars = max_prompt_chars

    # ------------------------------------------------------------------

    def hotwords_list(self) -> list[str]:
        """Return deduplicated terms bounded by max_terms (for faster-whisper hotwords=)."""
        return self.terms[: self.max_terms]

    def initial_prompt(self) -> str:
        """Build a short bounded prompt phrase for initial_prompt= fallback."""
        terms = self.hotwords_list()
        if not terms:
            return ""
        prefix = "Терминология: "
        joined = ", ".join(terms)
        phrase = prefix + joined
        if len(phrase) > self.max_prompt_chars:
            # Trim to fit, word-boundary is not critical here (abbreviations dominate)
            phrase = phrase[: self.max_prompt_chars].rstrip(", ")
        return phrase


_DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[3] / "configs" / "asr_hotwords.yaml"


def load_hotwords_config(path: Path | str | None = None) -> HotwordsConfig:
    """Load and validate asr_hotwords.yaml.

    Returns a disabled HotwordsConfig on missing file (safe default).
    Raises HotwordsConfigError on structural problems.
    """
    resolved = Path(path) if path else _DEFAULT_CONFIG_PATH
    if not resolved.exists():
        return HotwordsConfig(enabled=False, terms=[], max_terms=30, max_prompt_chars=300)

    raw_text = resolved.read_text(encoding="utf-8")
    try:
        data = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise HotwordsConfigError(f"Cannot parse {resolved.name}: {exc}") from exc

    if data is None:
        return HotwordsConfig(enabled=False, terms=[], max_terms=30, max_prompt_chars=300)
    if not isinstance(data, dict):
        raise HotwordsConfigError(f"{resolved.name}: root must be a mapping, got {type(data).__name__}")

    enabled = bool(data.get("enabled", False))
    max_terms = _parse_positive_int(data, "max_terms", default=30, path=resolved)
    max_prompt_chars = _parse_positive_int(data, "max_prompt_chars", default=300, path=resolved)
    terms = _parse_terms(data.get("terms"), resolved)

    return HotwordsConfig(
        enabled=enabled,
        terms=terms,
        max_terms=max_terms,
        max_prompt_chars=max_prompt_chars,
    )


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _parse_positive_int(data: dict[str, Any], key: str, *, default: int, path: Path) -> int:
    value = data.get(key, default)
    if not isinstance(value, int) or value <= 0:
        raise HotwordsConfigError(f"{path.name}: '{key}' must be a positive integer, got {value!r}")
    return value


def _parse_terms(raw: Any, path: Path) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise HotwordsConfigError(f"{path.name}: 'terms' must be a list, got {type(raw).__name__}")
    seen: set[str] = set()
    result: list[str] = []
    for i, item in enumerate(raw):
        if not isinstance(item, str):
            raise HotwordsConfigError(f"{path.name}: terms[{i}] must be a string, got {type(item).__name__}")
        stripped = item.strip()
        if not stripped:
            continue
        if stripped not in seen:
            seen.add(stripped)
            result.append(stripped)
    return result
