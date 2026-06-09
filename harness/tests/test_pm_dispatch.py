#!/usr/bin/env python3
"""Tests for PM dispatch capability capsule integration."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PM_DISPATCH_PATH = ROOT / "tools" / "pm_dispatch.py"


def _load_pm_dispatch():
    spec = importlib.util.spec_from_file_location("pm_dispatch", PM_DISPATCH_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_select_operator_by_role_prefers_capsule_operator_constraints(monkeypatch):
    pm_dispatch = _load_pm_dispatch()
    monkeypatch.setattr(
        pm_dispatch,
        "load_registry",
        lambda: {
            "version": 1,
            "operators": {
                "builder-a": {
                    "enabled": True,
                    "available": True,
                    "roles": ["builder"],
                    "launch_cmd_kind": "command",
                    "task_classes": ["implementation"],
                    "profile": "generic",
                    "preferred_for": [],
                },
                "builder-b": {
                    "enabled": True,
                    "available": True,
                    "roles": ["builder"],
                    "launch_cmd_kind": "command",
                    "task_classes": ["implementation"],
                    "profile": "generic",
                    "preferred_for": [],
                },
            },
        },
    )
    monkeypatch.setattr(pm_dispatch, "is_dispatchable", lambda op: (True, ""))
    operator_id, _, reason = pm_dispatch.select_operator_by_role(
        role="builder",
        task_type="implementation",
        resolved_capsule={"operator_constraints": {"preferred": ["builder-b"], "forbidden": [], "default_operator_profile": ""}},
    )
    assert reason == ""
    assert operator_id == "builder-b"


def test_select_operator_by_role_prefers_codex_over_capsule_claude_constraints(monkeypatch):
    pm_dispatch = _load_pm_dispatch()
    monkeypatch.setattr(
        pm_dispatch,
        "load_registry",
        lambda: {
            "version": 1,
            "operators": {
                "mini-claude-sonnet-builder": {
                    "enabled": True,
                    "available": True,
                    "roles": ["builder"],
                    "launch_cmd_kind": "command",
                    "task_classes": ["implementation"],
                    "profile": "builder",
                    "preferred_for": ["builder", "implementation"],
                },
                "mini-codex-gpt53-spark-builder-1": {
                    "enabled": True,
                    "available": True,
                    "roles": ["builder"],
                    "launch_cmd_kind": "command",
                    "task_classes": ["implementation"],
                    "profile": "codex-builder",
                    "provider": "openai",
                    "model_config": "Codex CLI;gpt-5.3-codex-spark",
                    "preferred_for": ["builder", "implementation", "codex"],
                },
            },
        },
    )
    monkeypatch.setattr(pm_dispatch, "is_dispatchable", lambda op: (True, ""))

    operator_id, _, reason = pm_dispatch.select_operator_by_role(
        role="builder",
        task_type="implementation",
        resolved_capsule={
            "operator_constraints": {
                "preferred": ["mini-claude-sonnet-builder"],
                "forbidden": [],
                "default_operator_profile": "mini-claude-sonnet-builder",
            }
        },
    )

    assert reason == ""
    assert operator_id == "mini-codex-gpt53-spark-builder-1"


def test_select_operator_by_role_explicit_operator_overrides_codex_first(monkeypatch):
    pm_dispatch = _load_pm_dispatch()
    monkeypatch.setattr(
        pm_dispatch,
        "load_registry",
        lambda: {
            "version": 1,
            "operators": {
                "mini-claude-sonnet-builder": {
                    "enabled": True,
                    "available": True,
                    "roles": ["builder"],
                    "launch_cmd_kind": "command",
                    "task_classes": ["implementation"],
                    "profile": "builder",
                    "preferred_for": ["builder", "implementation"],
                },
                "mini-codex-gpt53-spark-builder-1": {
                    "enabled": True,
                    "available": True,
                    "roles": ["builder"],
                    "launch_cmd_kind": "command",
                    "task_classes": ["implementation"],
                    "profile": "codex-builder",
                    "provider": "openai",
                    "model_config": "Codex CLI;gpt-5.3-codex-spark",
                    "preferred_for": ["builder", "implementation", "codex"],
                },
            },
        },
    )
    monkeypatch.setattr(pm_dispatch, "is_dispatchable", lambda op: (True, ""))

    operator_id, _, reason = pm_dispatch.select_operator_by_role(
        role="builder",
        task_type="implementation",
        prefer_operator="mini-claude-sonnet-builder",
    )

    assert reason == ""
    assert operator_id == "mini-claude-sonnet-builder"


def test_select_operator_by_role_prefers_codex_planner(monkeypatch):
    pm_dispatch = _load_pm_dispatch()
    monkeypatch.setattr(
        pm_dispatch,
        "load_registry",
        lambda: {
            "version": 1,
            "operators": {
                "mini-claude-opus-planner": {
                    "enabled": True,
                    "available": True,
                    "roles": ["planner"],
                    "launch_cmd_kind": "command",
                    "task_classes": ["planning"],
                    "profile": "planner",
                    "preferred_for": ["planner", "planning"],
                },
                "mini-codex-gpt55-medium-planner-1": {
                    "enabled": True,
                    "available": True,
                    "roles": ["planner"],
                    "launch_cmd_kind": "command",
                    "task_classes": ["planning", "requirements"],
                    "profile": "codex-planner",
                    "provider": "openai",
                    "model_config": "Codex CLI;gpt-5.5",
                    "preferred_for": ["planner", "planning", "codex"],
                },
            },
        },
    )
    monkeypatch.setattr(pm_dispatch, "is_dispatchable", lambda op: (True, ""))

    operator_id, _, reason = pm_dispatch.select_operator_by_role(
        role="planner",
        task_type="planning",
        resolved_capsule={
            "operator_constraints": {
                "preferred": ["mini-claude-opus-planner"],
                "forbidden": [],
                "default_operator_profile": "mini-claude-opus-planner",
            }
        },
    )

    assert reason == ""
    assert operator_id == "mini-codex-gpt55-medium-planner-1"


def test_cmd_submit_reads_task_graph_capsule_metadata(monkeypatch):
    pm_dispatch = _load_pm_dispatch()
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        monkeypatch.setattr(pm_dispatch, "HARNESS_DIR", root)
        monkeypatch.setattr(pm_dispatch, "SPRINTS_DIR", root / "sprints")
        monkeypatch.setattr(pm_dispatch, "PM_INBOX_DIR", root / "run" / "pm-inbox")
        monkeypatch.setattr(pm_dispatch, "OPERATOR_INBOX_DIR", root / "run" / "operator-inbox")
        monkeypatch.setattr(pm_dispatch, "OPERATOR_STATUS_DIR", root / "run" / "operator-status")
        monkeypatch.setattr(pm_dispatch, "PERSONAS_DIR", root / "personas")
        (root / "personas").mkdir(parents=True, exist_ok=True)
        (root / "personas" / "builder.md").write_text("# Builder\n", encoding="utf-8")
        sprint_graph = {
            "nodes": [
                {
                    "id": "S2",
                    "goal": "Implement the approved scope.",
                    "logical_operator": "ImplementationWorker",
                    "acceptance": ["Patch is produced within declared write scope."],
                    "requirement_ids": ["REQ-001"],
                    "capability_native": True,
                    "capability_capsule_id": "cap.requirement-compiler-implementation",
                    "dispatch_task_type": "implementation",
                    "capsule_plan": {
                        "capability_native": True,
                        "capability_capsule_id": "cap.requirement-compiler-implementation",
                        "dispatch_task_type": "implementation",
                    },
                }
            ]
        }
        (root / "sprints").mkdir(parents=True, exist_ok=True)
        (root / "sprints" / "sprint-cap.task_graph.json").write_text(json.dumps(sprint_graph), encoding="utf-8")

        monkeypatch.setattr(
            pm_dispatch,
            "load_registry",
            lambda: {
                "version": 1,
                "operators": {
                    "mini-claude-sonnet-builder": {
                        "enabled": True,
                        "available": True,
                        "roles": ["builder"],
                        "launch_cmd_kind": "command",
                        "task_classes": ["implementation"],
                        "profile": "builder",
                        "preferred_for": ["builder", "implementation"],
                        "model": "test-model",
                        "persona": "builder",
                    }
                },
            },
        )
        monkeypatch.setattr(pm_dispatch, "is_dispatchable", lambda op: (True, ""))

        sys.path.insert(0, str(ROOT / "lib"))
        import capability_capsules as caps

        monkeypatch.setattr(
            caps,
            "resolve_capability_capsule_for_task",
            lambda task, operator_id=None, registry_path=None: {
                "capability_capsule_id": "cap.requirement-compiler-implementation",
                "operator_constraints": {
                    "preferred": ["mini-claude-sonnet-builder"],
                    "forbidden": [],
                    "default_operator_profile": "mini-claude-sonnet-builder",
                },
            },
        )

        captured: dict[str, object] = {}
        fake_operator_runtime = types.ModuleType("operator_runtime")

        def _submit(envelope):
            captured["envelope"] = dict(envelope)
            return {
                "lease_id": "lease-1",
                "inbox_path": str(root / "run" / "operator-inbox" / "mini-claude-sonnet-builder" / "pm.json"),
            }

        fake_operator_runtime.submit = _submit  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "operator_runtime", fake_operator_runtime)
        monkeypatch.setenv("SOLAR_PM_DISPATCH_ALLOW_DIRECT", "1")

        args = argparse.Namespace(
            role="builder",
            objective="Implement the approved scope.",
            operator="",
            sprint="sprint-cap",
            node="S2",
            task_type="",
            context="",
            dry_run=False,
        )
        rc = pm_dispatch.cmd_submit(args)
        assert rc == 0
        envelope = captured["envelope"]
        assert envelope["capability_native"] is True
        assert envelope["capability_capsule_id"] == "cap.requirement-compiler-implementation"
        assert envelope["logical_operator"] == "ImplementationWorker"
        assert envelope["task_type"] == "implementation"


def test_cmd_compile_request_rejects_invalid_compiled_package(monkeypatch, tmp_path):
    pm_dispatch = _load_pm_dispatch()
    monkeypatch.setenv("SOLAR_PM_DISPATCH_ALLOW_DIRECT", "1")
    monkeypatch.setattr(pm_dispatch, "SPRINTS_DIR", tmp_path / "sprints")
    monkeypatch.setattr(pm_dispatch, "HARNESS_DIR", tmp_path / "harness")

    router = types.SimpleNamespace(
        build_pm_intake=lambda *args, **kwargs: {"compiled_artifacts": {"product_brief": {"title": "bad", "problem": "bad"}}},
        validate_compiled_package=lambda payload: {"ok": False, "errors": ["raw_metadata_pollution_detected"]},
        emit_requirement_package=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("emit should not run")),
    )

    class _Loader:
        def exec_module(self, module):
            return None

    fake_spec = types.SimpleNamespace(loader=_Loader())
    monkeypatch.setattr(pm_dispatch.importlib.util, "spec_from_file_location", lambda *args, **kwargs: fake_spec)
    monkeypatch.setattr(pm_dispatch.importlib.util, "module_from_spec", lambda spec: router)

    touched: dict[str, object] = {"status": False}

    def _unexpected_status(*args, **kwargs):
        touched["status"] = True
        raise AssertionError("status should not be created when validation fails")

    monkeypatch.setattr(pm_dispatch, "ensure_compiled_sprint_status", _unexpected_status)

    args = argparse.Namespace(
        text="坏包不能继续落 status",
        input_file="",
        sprint="sprint-test",
        workspace_root=str(tmp_path / "workspace"),
        paper=[],
        log=[],
        repo_context=[],
        target_system="solar-harness",
        dispatch_planner=False,
        dry_run=False,
    )
    rc = pm_dispatch.cmd_compile_request(args)
    assert rc == 2
    assert touched["status"] is False


def test_cmd_submit_persists_failed_record_when_no_operator_available(monkeypatch, tmp_path):
    pm_dispatch = _load_pm_dispatch()
    monkeypatch.setenv("SOLAR_PM_DISPATCH_ALLOW_DIRECT", "1")
    monkeypatch.setattr(pm_dispatch, "HARNESS_DIR", tmp_path)
    monkeypatch.setattr(pm_dispatch, "SPRINTS_DIR", tmp_path / "sprints")
    monkeypatch.setattr(pm_dispatch, "PM_INBOX_DIR", tmp_path / "run" / "pm-inbox")
    monkeypatch.setattr(pm_dispatch, "OPERATOR_INBOX_DIR", tmp_path / "run" / "operator-inbox")
    monkeypatch.setattr(pm_dispatch, "OPERATOR_STATUS_DIR", tmp_path / "run" / "operator-status")
    monkeypatch.setattr(
        pm_dispatch,
        "select_operator_by_role",
        lambda **kwargs: ("", {}, "no_dispatchable_operator_for_role: planner"),
    )

    args = argparse.Namespace(
        role="planner",
        objective="Need planner handoff",
        operator="",
        sprint="sprint-no-operator",
        node="N0",
        task_type="planning",
        context="",
        dry_run=False,
    )
    rc = pm_dispatch.cmd_submit(args)
    assert rc == 1
    records = list((tmp_path / "run" / "pm-inbox").glob("pm-*.json"))
    assert len(records) == 1
    payload = json.loads(records[0].read_text(encoding="utf-8"))
    assert payload["status"] == "failed_no_dispatchable_operator"
    assert payload["failure_reason"] == "no_dispatchable_operator_for_role: planner"


def test_pending_pm_backlog_count_ignores_failed_variants(monkeypatch, tmp_path):
    pm_dispatch = _load_pm_dispatch()
    inbox = tmp_path / "run" / "pm-inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(pm_dispatch, "PM_INBOX_DIR", inbox)
    samples = {
        "pm-a.json": {"status": "submitted"},
        "pm-b.json": {"status": "failed_contract_closeout"},
        "pm-c.json": {"status": "failed_missing_pm_result"},
        "pm-d.json": {"status": "completed"},
    }
    for name, payload in samples.items():
        (inbox / name).write_text(json.dumps(payload), encoding="utf-8")
    assert pm_dispatch._pending_pm_backlog_count() == 1


def _write_builder_ready_graph(sprints: Path, sprint_id: str) -> None:
    (sprints / f"{sprint_id}.status.json").write_text(
        json.dumps({"status": "active", "phase": "planning_complete"}),
        encoding="utf-8",
    )
    (sprints / f"{sprint_id}.task_graph.json").write_text(
        json.dumps(
            {
                "sprint_id": sprint_id,
                "nodes": [
                    {
                        "id": "B1",
                        "goal": "Implement approved change.",
                        "logical_operator": "ImplementationWorker",
                        "dispatch_task_type": "implementation",
                        "acceptance": ["handoff exists"],
                        "requirement_ids": ["REQ-1"],
                        "status": "pending",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def test_builder_pool_backlog_includes_latent_planning_complete(monkeypatch, tmp_path):
    pm_dispatch = _load_pm_dispatch()
    sprints = tmp_path / "sprints"
    inbox = tmp_path / "run" / "pm-inbox"
    sprints.mkdir(parents=True)
    inbox.mkdir(parents=True)
    _write_builder_ready_graph(sprints, "sprint-latent")

    monkeypatch.setattr(pm_dispatch, "SPRINTS_DIR", sprints)
    monkeypatch.setattr(pm_dispatch, "PM_INBOX_DIR", inbox)

    assert pm_dispatch._builder_pool_backlog_breakdown() == {
        "pending_pm": 0,
        "latent_builder_ready": 1,
        "total": 1,
    }

    (inbox / "pm-existing.json").write_text(
        json.dumps({"status": "submitted", "sprint_id": "sprint-latent", "node_id": "B1"}),
        encoding="utf-8",
    )
    assert pm_dispatch._builder_pool_backlog_breakdown() == {
        "pending_pm": 1,
        "latent_builder_ready": 0,
        "total": 1,
    }


def test_drain_builder_ready_submits_and_marks_graph(monkeypatch, tmp_path):
    pm_dispatch = _load_pm_dispatch()
    sprints = tmp_path / "sprints"
    inbox = tmp_path / "run" / "pm-inbox"
    sprints.mkdir(parents=True)
    inbox.mkdir(parents=True)
    _write_builder_ready_graph(sprints, "sprint-drain")

    monkeypatch.setattr(pm_dispatch, "SPRINTS_DIR", sprints)
    monkeypatch.setattr(pm_dispatch, "PM_INBOX_DIR", inbox)
    monkeypatch.setattr(pm_dispatch, "HARNESS_DIR", tmp_path)

    def fake_cmd_submit(args):
        pm_dispatch.write_pm_task_record(
            "pm-sprint-drain-B1-test",
            {
                "task_id": "pm-sprint-drain-B1-test",
                "status": "submitted",
                "sprint_id": args.sprint,
                "node_id": args.node,
                "operator_id": "mini-codex-gpt53-spark-builder-1",
            },
        )
        return 0

    monkeypatch.setattr(pm_dispatch, "cmd_submit", fake_cmd_submit)
    rc = pm_dispatch.cmd_drain_builder_ready(
        argparse.Namespace(sprint="", max_items=0, dry_run=False, json=True)
    )

    assert rc == 0
    graph = json.loads((sprints / "sprint-drain.task_graph.json").read_text(encoding="utf-8"))
    assert graph["nodes"][0]["status"] == "dispatched"
    assert graph["nodes"][0]["dispatched_via"] == "pm_dispatch"
    assert graph["nodes"][0]["pm_task_id"] == "pm-sprint-drain-B1-test"
