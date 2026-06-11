from __future__ import annotations

"""Central role/permission definitions for MeetingAgent RBAC.

All authorization decisions resolve through this module. Providers
(local, machine, future yandex/google/oidc) only authenticate; they
never grant permissions directly.
"""

VIEWER_PERMISSIONS: frozenset[str] = frozenset({
    "meetings.read",
    "artifacts.read",
    "transcripts.read",
    "search.use",
    "chat.use",
})

EDITOR_PERMISSIONS: frozenset[str] = VIEWER_PERMISSIONS | frozenset({
    "meetings.upload",
    "meetings.edit",
    "jobs.start",
    "jobs.cancel",
    "jobs.retry",
    "artifacts.edit",
})

ADMIN_PERMISSIONS: frozenset[str] = EDITOR_PERMISSIONS | frozenset({
    "users.manage",
    "roles.manage",
    "settings.manage",
    "audit.read",
    "meetings.delete",
    "tokens.manage",
})

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "viewer": VIEWER_PERMISSIONS,
    "editor": EDITOR_PERMISSIONS,
    "admin": ADMIN_PERMISSIONS,
}

BUILTIN_ROLES: frozenset[str] = frozenset(ROLE_PERMISSIONS)


def permissions_for_roles(roles: frozenset[str] | set[str]) -> frozenset[str]:
    """Union of permissions for known roles. Unknown roles grant nothing."""
    result: set[str] = set()
    for role in roles:
        result |= ROLE_PERMISSIONS.get(role, frozenset())
    return frozenset(result)
