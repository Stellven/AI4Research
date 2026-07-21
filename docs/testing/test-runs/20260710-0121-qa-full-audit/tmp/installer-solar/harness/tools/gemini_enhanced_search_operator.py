#!/usr/bin/env python3
"""CLI wrapper for the Gemini enhanced search operator."""
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from gemini_enhanced_search import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
