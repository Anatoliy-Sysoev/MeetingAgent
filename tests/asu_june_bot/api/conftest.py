"""Shared helpers for API tests that need auth after RBAC integration."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from asu_june_bot.auth.repository import AuthRepository  # noqa: E402
from asu_june_bot.auth.service import LocalAuthService  # noqa: E402

TOKEN = "test-secret-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


def make_auth_service(tmp_path: Path) -> LocalAuthService:
    """Create a minimal in-memory-backed LocalAuthService for tests."""
    repo = AuthRepository(tmp_path / "test_auth.db")
    repo.initialize()
    return LocalAuthService(repo)
