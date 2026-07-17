#!/usr/bin/env python3
"""Compatibility entrypoint for the canonical APO plan compiler.

Product logic lives in ``harness/lib/apo_plan_compiler.py``.  This file stays
only because older callers import from ``harness/tools``.
"""

from __future__ import annotations

import sys
from pathlib import Path


_CANONICAL_SOURCE = Path(__file__).resolve().parents[1] / "lib" / "apo_plan_compiler.py"
_LIB_DIR = _CANONICAL_SOURCE.parent
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

_source = _CANONICAL_SOURCE.read_text(encoding="utf-8")
exec(compile(_source, str(_CANONICAL_SOURCE), "exec"), globals(), globals())
__solar_canonical_source__ = str(_CANONICAL_SOURCE)
