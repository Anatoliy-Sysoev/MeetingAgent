from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from meeting_agent.auth.models import ExternalIdentity

# Reserved provider ids for future tasks. Registering one of these later
# must not require changes to the role model or RBAC code.
RESERVED_PROVIDER_IDS: frozenset[str] = frozenset({
    "yandex", "google", "oidc", "trusted_proxy",
})

PROVIDER_TYPES: frozenset[str] = frozenset({"local", "machine", "external"})


class UnknownProviderError(KeyError):
    pass


class ProviderAlreadyRegistered(ValueError):
    pass


class AuthProvider(ABC):
    """Minimal provider contract.

    Providers authenticate and normalize identities only; they never
    assign roles or permissions — RBAC stays local.
    """

    provider_id: str
    provider_type: str

    @abstractmethod
    def normalize_identity(self, provider_data: dict[str, Any]) -> ExternalIdentity:
        ...


class LocalPasswordProvider(AuthProvider):
    provider_id = "local"
    provider_type = "local"

    def normalize_identity(self, provider_data: dict[str, Any]) -> ExternalIdentity:
        return ExternalIdentity(
            identity_id=provider_data["identity_id"],
            user_id=provider_data["user_id"],
            provider=self.provider_id,
            subject=provider_data["subject"],
            email=provider_data.get("email"),
            email_verified=bool(provider_data.get("email_verified", False)),
            display_name=provider_data.get("display_name"),
        )


class MachineTokenProvider(AuthProvider):
    provider_id = "machine"
    provider_type = "machine"

    def normalize_identity(self, provider_data: dict[str, Any]) -> ExternalIdentity:
        return ExternalIdentity(
            identity_id=provider_data["identity_id"],
            user_id=provider_data["user_id"],
            provider=self.provider_id,
            subject=provider_data["subject"],
        )


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, AuthProvider] = {}

    def register(self, provider: AuthProvider) -> None:
        if provider.provider_id in self._providers:
            raise ProviderAlreadyRegistered(
                f"Provider already registered: {provider.provider_id!r}"
            )
        if provider.provider_type not in PROVIDER_TYPES:
            raise ValueError(f"Invalid provider_type: {provider.provider_type!r}")
        self._providers[provider.provider_id] = provider

    def get(self, provider_id: str) -> AuthProvider:
        try:
            return self._providers[provider_id]
        except KeyError:
            raise UnknownProviderError(f"Unknown auth provider: {provider_id!r}") from None

    def ids(self) -> frozenset[str]:
        return frozenset(self._providers)


def default_registry() -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register(LocalPasswordProvider())
    registry.register(MachineTokenProvider())
    return registry
