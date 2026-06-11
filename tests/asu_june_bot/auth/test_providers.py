from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from asu_june_bot.auth.models import ExternalIdentity  # noqa: E402
from asu_june_bot.auth.providers import (  # noqa: E402
    AuthProvider,
    ProviderAlreadyRegistered,
    UnknownProviderError,
    default_registry,
)


def test_local_provider_registered() -> None:
    registry = default_registry()
    assert registry.get("local").provider_type == "local"


def test_machine_provider_registered() -> None:
    registry = default_registry()
    assert registry.get("machine").provider_type == "machine"


def test_unknown_provider_controlled_error() -> None:
    registry = default_registry()
    with pytest.raises(UnknownProviderError):
        registry.get("yandex")


def test_duplicate_registration_rejected() -> None:
    registry = default_registry()
    from asu_june_bot.auth.providers import LocalPasswordProvider
    with pytest.raises(ProviderAlreadyRegistered):
        registry.register(LocalPasswordProvider())


def test_future_provider_registers_without_rbac_changes() -> None:
    """A new external provider plugs in via the registry only."""

    class FakeYandexProvider(AuthProvider):
        provider_id = "yandex"
        provider_type = "external"

        def normalize_identity(self, provider_data: dict[str, Any]) -> ExternalIdentity:
            return ExternalIdentity(
                identity_id=provider_data["identity_id"],
                user_id=provider_data["user_id"],
                provider=self.provider_id,
                subject=provider_data["subject"],
            )

    registry = default_registry()
    registry.register(FakeYandexProvider())
    assert "yandex" in registry.ids()

    identity = registry.get("yandex").normalize_identity(
        {"identity_id": "i-1", "user_id": "u-1", "subject": "12345"}
    )
    assert identity.provider == "yandex"
    assert identity.subject == "12345"
