#!/usr/bin/env python3
"""Forwarding shim for B2 wave-2 intent_consumer retirement.

The old tools copy was a stale duplicate of harness/lib/intent_consumer.py:
it lacked the research-artifact helpers (extract/require/annotate), the
blocked_missing_research_artifact consume guard, the post-bind package
annotation, and — load-bearing for P5 — the SOLAR_PLAN_VALIDATOR planner
compile-policy block in planner_objective_for_compiled_sprint, so any caller
importing with harness/tools at sys.path[0] dispatched an untaught planner
(B2-WAVE2-SCOUT.md). The lib module is the single source of truth.
"""
from __future__ import annotations

import importlib.util as _importlib_util
import sys as _sys
from pathlib import Path as _Path


_LIB_DIR = _Path(__file__).resolve().parents[1] / "lib"
_LIB_MODULE_PATH = _LIB_DIR / "intent_consumer.py"
_LIB_MODULE_NAME = "_solar_b2_lib_intent_consumer"


def _load_lib_intent_consumer():
    lib_dir = str(_LIB_DIR)
    while lib_dir in _sys.path:
        _sys.path.remove(lib_dir)
    _sys.path.insert(0, lib_dir)

    spec = _importlib_util.spec_from_file_location(
        _LIB_MODULE_NAME, _LIB_MODULE_PATH
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load intent_consumer from {_LIB_MODULE_PATH}")

    module = _importlib_util.module_from_spec(spec)
    _sys.modules[_LIB_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


_LIB_MODULE = _load_lib_intent_consumer()
__all__ = sorted(name for name in vars(_LIB_MODULE) if not name.startswith("_"))
globals().update({name: getattr(_LIB_MODULE, name) for name in __all__})

if __name__ == "intent_consumer":
    _sys.modules[__name__] = _LIB_MODULE

if __name__ == "__main__":
    # The pre-shim tools copy was directly runnable (`python3
    # tools/intent_consumer.py consume|status ...`); keep that entry for
    # out-of-tree callers by forwarding to the lib CLI.
    _sys.exit(_LIB_MODULE.main())
