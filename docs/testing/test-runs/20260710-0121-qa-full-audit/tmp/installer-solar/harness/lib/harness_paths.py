#!/usr/bin/env python3
"""Shared harness path resolution helpers.

Separates the checked-in source tree from the runtime harness state root.
"""
from __future__ import annotations

import os
from pathlib import Path


HOME = Path.home()
SOURCE_HARNESS_DIR = Path(__file__).resolve().parents[1]
DEFAULT_RUNTIME_HARNESS_DIR = HOME / ".solar" / "harness"


def resolve_source_harness_dir() -> Path:
    """Return the checked-in harness source tree."""
    return SOURCE_HARNESS_DIR


def resolve_runtime_harness_dir() -> Path:
    """Return the runtime harness root used for queues, leases, and state.

    Resolution order:
    1. Explicit environment override.
    2. Canonical `~/.solar/harness` runtime root when it exists.
    3. Fall back to the checked-in source tree for isolated tests/fixtures.
    """
    for key in ("HARNESS_DIR", "SOLAR_HARNESS_DIR"):
        raw = str(os.environ.get(key) or "").strip()
        if raw:
            return Path(raw).expanduser().resolve()
    if DEFAULT_RUNTIME_HARNESS_DIR.exists():
        return DEFAULT_RUNTIME_HARNESS_DIR.resolve()
    return SOURCE_HARNESS_DIR
