"""Compatibility shim for vendored MIA memory_functions module.

The upstream ECNU-SII/MIA Memory-Serve imports get_memory_tool_schemas from
memory_functions.py, but never calls it.  This shim satisfies the import
without requiring the upstream file to exist.
"""
from __future__ import annotations

from typing import List


def get_memory_tool_schemas() -> List[dict]:
    """Return an empty schema list (import target only; never called at runtime)."""
    return []
