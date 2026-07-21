#!/usr/bin/env python3
"""Compatibility wrapper for the canonical graph node dispatcher.

The implementation lives in ``harness/lib/graph_node_dispatcher.py``.  Keeping a
second full copy here caused runtime fixes to drift between ``lib`` and
``tools``; this file remains only as a CLI entrypoint for older scripts.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType


def _harness_dir() -> Path:
    raw = os.environ.get("HARNESS_DIR")
    return Path(raw).expanduser() if raw else Path(__file__).resolve().parents[1]


def _load_impl() -> ModuleType:
    harness_dir = _harness_dir()
    lib_dir = harness_dir / "lib"
    impl_path = lib_dir / "graph_node_dispatcher.py"
    if str(lib_dir) not in sys.path:
        sys.path.insert(0, str(lib_dir))
    spec = importlib.util.spec_from_file_location("solar_graph_node_dispatcher_impl", impl_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load graph dispatcher implementation: {impl_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_IMPL = _load_impl()
main = _IMPL.main


if __name__ == "__main__":
    raise SystemExit(main())
