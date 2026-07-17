#!/usr/bin/env python3
"""Compatibility shim for the canonical skill capability plane.

The implementation lives in ``harness/lib/solar_skills.py``.  A second full
copy here drifted behind the runtime entrypoint and could still report the old
structural-only skill eval as a pass.  Keep this legacy import/CLI path, but
make the lib module the single source of truth.
"""
from __future__ import annotations

import importlib.util as _importlib_util
import sys as _sys
from pathlib import Path as _Path


_LIB_DIR = _Path(__file__).resolve().parents[1] / "lib"
_LIB_MODULE_PATH = _LIB_DIR / "solar_skills.py"
_LIB_MODULE_NAME = "_solar_lib_solar_skills"


def _load_lib_solar_skills():
    lib_dir = str(_LIB_DIR)
    while lib_dir in _sys.path:
        _sys.path.remove(lib_dir)
    _sys.path.insert(0, lib_dir)

    spec = _importlib_util.spec_from_file_location(
        _LIB_MODULE_NAME, _LIB_MODULE_PATH
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load solar_skills from {_LIB_MODULE_PATH}")
    module = _importlib_util.module_from_spec(spec)
    _sys.modules[_LIB_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


_LIB_MODULE = _load_lib_solar_skills()
_RESERVED = {
    "__name__",
    "__file__",
    "__package__",
    "__loader__",
    "__spec__",
    "__builtins__",
}
globals().update(
    {name: value for name, value in vars(_LIB_MODULE).items() if name not in _RESERVED}
)
__all__ = sorted(name for name in vars(_LIB_MODULE) if not name.startswith("_"))

if __name__ == "solar_skills":
    _sys.modules[__name__] = _LIB_MODULE

if __name__ == "__main__":
    _sys.exit(_LIB_MODULE.main())
