"""Deprecated compatibility package; use :mod:`meeting_agent.meetings`."""

from asu_june_bot._compat import install_deprecated_package_aliases

install_deprecated_package_aliases(
    legacy_package=__name__,
    target_package="meeting_agent.meetings",
    submodules=(
        "artifact_catalog",
        "ingest_lock",
        "manifest",
        "qa",
        "service",
        "vector_cache",
        "vector_index",
    ),
    namespace=globals(),
)
