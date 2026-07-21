#!/usr/bin/env python3
"""Compatibility wrapper for the canonical graph scheduler module.

This path historically drifted from ``harness/lib/graph_scheduler.py`` and
created a dual-source hazard. Keep `tools/graph_scheduler.py` as a thin
compatibility shim so CLI callers and legacy imports always execute the single
canonical implementation from `lib/graph_scheduler.py`.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path


_MODULE_PATH = Path(__file__).resolve().parents[1] / "lib" / "graph_scheduler.py"
_SPEC = importlib.util.spec_from_file_location("solar_graph_scheduler_canonical", _MODULE_PATH)
if _SPEC is None or _SPEC.loader is None:  # pragma: no cover
    raise RuntimeError(f"unable to load canonical graph scheduler from {_MODULE_PATH}")
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)

for _name in dir(_MODULE):
    if _name.startswith("__") and _name not in {"__doc__", "__all__"}:
        continue
    globals()[_name] = getattr(_MODULE, _name)


if __name__ == "__main__":
    globals()["main"]()
