from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from asu_june_bot.qh import build_release_gate  # noqa: E402


def test_release_gate_is_pending_without_local_validation() -> None:
    result = build_release_gate()
    payload = result.to_dict()

    assert payload["status"] == "pending_local_validation"
    assert "QH-5A" in payload["pending"]
    assert "QH-5B" in payload["pending"]


def test_release_gate_passes_after_local_validation_and_baseline_compare() -> None:
    result = build_release_gate(local_validation_done=True, baseline_compared=True)
    payload = result.to_dict()

    assert payload["status"] == "passed"
    assert payload["pending"] == []
    assert payload["failed"] == []
