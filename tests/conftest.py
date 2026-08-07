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

for path in (REPO_ROOT, HARNESS_ROOT, HARNESS_LIB, HARNESS_TOOLS):
    value = str(path)
    if value not in sys.path:
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
