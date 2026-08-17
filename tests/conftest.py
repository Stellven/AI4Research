"""Repository-wide test discovery and import isolation."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


# Collection and execution must not leave bytecode caches in the source tree.
# This is process-local and does not change a developer's global Python setup.
sys.dont_write_bytecode = True


REPO_ROOT = Path(__file__).resolve().parents[1]
HARNESS_ROOT = REPO_ROOT / "harness"
HARNESS_LIB = HARNESS_ROOT / "lib"
HARNESS_TOOLS = HARNESS_ROOT / "tools"

# Import precedence, highest first. `harness/lib` MUST outrank `harness/tools`:
# 172 module names exist in both directories, and for the refactored ones
# `tools/<name>.py` is a thin CLI wrapper whose own docstring says "the
# implementation lives in harness/lib". The previous loop inserted each entry at
# position 0, which reversed this tuple and put `tools` first, so the suite
# imported wrappers instead of implementations. That single ordering silently
# produced 101 setup errors in tests/harness/scenarios (monkeypatching
# module-level constants the wrapper does not define) and made
# tests/harness/gate_ledger and tests/harness/lib uncollectable.
#
# Downstream conftests re-insert `harness/lib` under an `if not in sys.path`
# guard, which is a no-op once it is present at any position, so the order has
# to be correct here.
IMPORT_PRECEDENCE = (HARNESS_LIB, HARNESS_TOOLS, HARNESS_ROOT, REPO_ROOT)

for path in reversed(IMPORT_PRECEDENCE):
    value = str(path)
    while value in sys.path:
        sys.path.remove(value)
    sys.path.insert(0, value)

os.environ.setdefault("HARNESS_DIR", str(HARNESS_ROOT))
os.environ.setdefault("SOLAR_HARNESS_DIR", str(HARNESS_ROOT))

# Journey fixtures may intentionally contain miniature projects with files
# named test_*.py. They are user inputs for journey tests, not repository tests.
collect_ignore_glob = [
    "journeys/**/fixtures/**",
    "quarantine/**",
]


@pytest.fixture(autouse=True)
def _isolated_user_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Prevent a test's default user-state writes from reaching the real home.

    Tests that need a particular home or XDG layout may still replace these
    values explicitly. Subprocesses inherit the same per-test sandbox.
    """

    home = tmp_path / "user-home"
    appdata = home / "AppData" / "Roaming"
    local_appdata = home / "AppData" / "Local"
    xdg_config = home / ".config"
    xdg_cache = home / ".cache"
    xdg_data = home / ".local" / "share"
    for directory in (home, appdata, local_appdata, xdg_config, xdg_cache, xdg_data):
        directory.mkdir(parents=True, exist_ok=True)

    for name, value in {
        "HOME": home,
        "USERPROFILE": home,
        "APPDATA": appdata,
        "LOCALAPPDATA": local_appdata,
        "XDG_CONFIG_HOME": xdg_config,
        "XDG_CACHE_HOME": xdg_cache,
        "XDG_DATA_HOME": xdg_data,
    }.items():
        monkeypatch.setenv(name, str(value))

    yield
