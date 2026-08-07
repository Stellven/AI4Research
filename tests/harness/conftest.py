"""Conftest for research tests.

The survey quality gates need the real ``research.evaluator.audit_sources``.
Older tests used a module stub to break an import cycle, but that silently
disabled source-authority checks for the survey finalizer.
"""

from __future__ import annotations

import importlib
import os
import sys
import types
from pathlib import Path
from typing import Mapping

import pytest


_HARNESS_DIR = (Path(__file__).resolve().parents[2] / 'harness')
_HARNESS_LIB = str(_HARNESS_DIR / "lib")
_HARNESS_DIR_REAL = _HARNESS_DIR.resolve()
_INSTALLED_HARNESS_LINK = Path.home() / ".solar" / "harness"
_INSTALLED_HARNESS = (Path.home() / ".solar" / "harness").resolve()

if _HARNESS_LIB not in sys.path:
    sys.path.insert(0, _HARNESS_LIB)
os.environ.setdefault("HARNESS_DIR", str(_HARNESS_DIR))
os.environ.setdefault("SOLAR_HARNESS_DIR", str(_HARNESS_DIR))

_HARNESS_CLI = _HARNESS_DIR / "lib" / "cli"
_cli_pkg = types.ModuleType("cli")
_cli_pkg.__path__ = [str(_HARNESS_CLI)]
sys.modules["cli"] = _cli_pkg


# Stale/dead tests were moved to tests/quarantine/legacy_harness.
# They are deliberately not collected as product evidence; see its manifest.json.
collect_ignore: list[str] = []


def _path_is_installed_harness(raw: object) -> bool:
    if raw in (None, ""):
        return False
    try:
        path = Path(str(raw)).expanduser()
    except Exception:
        return False
    try:
        raw_absolute = path.absolute()
        installed_link_absolute = _INSTALLED_HARNESS_LINK.absolute()
    except Exception:
        raw_absolute = None
        installed_link_absolute = None
    if (
        raw_absolute is not None
        and installed_link_absolute is not None
        and (raw_absolute == installed_link_absolute or installed_link_absolute in raw_absolute.parents)
    ):
        return True

    # If ~/.solar/harness is a symlink to the current checkout, allow tests to
    # use the checkout path while still rejecting raw ~/.solar/harness imports.
    if _INSTALLED_HARNESS == _HARNESS_DIR_REAL:
        return False

    try:
        resolved = path.resolve()
    except Exception:
        return False
    return resolved == _INSTALLED_HARNESS or _INSTALLED_HARNESS in resolved.parents


def _collect_installed_harness_leaks(
    *,
    paths: list[str] | None = None,
    modules: Mapping[str, object] | None = None,
    env: Mapping[str, str] | None = None,
) -> list[str]:
    leaks: list[str] = []
    env = env if env is not None else os.environ
    for key in ("HARNESS_DIR", "SOLAR_HARNESS_DIR"):
        value = env.get(key, "")
        if _path_is_installed_harness(value):
            leaks.append(f"env:{key}={value}")

    for item in paths if paths is not None else list(sys.path):
        if _path_is_installed_harness(item):
            leaks.append(f"sys.path:{item}")

    for name, module in (modules if modules is not None else sys.modules).items():
        file_value = getattr(module, "__file__", None)
        if _path_is_installed_harness(file_value):
            leaks.append(f"module:{name}={file_value}")
    return sorted(set(leaks))


@pytest.fixture(autouse=True)
def _fail_on_installed_harness_runtime_leak():
    if os.environ.get("SOLAR_ALLOW_INSTALLED_HARNESS_TESTS", "").strip().lower() in {"1", "true", "yes", "on"}:
        yield
        return
    leaks_before = _collect_installed_harness_leaks()
    assert not leaks_before, "test is using installed ~/.solar/harness runtime:\n" + "\n".join(leaks_before)
    yield
    leaks_after = _collect_installed_harness_leaks()
    assert not leaks_after, "test leaked installed ~/.solar/harness runtime:\n" + "\n".join(leaks_after)

try:
    importlib.import_module("research.evaluator")
except Exception:
    if "research.evaluator" not in sys.modules:
        _mod = types.ModuleType("research.evaluator")
        _mod.audit_sources = lambda *a, **k: {}
        sys.modules["research.evaluator"] = _mod
