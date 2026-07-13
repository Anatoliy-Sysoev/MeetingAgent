"""Deprecated compatibility package; use :mod:`meeting_agent.live_sessions`."""

from asu_june_bot._compat import install_deprecated_package_aliases

install_deprecated_package_aliases(
    legacy_package=__name__,
    target_package="meeting_agent.live_sessions",
    submodules=("service", "store"),
    namespace=globals(),
)
