"""Integrated bot API plus deprecated aliases for moved MeetingAgent modules."""

from asu_june_bot._compat import install_deprecated_package_aliases

install_deprecated_package_aliases(
    legacy_package=__name__,
    target_package="meeting_agent.api",
    submodules=(
        "auth",
        "bootstrap_policy",
        "errors",
        "host_policy",
        "meeting_dtos",
        "middleware",
        "routes_admin",
        "routes_admin_ui",
        "routes_auth",
        "routes_ingest",
        "routes_jobs",
        "routes_live",
        "routes_meetingagent_ui",
        "routes_meetings",
        "routes_workspace",
        "ui_assets",
    ),
    namespace=globals(),
    package_deprecated=False,
)

from .app import create_app  # noqa: E402 - aliases must exist before app imports

__all__ = ["create_app"]
