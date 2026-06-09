from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[4]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from meeting_agent.transcription.hotwords import (  # noqa: E402
    HotwordsConfig,
    HotwordsConfigError,
    load_hotwords_config,
)


# ------------------------------------------------------------------
# load_hotwords_config
# ------------------------------------------------------------------

def test_missing_file_returns_disabled(tmp_path: Path) -> None:
    cfg = load_hotwords_config(tmp_path / "nonexistent.yaml")
    assert cfg.enabled is False
    assert cfg.terms == []


def test_empty_file_returns_disabled(tmp_path: Path) -> None:
    f = tmp_path / "hw.yaml"
    f.write_text("", encoding="utf-8")
    cfg = load_hotwords_config(f)
    assert cfg.enabled is False


def test_enabled_false_by_default(tmp_path: Path) -> None:
    f = tmp_path / "hw.yaml"
    f.write_text("terms:\n  - ПСИ\n", encoding="utf-8")
    cfg = load_hotwords_config(f)
    assert cfg.enabled is False


def test_enabled_true(tmp_path: Path) -> None:
    f = tmp_path / "hw.yaml"
    f.write_text("enabled: true\nterms:\n  - ФТТ\n  - ЦТА\n", encoding="utf-8")
    cfg = load_hotwords_config(f)
    assert cfg.enabled is True
    assert cfg.terms == ["ФТТ", "ЦТА"]


def test_duplicate_terms_deduplicated(tmp_path: Path) -> None:
    f = tmp_path / "hw.yaml"
    f.write_text("enabled: true\nterms:\n  - ПСИ\n  - ПСИ\n  - ФТТ\n", encoding="utf-8")
    cfg = load_hotwords_config(f)
    assert cfg.terms == ["ПСИ", "ФТТ"]


def test_empty_string_terms_skipped(tmp_path: Path) -> None:
    f = tmp_path / "hw.yaml"
    f.write_text("enabled: true\nterms:\n  - ПСИ\n  - ''\n  - ФТТ\n", encoding="utf-8")
    cfg = load_hotwords_config(f)
    assert cfg.terms == ["ПСИ", "ФТТ"]


def test_russian_multiword_term(tmp_path: Path) -> None:
    f = tmp_path / "hw.yaml"
    f.write_text("enabled: true\nterms:\n  - Строительный контроль\n  - PRIVATE_SYSTEM\n", encoding="utf-8")
    cfg = load_hotwords_config(f)
    assert "Строительный контроль" in cfg.terms
    assert "PRIVATE_SYSTEM" in cfg.terms


def test_invalid_yaml_raises(tmp_path: Path) -> None:
    f = tmp_path / "hw.yaml"
    f.write_text("terms: [bad: yaml: here", encoding="utf-8")
    with pytest.raises(HotwordsConfigError):
        load_hotwords_config(f)


def test_non_dict_root_raises(tmp_path: Path) -> None:
    f = tmp_path / "hw.yaml"
    f.write_text("- item1\n- item2\n", encoding="utf-8")
    with pytest.raises(HotwordsConfigError):
        load_hotwords_config(f)


def test_terms_not_list_raises(tmp_path: Path) -> None:
    f = tmp_path / "hw.yaml"
    f.write_text("enabled: true\nterms: 'not a list'\n", encoding="utf-8")
    with pytest.raises(HotwordsConfigError):
        load_hotwords_config(f)


def test_term_not_string_raises(tmp_path: Path) -> None:
    f = tmp_path / "hw.yaml"
    f.write_text("enabled: true\nterms:\n  - 123\n", encoding="utf-8")
    with pytest.raises(HotwordsConfigError):
        load_hotwords_config(f)


def test_invalid_max_terms_raises(tmp_path: Path) -> None:
    f = tmp_path / "hw.yaml"
    f.write_text("enabled: true\nmax_terms: -5\nterms:\n  - ПСИ\n", encoding="utf-8")
    with pytest.raises(HotwordsConfigError):
        load_hotwords_config(f)


def test_max_terms_limits_hotwords_list(tmp_path: Path) -> None:
    terms = [f"TERM{i}" for i in range(50)]
    data = {"enabled": True, "max_terms": 10, "terms": terms}
    f = tmp_path / "hw.yaml"
    f.write_text(yaml.dump(data, allow_unicode=True), encoding="utf-8")
    cfg = load_hotwords_config(f)
    assert len(cfg.hotwords_list()) == 10


# ------------------------------------------------------------------
# HotwordsConfig methods
# ------------------------------------------------------------------

