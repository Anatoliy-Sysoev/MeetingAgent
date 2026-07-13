from __future__ import annotations

import pytest

from asu_june_bot.api.dependencies import _live_settings


def test_live_settings_have_bounded_product_defaults() -> None:
    assert _live_settings({}) == {
        "model_path": "models/vosk/vosk-model-small-ru-0.22",
        "vad": "silero",
        "sample_rate": 16_000,
        "block_ms": 300,
        "mic_queue_max_blocks": 32,
        "partials_max": 1_000,
        "events_max": 500,
        "sessions_max": 50,
        "active_sessions_max": 2,
        "max_state_bytes": 4 * 1024 * 1024,
        "stop_timeout_seconds": 15.0,
        "audio_archive_max_bytes": 2_000_000_000,
        "audio_archive_min_free_bytes": 256 * 1024 * 1024,
    }


@pytest.mark.parametrize(
    "config",
    [
        {"live": []},
        {"live": {"vad": ""}},
        {"live": {"model_path": True}},
        {"live": {"events_max": "500"}},
        {"live": {"sessions_max": False}},
        {"live": {"stop_timeout_seconds": True}},
        {"live": {"audio_archive_max_bytes": "2000000000"}},
        {"live": {"audio_archive_min_free_bytes": False}},
    ],
)
def test_live_settings_reject_wrong_types(config: dict) -> None:
    with pytest.raises(ValueError, match="Invalid live"):
        _live_settings(config)


def test_live_settings_preserve_explicit_zero_for_service_validation() -> None:
    assert _live_settings({"live": {"events_max": 0}})["events_max"] == 0
