#!/usr/bin/env python3
"""Compatibility entrypoint for the authoritative research CLI.

The product implementation lives in ``harness/lib/research/cli.py``.  This
path remains executable for older scripts, but it contains no second CLI.
"""
from __future__ import annotations

import sys
from pathlib import Path


LIB_DIR = Path(__file__).resolve().parents[2] / "lib"
while str(LIB_DIR) in sys.path:
    sys.path.remove(str(LIB_DIR))
sys.path.insert(0, str(LIB_DIR))

from research.cli import build_parser, main  # noqa: E402


__all__ = ["build_parser", "main"]


if __name__ == "__main__":
    raise SystemExit(main())
