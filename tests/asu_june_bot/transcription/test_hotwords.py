from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
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
    f.write_text("enabled: true\nterms:\n  - Строительный контроль\n  - ЦП УПКС\n", encoding="utf-8")
    cfg = load_hotwords_config(f)
    assert "Строительный контроль" in cfg.terms
    assert "ЦП УПКС" in cfg.terms


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
# build_faster_whisper_config in script (real function, glossary patched)
# ------------------------------------------------------------------

import importlib.util  # noqa: E402
import types  # noqa: E402


def _load_script_module():
    spec = importlib.util.spec_from_file_location(
        "_t22_transcribe", ROOT / "scripts" / "22_transcribe_meeting.py"
    )
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _args(**overrides) -> types.SimpleNamespace:
    base = dict(
        hotwords=False,
        hotwords_config=None,
        model="tiny",
        language="ru",
        compute_type="int8",
        device="cpu",
        beam_size=5,
        vad_filter=True,
    )
    base.update(overrides)
    return types.SimpleNamespace(**base)


def test_build_config_no_flag_disabled_config(tmp_path, monkeypatch) -> None:
    """No --hotwords + enabled:false config → hotwords=None (glossary prompt may apply)."""
    mod = _load_script_module()
    monkeypatch.setattr(mod, "extract_initial_prompt", lambda: "")
    hw = tmp_path / "hw.yaml"
    hw.write_text("enabled: false\nterms:\n  - ПСИ\n", encoding="utf-8")
    cfg = mod.build_faster_whisper_config(_args(hotwords_config=str(hw)))
    assert cfg.hotwords is None
    assert cfg.initial_prompt == ""


def test_build_config_flag_activates(tmp_path, monkeypatch) -> None:
    """--hotwords + terms → hotwords=[...], initial_prompt cleared."""
    mod = _load_script_module()
    monkeypatch.setattr(mod, "extract_initial_prompt", lambda: "glossary")
    hw = tmp_path / "hw.yaml"
    hw.write_text("enabled: false\nterms:\n  - ПСИ\n  - ФТТ\n", encoding="utf-8")
    cfg = mod.build_faster_whisper_config(_args(hotwords=True, hotwords_config=str(hw)))
    assert cfg.hotwords == ["ПСИ", "ФТТ"]
    assert cfg.initial_prompt is None


def test_build_config_enabled_true_activates_without_flag(tmp_path, monkeypatch) -> None:
    """enabled:true in config → hotwords=[...] even without --hotwords flag."""
    mod = _load_script_module()
    monkeypatch.setattr(mod, "extract_initial_prompt", lambda: "glossary")
    hw = tmp_path / "hw.yaml"
    hw.write_text("enabled: true\nterms:\n  - ЦТА\n", encoding="utf-8")
    cfg = mod.build_faster_whisper_config(_args(hotwords=False, hotwords_config=str(hw)))
    assert cfg.hotwords == ["ЦТА"]
    assert cfg.initial_prompt is None


def test_build_config_invalid_raises(tmp_path) -> None:
    """Invalid hotwords config → TranscribeMeetingError."""
    mod = _load_script_module()
    hw = tmp_path / "hw.yaml"
    hw.write_text("enabled: true\nterms: 'not a list'\n", encoding="utf-8")
    with pytest.raises(mod.TranscribeMeetingError):
        mod.build_faster_whisper_config(_args(hotwords=True, hotwords_config=str(hw)))


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
