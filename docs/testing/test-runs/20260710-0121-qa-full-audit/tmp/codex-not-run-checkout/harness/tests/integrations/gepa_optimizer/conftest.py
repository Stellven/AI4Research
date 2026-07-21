"""Test fixtures for integrations.gepa_optimizer.

Adds the harness root to sys.path so ``import integrations.gepa_optimizer``
resolves without a project-level install.
"""

from __future__ import annotations

import sys
from pathlib import Path

_HARNESS_ROOT = Path(__file__).resolve().parents[3]
if str(_HARNESS_ROOT) not in sys.path:
    sys.path.insert(0, str(_HARNESS_ROOT))
