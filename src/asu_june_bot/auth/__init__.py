"""Deprecated compatibility package; use :mod:`meeting_agent.auth`."""

from asu_june_bot._compat import install_deprecated_package_aliases

install_deprecated_package_aliases(
    legacy_package=__name__,
    target_package="meeting_agent.auth",
    submodules=(
        "deployment_safety",
        "models",
        "passwords",
        "permissions",
        "providers",
        "repository",
        "secret_strength",
        "service",
        "throttle",
        "trusted_proxy",
    ),
    namespace=globals(),
)
