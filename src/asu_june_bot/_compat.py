from __future__ import annotations

import importlib
import sys
from collections.abc import Iterable
from types import ModuleType
from typing import Any


def install_deprecated_package_aliases(
    *,
    legacy_package: str,
    target_package: str,
    submodules: Iterable[str],
    namespace: dict[str, Any],
    package_deprecated: bool = True,
) -> ModuleType:
    """Expose moved modules under their legacy import paths without duplicating code."""
    target = importlib.import_module(target_package)
    exported = tuple(getattr(target, "__all__", ()))
    for name in exported:
        namespace[name] = getattr(target, name)
    namespace["__all__"] = list(exported)
    submodule_names = tuple(submodules)
    namespace["DEPRECATED_COMPATIBILITY_SHIM"] = package_deprecated
    namespace["DEPRECATED_MODULE_ALIASES"] = submodule_names

    package_module = sys.modules[legacy_package]
    for submodule in submodule_names:
        implementation = importlib.import_module(f"{target_package}.{submodule}")
        sys.modules[f"{legacy_package}.{submodule}"] = implementation
        setattr(package_module, submodule, implementation)
    return target
