#!/usr/bin/env python3
"""Legacy tools entrypoints must execute the canonical planning libraries."""

from __future__ import annotations

import importlib.util
import inspect
import sys
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
for directory in (ROOT / "lib", ROOT / "tools"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))


def _load_tool_module(filename: str):
    path = ROOT / "tools" / filename
    name = f"authority_{path.stem}_{time.time_ns()}"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("filename", "function_name"),
    [
        ("capability_capsules.py", "default_capability_plan_for_logical_operator"),
        ("apo_plan_compiler.py", "compile_execution_plan_for_node"),
    ],
)
def test_tools_entrypoint_reexports_canonical_library(filename: str, function_name: str):
    module = _load_tool_module(filename)
    canonical_path = (ROOT / "lib" / filename).resolve()

    assert Path(module.__solar_canonical_source__).resolve() == canonical_path
    assert Path(inspect.getsourcefile(getattr(module, function_name)) or "").resolve() == canonical_path
