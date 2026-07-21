"""Compatibility shim for tools/operator_score.py.

Runtime test environments sometimes resolve ``operator_score`` from ``tools/``
before ``lib/``. Re-export the canonical implementation from ``lib`` so repo
and runtime stay behaviorally identical.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path


_LIB_PATH = Path(__file__).resolve().parents[1] / "lib" / "operator_score.py"
_SPEC = importlib.util.spec_from_file_location("solar_lib_operator_score", _LIB_PATH)
if _SPEC is None or _SPEC.loader is None:  # pragma: no cover
    raise ImportError(f"Unable to load operator_score implementation from {_LIB_PATH}")
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)

__all__ = [name for name in dir(_MODULE) if not name.startswith("_")]

globals().update({name: getattr(_MODULE, name) for name in __all__})
