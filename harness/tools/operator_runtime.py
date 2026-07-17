#!/usr/bin/env python3
"""Forwarding shim for B2 wave-1 operator_runtime retirement.

The old tools copy was the P2 smoke-4 shadow class: it could drift behind
harness/lib/operator_runtime.py while tools entrypoints ran with harness/tools
at sys.path[0]. The lib module is now the single source of truth.
"""
from __future__ import annotations

import importlib.util as _importlib_util
import sys as _sys
from pathlib import Path as _Path


_LIB_DIR = _Path(__file__).resolve().parents[1] / "lib"
_LIB_MODULE_PATH = _LIB_DIR / "operator_runtime.py"
_LIB_MODULE_NAME = "_solar_b2_lib_operator_runtime"


def _load_lib_operator_runtime():
    lib_dir = str(_LIB_DIR)
    while lib_dir in _sys.path:
        _sys.path.remove(lib_dir)
    _sys.path.insert(0, lib_dir)

    spec = _importlib_util.spec_from_file_location(
        _LIB_MODULE_NAME, _LIB_MODULE_PATH
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load operator_runtime from {_LIB_MODULE_PATH}")

    module = _importlib_util.module_from_spec(spec)
    _sys.modules[_LIB_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


_LIB_MODULE = _load_lib_operator_runtime()
__all__ = sorted(name for name in vars(_LIB_MODULE) if not name.startswith("_"))
globals().update({name: getattr(_LIB_MODULE, name) for name in __all__})

if __name__ == "operator_runtime":
    _sys.modules[__name__] = _LIB_MODULE

if __name__ == "__main__":
    # The pre-shim tools copy was directly runnable (`python3
    # tools/operator_runtime.py ...`); keep that entry for out-of-tree
    # callers by forwarding to the lib CLI.
    _sys.exit(_LIB_MODULE.main())
