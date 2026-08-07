"""Make the capabilities dir importable so `gemini_deep_research` resolves as a
top-level package regardless of CWD. Imported first by the test modules.
"""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[6]
_CAP_DIR = str(_REPO_ROOT / "harness" / "lib" / "capabilities")
if _CAP_DIR not in sys.path:
    sys.path.insert(0, _CAP_DIR)
