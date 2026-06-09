#!/usr/bin/env python3
"""Tests for PyYAML-free capability planning imports."""

from __future__ import annotations

import builtins
import importlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "lib"


def test_apo_plan_compiler_imports_and_plans_without_pyyaml(monkeypatch):
    original_import = builtins.__import__

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "yaml":
            raise ModuleNotFoundError("No module named 'yaml'")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    if str(LIB) not in sys.path:
        sys.path.insert(0, str(LIB))
    for module_name in ("yaml", "simple_yaml", "capability_capsules", "apo_plan_compiler"):
        sys.modules.pop(module_name, None)

    apo = importlib.import_module("apo_plan_compiler")
    node = {
        "id": "N1",
        "goal": "Wire smoke path.",
        "logical_operator": "ImplementationWorker",
        "type": "implementation",
    }
    plan = apo.build_capsule_plan_node(
        node,
        request_type="implementation",
        registry_path=ROOT / "config" / "capability-capsules.registry.yaml",
    )

    assert plan["selected"] is True
    assert plan["capability_capsule_id"] == "cap.requirement-compiler-implementation"
    assert [stage["stage_kind"] for stage in plan["stages"]] == [
        "guard",
        "resource",
        "capability",
        "verifier",
    ]
