#!/usr/bin/env python3
"""Reasonix operators are advisory/review only, not code-edit builders."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PHYSICAL_OPERATORS = ROOT / "config" / "physical-operators.json"
LOGICAL_OPERATORS = ROOT / "config" / "logical-operators.json"
PM_DISPATCH = ROOT / "tools" / "pm_dispatch.py"
DEEPSEEK_V4_PRO_PRD_EVALUATOR = "mini-reasonix-deepseek-v4-pro-prd-evaluator"

CODE_LOGICAL_OPERATORS = {"ImplementationWorker", "PatchWorker", "TestDesigner"}
CODE_TASK_MARKERS = {"implementation", "code-edit", "repo-modification"}


def _load_pm_dispatch():
    spec = importlib.util.spec_from_file_location("pm_dispatch", PM_DISPATCH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _reasonix_ops() -> dict[str, dict]:
    config = json.loads(PHYSICAL_OPERATORS.read_text(encoding="utf-8"))
    return {
        op_id: op
        for op_id, op in config["operators"].items()
        if "reasonix" in op_id.lower() or "reasonix" in str(op.get("base_url", "")).lower()
    }


def test_reasonix_physical_operators_are_advisory_only():
    reasonix_ops = _reasonix_ops()
    assert reasonix_ops, "expected at least one Reasonix operator"
    for op_id, op in reasonix_ops.items():
        roles = {str(item).lower() for item in op.get("roles", [])}
        task_classes = {str(item).lower() for item in op.get("task_classes", [])}
        avoid_for = {str(item).lower() for item in op.get("avoid_for", [])}
        pool = op.get("builder_pool", {})

        assert "builder" not in roles, f"{op_id}: Reasonix must not advertise builder role"
        assert task_classes <= {"analysis", "review", "advisory"}, (
            f"{op_id}: unexpected task_classes={sorted(task_classes)}"
        )
        assert CODE_TASK_MARKERS <= avoid_for, f"{op_id}: missing code avoid markers"
        assert pool.get("enabled") is False, f"{op_id}: Reasonix builder pool must stay disabled"
        assert "file_execution" in str(pool.get("disabled_reason", "")), (
            f"{op_id}: disabled_reason should document missing file execution proof"
        )


def test_deepseek_v4_pro_prd_evaluator_registered_for_prd_and_eval_only():
    reasonix_ops = _reasonix_ops()
    op = reasonix_ops.get(DEEPSEEK_V4_PRO_PRD_EVALUATOR)
    assert op is not None, "DeepSeek V4 Pro PRD/eval advisory operator must be registered"
    assert op.get("model") == "deepseek-v4-pro"
    assert set(op.get("roles", [])) == {"planner", "evaluator"}
    assert op.get("policy", {}).get("write_files") == "denied"
    assert op.get("policy", {}).get("run_shell") == "denied"
    assert "prd-review" in {str(item).lower() for item in op.get("preferred_for", [])}
    assert "implementation" in {str(item).lower() for item in op.get("avoid_for", [])}


def test_reasonix_not_bound_to_code_logical_operators():
    config = json.loads(LOGICAL_OPERATORS.read_text(encoding="utf-8"))
    bindings = config.get("bindings", {})
    for logical_name in CODE_LOGICAL_OPERATORS:
        candidates = bindings.get(logical_name, {}).get("candidates", [])
        actor_ids = {str(candidate.get("actor_id", "")).lower() for candidate in candidates}
        assert not any("reasonix" in actor_id for actor_id in actor_ids), (
            f"{logical_name}: Reasonix must not be a code-edit candidate"
        )


def test_pm_dispatch_rejects_explicit_reasonix_code_task(monkeypatch):
    pm_dispatch = _load_pm_dispatch()
    reasonix_op = next(iter(_reasonix_ops().values()))
    monkeypatch.setattr(
        pm_dispatch,
        "load_registry",
        lambda: {
            "version": 1,
            "operators": {
                "mini-reasonix-deepseek-v4-builder": {
                    **reasonix_op,
                    "enabled": True,
                    "available": True,
                }
            },
        },
    )
    monkeypatch.setattr(pm_dispatch, "is_dispatchable", lambda op: (True, ""))

    operator_id, _, reason = pm_dispatch.select_operator_by_role(
        role="builder",
        task_type="implementation",
        prefer_operator="mini-reasonix-deepseek-v4-builder",
    )

    assert operator_id == ""
    assert "preferred_operator_rejected_for_task" in reason
    assert "code_execution" in reason


def test_pm_dispatch_allows_reasonix_review_task(monkeypatch):
    pm_dispatch = _load_pm_dispatch()
    reasonix_op = next(iter(_reasonix_ops().values()))
    monkeypatch.setattr(
        pm_dispatch,
        "load_registry",
        lambda: {
            "version": 1,
            "operators": {
                "mini-reasonix-deepseek-v4-builder": {
                    **reasonix_op,
                    "enabled": True,
                    "available": True,
                }
            },
        },
    )
    monkeypatch.setattr(pm_dispatch, "is_dispatchable", lambda op: (True, ""))

    operator_id, _, reason = pm_dispatch.select_operator_by_role(
        role="evaluator",
        task_type="review",
        prefer_operator="mini-reasonix-deepseek-v4-builder",
    )

    assert reason == ""
    assert operator_id == "mini-reasonix-deepseek-v4-builder"


def test_pm_dispatch_allows_deepseek_v4_pro_prd_review_task(monkeypatch):
    pm_dispatch = _load_pm_dispatch()
    reasonix_op = _reasonix_ops()[DEEPSEEK_V4_PRO_PRD_EVALUATOR]
    monkeypatch.setattr(
        pm_dispatch,
        "load_registry",
        lambda: {
            "version": 1,
            "operators": {
                DEEPSEEK_V4_PRO_PRD_EVALUATOR: {
                    **reasonix_op,
                    "enabled": True,
                    "available": True,
                }
            },
        },
    )
    monkeypatch.setattr(pm_dispatch, "is_dispatchable", lambda op: (True, ""))

    operator_id, _, reason = pm_dispatch.select_operator_by_role(
        role="planner",
        task_type="prd-review",
        prefer_operator=DEEPSEEK_V4_PRO_PRD_EVALUATOR,
    )

    assert reason == ""
    assert operator_id == DEEPSEEK_V4_PRO_PRD_EVALUATOR