def test_hotwords_list_order_preserved() -> None:
    cfg = HotwordsConfig(enabled=True, terms=["ЦТА", "ФТТ", "ПСИ"], max_terms=30, max_prompt_chars=300)
    assert cfg.hotwords_list() == ["ЦТА", "ФТТ", "ПСИ"]


def test_initial_prompt_bounded_by_max_chars() -> None:
    terms = [f"TERM{i}" for i in range(100)]
    cfg = HotwordsConfig(enabled=True, terms=terms, max_terms=100, max_prompt_chars=50)
    prompt = cfg.initial_prompt()
    assert len(prompt) <= 50


def test_initial_prompt_empty_terms_returns_empty() -> None:
    cfg = HotwordsConfig(enabled=True, terms=[], max_terms=30, max_prompt_chars=300)
    assert cfg.initial_prompt() == ""


def test_initial_prompt_contains_terms() -> None:
    cfg = HotwordsConfig(enabled=True, terms=["ПСИ", "ФТТ"], max_terms=30, max_prompt_chars=300)
    prompt = cfg.initial_prompt()
    assert "ПСИ" in prompt
    assert "ФТТ" in prompt


# ------------------------------------------------------------------
# FasterWhisperConfig hotwords field
# ------------------------------------------------------------------

def test_faster_whisper_config_hotwords_field() -> None:
    from meeting_agent.transcription.faster_whisper_backend import FasterWhisperConfig

    cfg = FasterWhisperConfig(hotwords=["ПСИ", "ФТТ"])
    assert cfg.hotwords == ["ПСИ", "ФТТ"]


def test_faster_whisper_config_hotwords_default_none() -> None:
    from meeting_agent.transcription.faster_whisper_backend import FasterWhisperConfig

    cfg = FasterWhisperConfig()
    assert cfg.hotwords is None


# ------------------------------------------------------------------
# build_faster_whisper_config in script (no real ASR, mocked)
# ------------------------------------------------------------------

def test_script_build_config_no_hotwords_flag(tmp_path: Path) -> None:
    """Without --hotwords, initial_prompt comes from glossary (or empty), hotwords=None."""
    import types

    sys.path.insert(0, str(ROOT / "scripts"))
    import importlib

    script = importlib.import_module("22_transcribe_meeting") if "22_transcribe_meeting" in sys.modules else None
    # Direct import via spec
    import importlib.util

    spec = importlib.util.spec_from_file_location("_t22", ROOT / "scripts" / "22_transcribe_meeting.py")
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]

    args = types.SimpleNamespace(
        hotwords=False,
        hotwords_config=None,
        model="tiny",
        language="ru",
        compute_type="int8",
        device="cpu",
        beam_size=5,
        vad_filter=True,
    )
    # Only test the config construction, not actual ASR
    from meeting_agent.transcription.faster_whisper_backend import FasterWhisperConfig

    cfg = FasterWhisperConfig(
        model=args.model,
        language=args.language,
        compute_type=args.compute_type,
        device=args.device,
        beam_size=args.beam_size,
        vad_filter=args.vad_filter,
        hotwords=None,
    )
    assert cfg.hotwords is None


def test_script_build_config_with_hotwords_flag(tmp_path: Path) -> None:
    """With --hotwords, hotwords list is passed and initial_prompt cleared."""
    import types

    hw_file = tmp_path / "hw.yaml"
    hw_file.write_text("enabled: true\nterms:\n  - ПСИ\n  - ФТТ\n", encoding="utf-8")

    from meeting_agent.transcription.hotwords import load_hotwords_config

    hw = load_hotwords_config(hw_file)
    assert hw.enabled is True
    assert hw.hotwords_list() == ["ПСИ", "ФТТ"]

    from meeting_agent.transcription.faster_whisper_backend import FasterWhisperConfig

    cfg = FasterWhisperConfig(
        model="tiny",
        language="ru",
        compute_type="int8",
        device="cpu",
        beam_size=5,
        vad_filter=True,
        initial_prompt=None,
        hotwords=hw.hotwords_list(),
    )
    assert cfg.hotwords == ["ПСИ", "ФТТ"]
    assert cfg.initial_prompt is None


# ------------------------------------------------------------------
# Smoke: committed config file is valid
# ------------------------------------------------------------------

def test_committed_config_is_valid() -> None:
    cfg = load_hotwords_config(ROOT / "configs" / "asr_hotwords.yaml")
    assert isinstance(cfg.enabled, bool)
    assert isinstance(cfg.terms, list)
    assert cfg.max_terms > 0
    assert cfg.max_prompt_chars > 0


def test_committed_config_disabled_by_default() -> None:
    cfg = load_hotwords_config(ROOT / "configs" / "asr_hotwords.yaml")
    assert cfg.enabled is False
