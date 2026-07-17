#!/usr/bin/env python3
"""Forwarding shim for the canonical capability inference implementation.

The former tools copy drifted from ``harness/lib/capability_inference.py``:
the tools path respected explicit planner capabilities while the product lib
path unioned unrelated inferred requirements into them.  Keep the lib module
as the only behavior authority while preserving this executable/import path
for compatibility.
"""
from __future__ import annotations

import importlib.util as _importlib_util
import sys as _sys
from pathlib import Path as _Path


_LIB_DIR = _Path(__file__).resolve().parents[1] / "lib"
_LIB_MODULE_PATH = _LIB_DIR / "capability_inference.py"
_LIB_MODULE_NAME = "_solar_lib_capability_inference"


def _load_lib_capability_inference():
    lib_dir = str(_LIB_DIR)
    while lib_dir in _sys.path:
        _sys.path.remove(lib_dir)
    _sys.path.insert(0, lib_dir)

    spec = _importlib_util.spec_from_file_location(_LIB_MODULE_NAME, _LIB_MODULE_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load capability_inference from {_LIB_MODULE_PATH}")

    module = _importlib_util.module_from_spec(spec)
    _sys.modules[_LIB_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


_LIB_MODULE = _load_lib_capability_inference()
__all__ = sorted(name for name in vars(_LIB_MODULE) if not name.startswith("_"))
globals().update({name: getattr(_LIB_MODULE, name) for name in __all__})

if __name__ == "capability_inference":
    _sys.modules[__name__] = _LIB_MODULE

if __name__ == "__main__":
    _sys.exit(_LIB_MODULE.main())
