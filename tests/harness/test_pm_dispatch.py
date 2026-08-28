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

ROOT = (Path(__file__).resolve().parents[2] / 'harness')
PM_DISPATCH_PATH = ROOT / "tools" / "pm_dispatch.py"


def _load_pm_dispatch():
    spec = importlib.util.spec_from_file_location("pm_dispatch", PM_DISPATCH_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_reconcile_keeps_live_task_active_when_partial_result_exists(tmp_path, monkeypatch, capsys):
    pm_dispatch = _load_pm_dispatch()
    inbox = tmp_path / "pm-inbox"
    inbox.mkdir()
    result_path = tmp_path / "partial-result.md"
    result_path.write_text("worker is still writing\n", encoding="utf-8")
    task_id = "pm-sprint-live-N1-deadbeef"
    record_path = inbox / f"{task_id}.json"
    record_path.write_text(json.dumps({
        "task_id": task_id,
        "status": "submitted",
        "submitted_at": "2026-08-27T21:00:00Z",
        "result_path": str(result_path),
        "expected_artifacts": [str(tmp_path / "not-published-yet.md")],
    }), encoding="utf-8")
    monkeypatch.setattr(pm_dispatch, "PM_INBOX_DIR", inbox)
    monkeypatch.setattr(pm_dispatch, "_active_pm_task_ids", lambda: {task_id})

    rc = pm_dispatch.cmd_reconcile(argparse.Namespace(max_age_minutes=30, apply=True, json=True))

    assert rc == 0
    persisted = json.loads(record_path.read_text(encoding="utf-8"))
    assert persisted["status"] == "submitted"
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"] == {"keep_active": 1}
    assert payload["actions"][0]["action"] == "keep_active"


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


def test_scientific_research_rejects_spark_without_research_capability(monkeypatch):
    pm_dispatch = _load_pm_dispatch()
    monkeypatch.setattr(
        pm_dispatch,
        "load_registry",
        lambda: {
            "version": 1,
            "operators": {
                "mini-codex-gpt53-spark-builder-1": {
                    "enabled": True,
                    "available": True,
                    "roles": ["builder"],
                    "launch_cmd_kind": "command",
                    "task_classes": ["implementation", "tests", "code-edit"],
                    "strengths": ["code-edit", "independent-budget"],
                    "preferred_for": ["codex", "spark"],
                    "provider": "openai",
                    "model": "gpt-5.3-codex-spark",
                },
                "mini-codex-gpt55-medium-builder-1": {
                    "enabled": True,
                    "available": True,
                    "roles": ["builder"],
                    "launch_cmd_kind": "command",
                    "task_classes": ["research", "knowledge-extraction", "evidence"],
                    "strengths": ["web-research", "source-grounding"],
                    "preferred_for": ["research", "report-writing"],
                    "provider": "openai",
                    "model": "gpt-5.5",
                },
            },
        },
    )
    monkeypatch.setattr(pm_dispatch, "is_dispatchable", lambda op: (True, ""))
    monkeypatch.setattr(pm_dispatch, "_load_concurrency_policy_module", lambda: None)
    monkeypatch.setattr(pm_dispatch, "DEFAULT_OPERATOR_PROVIDERS", ["openai"])

    operator_id, operator, reason = pm_dispatch.select_operator_by_role(
        role="builder",
        task_type="scientific-research",
        logical_operator="ScientificLiteratureDiscoverer",
    )

    assert reason == ""
    assert operator_id == "mini-codex-gpt55-medium-builder-1"
    assert operator["model"] == "gpt-5.5"


def test_low_cost_ceiling_uses_spark_planner_spillover(monkeypatch):
    pm_dispatch = _load_pm_dispatch()
    monkeypatch.setenv("SOLAR_PM_MAX_COST_TIER", "low")
    monkeypatch.setenv("SOLAR_PM_ALLOW_ROLE_SPILLOVER_IN_PROVIDER_MODE", "1")
    monkeypatch.setattr(pm_dispatch, "DEFAULT_OPERATOR_PROVIDERS", frozenset({"openai"}))
    monkeypatch.setattr(
        pm_dispatch,
        "load_registry",
        lambda: {
            "version": 1,
            "operators": {
                "medium-planner": {
                    "enabled": True,
                    "available": True,
                    "roles": ["planner"],
                    "provider": "openai",
                    "cost_tier": "medium",
                    "launch_cmd_kind": "print_once",
                    "task_classes": ["planning"],
                },
                "spark-builder": {
                    "enabled": True,
                    "available": True,
                    "roles": ["builder"],
                    "role": "builder",
                    "provider": "openai",
                    "model": "gpt-5.3-codex-spark",
                    "cost_tier": "low",
                    "launch_cmd_kind": "print_once",
                    "task_classes": ["implementation", "tests", "code-edit"],
                    "strengths": ["code-edit"],
                },
            },
        },
    )
    monkeypatch.setattr(pm_dispatch, "is_dispatchable", lambda op: (True, ""))
    policy_mod = types.SimpleNamespace(
        load_policy=lambda: {},
        builder_pool_enabled=lambda policy: False,
        pool_member_ids=lambda registry: [],
        infer_builder_group=lambda operator: "codex-gpt-5.3-spark",
    )
    monkeypatch.setattr(pm_dispatch, "_load_concurrency_policy_module", lambda: policy_mod)
    monkeypatch.setattr(
        pm_dispatch,
        "_role_spillover_spec",
        lambda policy_module, policy, role: {
            "enabled": True,
            "max_active": 1,
            "allowed_source_roles": ["builder"],
            "preferred_groups": [],
            "reason": "low-cost planner fallback",
        },
    )
    monkeypatch.setattr(pm_dispatch, "_active_role_spillover_count", lambda role: 0)

    operator_id, operator, reason = pm_dispatch.select_operator_by_role(
        role="planner",
        task_type="planning",
    )

    assert reason == ""
    assert operator_id == "spark-builder"
    assert operator["model"] == "gpt-5.3-codex-spark"
    assert operator["borrowed_for_role"] == "planner"


def test_preferred_operator_cannot_bypass_cost_ceiling(monkeypatch):
    pm_dispatch = _load_pm_dispatch()
    monkeypatch.setenv("SOLAR_PM_MAX_COST_TIER", "low")
    monkeypatch.setattr(
        pm_dispatch,
        "load_registry",
        lambda: {
            "version": 1,
            "operators": {
                "expensive-planner": {
                    "enabled": True,
                    "available": True,
                    "roles": ["planner"],
                    "provider": "openai",
                    "cost_tier": "high",
                }
            },
        },
    )

    operator_id, operator, reason = pm_dispatch.select_operator_by_role(
        role="planner",
        task_type="planning",
        prefer_operator="expensive-planner",
    )

    assert operator_id == ""
    assert operator == {}
    assert "preferred_operator_cost_tier_exceeds_ceiling" in reason


def test_planner_alternatives_preserve_order_and_exclude_undeclared_operators(monkeypatch):
    pm_dispatch = _load_pm_dispatch()
    monkeypatch.setattr(
        pm_dispatch,
        "load_registry",
        lambda: {
            "version": 1,
            "operators": {
                "preferred-builder": {
                    "enabled": True,
                    "available": True,
                    "roles": ["builder"],
                    "launch_cmd_kind": "command",
                    "task_classes": ["implementation"],
                },
                "fallback-builder": {
                    "enabled": True,
                    "available": True,
                    "roles": ["builder"],
                    "launch_cmd_kind": "command",
                    "task_classes": ["implementation"],
                },
                "undeclared-builder": {
                    "enabled": True,
                    "available": True,
                    "roles": ["builder"],
                    "launch_cmd_kind": "command",
                    "task_classes": ["implementation"],
                },
            },
        },
    )
    monkeypatch.setattr(
        pm_dispatch,
        "is_dispatchable",
        lambda op: (
            (False, "runtime_state=leased")
            if op["operator_id"] == "preferred-builder"
            else (True, "")
        ),
    )

    operator_id, _operator, exclusions, reason = (
        pm_dispatch.select_operator_from_ordered_alternatives(
            ["preferred-builder", "fallback-builder"],
            role="builder",
            task_type="implementation",
        )
    )

    assert reason == ""
    assert operator_id == "fallback-builder"
    assert exclusions == [
        {
            "operator_id": "preferred-builder",
            "reason": "preferred_operator_unavailable: preferred-builder: runtime_state=leased",
            "stage": "selection",
        }
    ]


def test_strict_planner_alternative_never_falls_through_to_registry(monkeypatch):
    pm_dispatch = _load_pm_dispatch()
    monkeypatch.setattr(
        pm_dispatch,
        "load_registry",
        lambda: {
            "version": 1,
            "operators": {
                "declared-builder": {
                    "enabled": True,
                    "available": True,
                    "roles": ["builder"],
                },
                "undeclared-builder": {
                    "enabled": True,
                    "available": True,
                    "roles": ["builder"],
                },
            },
        },
    )
    monkeypatch.setattr(
        pm_dispatch,
        "is_dispatchable",
        lambda op: (
            (False, "runtime_state=leased")
            if op["operator_id"] == "declared-builder"
            else (True, "")
        ),
    )

    operator_id, operator, exclusions, reason = (
        pm_dispatch.select_operator_from_ordered_alternatives(
            ["declared-builder"],
            role="builder",
            task_type="implementation",
        )
    )

    assert operator_id == ""
    assert operator == {}
    assert reason == "operator_alternatives_exhausted"
    assert [item["operator_id"] for item in exclusions] == ["declared-builder"]


def test_submit_lease_race_retries_next_operator(monkeypatch, tmp_path):
    pm_dispatch = _load_pm_dispatch()
    monkeypatch.setenv("SOLAR_PM_DISPATCH_ALLOW_DIRECT", "1")
    monkeypatch.setattr(pm_dispatch, "HARNESS_DIR", tmp_path)
    monkeypatch.setattr(pm_dispatch, "SPRINTS_DIR", tmp_path / "sprints")
    monkeypatch.setattr(pm_dispatch, "PM_INBOX_DIR", tmp_path / "run" / "pm-inbox")
    monkeypatch.setattr(pm_dispatch, "OPERATOR_INBOX_DIR", tmp_path / "run" / "operator-inbox")
    monkeypatch.setattr(pm_dispatch, "DEFAULT_OPERATOR_PROVIDERS", frozenset())
    monkeypatch.setattr(pm_dispatch, "load_task_graph_node", lambda *_args: None)
    monkeypatch.setattr(pm_dispatch, "build_pm_dispatch_text", lambda **kwargs: f"operator={kwargs['operator_id']}")
    monkeypatch.setattr(
        pm_dispatch,
        "_build_pm_operator_envelope",
        lambda **kwargs: {
            "task_id": kwargs["task_id"],
            "operator_id": kwargs["operator_id"],
            "runtime_mode": "test",
            "provider_policy": "test",
        },
    )
    monkeypatch.setattr(
        pm_dispatch,
        "load_registry",
        lambda: {
            "version": 1,
            "operators": {
                "builder-primary": {
                    "enabled": True,
                    "available": True,
                    "roles": ["builder"],
                    "launch_cmd_kind": "command",
                    "task_classes": ["implementation"],
                    "model": "primary",
                },
                "builder-fallback": {
                    "enabled": True,
                    "available": True,
                    "roles": ["builder"],
                    "launch_cmd_kind": "command",
                    "task_classes": ["implementation"],
                    "model": "fallback",
                },
            },
        },
    )
    monkeypatch.setattr(pm_dispatch, "is_dispatchable", lambda _operator: (True, ""))
    records: list[dict] = []
    monkeypatch.setattr(pm_dispatch, "write_pm_task_record", lambda _task_id, record: records.append(dict(record)))

    class BusyError(RuntimeError):
        reason = "operator_busy"

    submitted: list[str] = []
    fake_operator_runtime = types.ModuleType("operator_runtime")

    def submit(envelope):
        submitted.append(envelope["operator_id"])
        if envelope["operator_id"] == "builder-primary":
            raise BusyError("lease was claimed after selection")
        return {"lease_id": "lease-fallback", "inbox_path": "fallback/inbox.json"}

    fake_operator_runtime.submit = submit  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "operator_runtime", fake_operator_runtime)

    args = argparse.Namespace(
        role="builder",
        objective="implement safely",
        operator="",
        operator_alternative=["builder-primary", "builder-fallback"],
        sprint="sprint-fallback",
        node="N1",
        task_type="implementation",
        context="",
        dry_run=False,
    )

    assert pm_dispatch.cmd_submit(args) == 0
    assert submitted == ["builder-primary", "builder-fallback"]
    assert records[-1]["operator_id"] == "builder-fallback"
    assert records[-1]["authorized_operator_alternatives"] == [
        "builder-primary",
        "builder-fallback",
    ]
    assert records[-1]["operator_selection_exclusions"] == [
        {
            "operator_id": "builder-primary",
            "reason": "operator_busy",
            "stage": "lease",
        }
    ]
    assert records[-1]["operator_fallbacks"] == [
        {
            "from_operator_id": "builder-primary",
            "to_operator_id": "builder-fallback",
            "reason": "operator_busy",
        }
    ]


def test_planner_alternative_exhaustion_is_persisted_for_gui(monkeypatch, tmp_path):
    pm_dispatch = _load_pm_dispatch()
    monkeypatch.setenv("SOLAR_PM_DISPATCH_ALLOW_DIRECT", "1")
    monkeypatch.setattr(pm_dispatch, "HARNESS_DIR", tmp_path)
    monkeypatch.setattr(pm_dispatch, "SPRINTS_DIR", tmp_path / "sprints")
    monkeypatch.setattr(pm_dispatch, "PM_INBOX_DIR", tmp_path / "run" / "pm-inbox")
    monkeypatch.setattr(pm_dispatch, "DEFAULT_OPERATOR_PROVIDERS", frozenset())
    monkeypatch.setattr(pm_dispatch, "load_task_graph_node", lambda *_args: None)
    monkeypatch.setattr(
        pm_dispatch,
        "load_registry",
        lambda: {
            "version": 1,
            "operators": {
                operator_id: {
                    "enabled": True,
                    "available": True,
                    "roles": ["builder"],
                    "launch_cmd_kind": "command",
                    "task_classes": ["implementation"],
                }
                for operator_id in ("builder-primary", "builder-fallback")
            },
        },
    )
    monkeypatch.setattr(pm_dispatch, "is_dispatchable", lambda _operator: (False, "runtime_state=leased"))
    records: list[dict] = []
    monkeypatch.setattr(pm_dispatch, "write_pm_task_record", lambda _task_id, record: records.append(dict(record)))

    args = argparse.Namespace(
        role="builder",
        objective="implement safely",
        operator="",
        operator_alternative=["builder-primary", "builder-fallback"],
        sprint="sprint-exhausted",
        node="N1",
        task_type="implementation",
        context="",
        dry_run=False,
    )

    assert pm_dispatch.cmd_submit(args) == 1
    assert records[-1]["status"] == "failed_no_dispatchable_operator"
    assert records[-1]["failure_reason"] == "operator_alternatives_exhausted"
    assert records[-1]["display_error"]["code"] == "operator_alternatives_exhausted"
    assert [
        item["operator_id"] for item in records[-1]["operator_selection_exclusions"]
    ] == ["builder-primary", "builder-fallback"]


def test_missing_operator_runtime_never_bypasses_lease_with_direct_inbox(monkeypatch, tmp_path):
    pm_dispatch = _load_pm_dispatch()
    monkeypatch.setenv("SOLAR_PM_DISPATCH_ALLOW_DIRECT", "1")
    monkeypatch.setattr(pm_dispatch, "HARNESS_DIR", tmp_path)
    monkeypatch.setattr(pm_dispatch, "SPRINTS_DIR", tmp_path / "sprints")
    monkeypatch.setattr(pm_dispatch, "PM_INBOX_DIR", tmp_path / "run" / "pm-inbox")
    monkeypatch.setattr(pm_dispatch, "OPERATOR_INBOX_DIR", tmp_path / "run" / "operator-inbox")
    monkeypatch.setattr(pm_dispatch, "DEFAULT_OPERATOR_PROVIDERS", frozenset())
    monkeypatch.setattr(pm_dispatch, "load_task_graph_node", lambda *_args: None)
    monkeypatch.setattr(pm_dispatch, "build_pm_dispatch_text", lambda **_kwargs: "dispatch")
    monkeypatch.setattr(pm_dispatch, "_build_pm_operator_envelope", lambda **kwargs: {"operator_id": kwargs["operator_id"]})
    monkeypatch.setattr(
        pm_dispatch,
        "load_registry",
        lambda: {
            "version": 1,
            "operators": {
                "builder-only": {
                    "enabled": True,
                    "available": True,
                    "roles": ["builder"],
                    "launch_cmd_kind": "command",
                    "task_classes": ["implementation"],
                }
            },
        },
    )
    monkeypatch.setattr(pm_dispatch, "is_dispatchable", lambda _operator: (True, ""))
    monkeypatch.setattr(
        pm_dispatch,
        "_load_operator_submit",
        lambda: (_ for _ in ()).throw(ImportError("operator runtime missing")),
    )
    records: list[dict] = []
    monkeypatch.setattr(pm_dispatch, "write_pm_task_record", lambda _task_id, record: records.append(dict(record)))

    args = argparse.Namespace(
        role="builder",
        objective="implement safely",
        operator="",
        sprint="sprint-no-runtime",
        node="N1",
        task_type="implementation",
        context="",
        dry_run=False,
    )

    assert pm_dispatch.cmd_submit(args) == 1
    assert records[-1]["status"] == "failed_operator_runtime_unavailable"
    assert not (pm_dispatch.OPERATOR_INBOX_DIR / "builder-only").exists()


def test_pm_operator_envelope_carries_strict_filesystem_scope(monkeypatch, tmp_path):
    pm_dispatch = _load_pm_dispatch()
    sprints = tmp_path / "sprints"
    sprints.mkdir()
    monkeypatch.setattr(pm_dispatch, "SPRINTS_DIR", sprints)
    sid = "sprint-strict-fs"
    (sprints / f"{sid}.task_graph.json").write_text(
        json.dumps(
            {
                "workflow_contract": "research.autosci.v1",
                "strict_filesystem_boundaries": True,
                "nodes": [],
            }
        ),
        encoding="utf-8",
    )
    dispatch_file = tmp_path / "dispatch.md"
    dispatch_file.write_text("bounded task", encoding="utf-8")

    envelope = pm_dispatch._build_pm_operator_envelope(
        task_id="task-1",
        sprint_id=sid,
        node_id="literature_discover",
        operator_id="builder-1",
        operator={"provider": "openai", "backend": "command", "model": "gpt-test"},
        task_type="scientific-research",
        objective="discover",
        dispatch_file=dispatch_file,
        result_path=str(tmp_path / "result.md"),
        role="builder",
        task_graph_node={
            "id": "literature_discover",
            "goal": "discover",
            "acceptance": ["bounded"],
            "requirement_ids": ["REQ-000"],
            "read_scope": ["dispatch/envelope.json"],
            "write_scope": ["artifacts/scientific/literature.json"],
        },
        additional_read_scope=[str(tmp_path / "published"), "dispatch/envelope.json"],
    )

    assert envelope["workflow_contract"] == "research.autosci.v1"
    assert envelope["strict_filesystem_boundaries"] is True
    assert envelope["read_scope"] == ["dispatch/envelope.json", str(tmp_path / "published")]
    assert envelope["write_scope"] == ["artifacts/scientific/literature.json"]
    assert envelope["write_scope_root"] == str(sprints / sid / "workdir")
    assert envelope["write_scope_resolution"] == "relative_to_write_scope_root"


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
                    "required_skills": ["python_implementation"],
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
        assert envelope["selected_skills"] == ["python_implementation"]


def test_capsule_submit_repairs_persisted_empty_grounded_compiler_bridge(monkeypatch):
    import capability_capsules

    monkeypatch.setattr(capability_capsules, "HARNESS_DIR", ROOT)
    monkeypatch.setattr(
        capability_capsules,
        "CAPSULE_REGISTRY_PATH",
        ROOT / "config" / "capability-capsules.registry.yaml",
    )
    pm_dispatch = _load_pm_dispatch()

    metadata = pm_dispatch._capsule_submit_metadata(
        {
            "id": "R4",
            "goal": "Compile the grounded synthesis into a governed Chinese report.",
            "logical_operator": "GroundedResearchCompiler",
            "dispatch_task_type": "research",
            "capability_capsule_id": "cap.skill-execution-bridge",
            "capsule_plan_ir": {
                "capability_capsule_id": "cap.skill-execution-bridge",
                "selected_skills": [],
            },
        }
    )

    assert metadata["capability_capsule_id"] == "cap.requirement-research-synthesizer"
    assert metadata["dispatch_task_type"] == "research"
    assert metadata["capsule_override_reason"] == "invalid_empty_skill_bridge_recovered"


def test_cmd_submit_canonicalizes_analysis_audit_node_before_submit(monkeypatch):
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
                    "id": "S1",
                    "goal": "Inspect repository scope and confirm CLI placement before implementation.",
                    "logical_operator": "ImplementationWorker",
                    "capability_native": True,
                    "capability_capsule_id": "cap.requirement-compiler-audit",
                    "dispatch_task_type": "analysis",
                    "type": "analysis",
                }
            ]
        }
        (root / "sprints").mkdir(parents=True, exist_ok=True)
        (root / "sprints" / "sprint-audit.task_graph.json").write_text(json.dumps(sprint_graph), encoding="utf-8")

        monkeypatch.setattr(
            pm_dispatch,
            "load_registry",
            lambda: {
                "version": 1,
                "operators": {
                    "mini-codex-gpt53-spark-builder-1": {
                        "enabled": True,
                        "available": True,
                        "roles": ["builder"],
                        "launch_cmd_kind": "command",
                        "task_classes": ["audit_inventory"],
                        "profile": "codex-builder",
                        "preferred_for": ["codex"],
                        "provider": "openai",
                        "model": "gpt-5.3-codex-spark",
                        "persona": "builder",
                    }
                },
            },
        )
        monkeypatch.setattr(pm_dispatch, "is_dispatchable", lambda op: (True, ""))

        sys.path.insert(0, str(ROOT / "lib"))
        import capability_capsules as caps

        resolve_call: dict[str, object] = {}

        def _resolve(task, operator_id=None, registry_path=None):
            resolve_call["task"] = dict(task)
            return {
                "capability_capsule_id": "cap.requirement-compiler-audit",
                "operator_constraints": {
                    "preferred": ["mini-codex-gpt53-spark-builder-1"],
                    "forbidden": [],
                    "default_operator_profile": "mini-codex-gpt53-spark-builder-1",
                },
            }

        monkeypatch.setattr(caps, "resolve_capability_capsule_for_task", _resolve)

        captured: dict[str, object] = {}
        fake_operator_runtime = types.ModuleType("operator_runtime")

        def _submit(envelope):
            captured["envelope"] = dict(envelope)
            return {
                "lease_id": "lease-1",
                "inbox_path": str(root / "run" / "operator-inbox" / "mini-codex-gpt53-spark-builder-1" / "pm.json"),
            }

        fake_operator_runtime.submit = _submit  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "operator_runtime", fake_operator_runtime)
        monkeypatch.setenv("SOLAR_PM_DISPATCH_ALLOW_DIRECT", "1")
        monkeypatch.setenv("SOLAR_PM_DEFAULT_PROVIDERS", "openai")

        args = argparse.Namespace(
            role="builder",
            objective="Inspect repository scope and confirm CLI placement before implementation.",
            operator="",
            sprint="sprint-audit",
            node="S1",
            task_type="",
            context="",
            dry_run=False,
        )
        rc = pm_dispatch.cmd_submit(args)
        assert rc == 0
        assert resolve_call["task"]["task_type"] == "audit_inventory"
        envelope = captured["envelope"]
        assert envelope["operator_id"] == "mini-codex-gpt53-spark-builder-1"
        assert envelope["capability_capsule_id"] == "cap.requirement-compiler-audit"
        assert envelope["task_type"] == "audit_inventory"


def test_cmd_submit_canonicalizes_implementation_capsule_test_authoring(monkeypatch):
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
                    "goal": "Author focused tests for the implementation.",
                    "logical_operator": "ImplementationWorker",
                    "capability_native": True,
                    "capability_capsule_id": "cap.requirement-compiler-implementation",
                    "dispatch_task_type": "tests",
                    "type": "implementation",
                }
            ]
        }
        (root / "sprints").mkdir(parents=True, exist_ok=True)
        (root / "sprints" / "sprint-tests.task_graph.json").write_text(json.dumps(sprint_graph), encoding="utf-8")

        monkeypatch.setattr(
            pm_dispatch,
            "load_registry",
            lambda: {
                "version": 1,
                "operators": {
                    "mini-codex-gpt55-medium-builder-1": {
                        "enabled": True,
                        "available": True,
                        "roles": ["builder"],
                        "launch_cmd_kind": "command",
                        "task_classes": ["implementation"],
                        "profile": "codex-builder",
                        "preferred_for": ["codex", "implementation"],
                        "provider": "openai",
                        "model": "gpt-5.5",
                        "persona": "builder",
                    }
                },
            },
        )
        monkeypatch.setattr(pm_dispatch, "is_dispatchable", lambda op: (True, ""))

        sys.path.insert(0, str(ROOT / "lib"))
        import capability_capsules as caps

        resolve_call: dict[str, object] = {}

        def _resolve(task, operator_id=None, registry_path=None):
            resolve_call["task"] = dict(task)
            return {
                "capability_capsule_id": "cap.requirement-compiler-implementation",
                "operator_constraints": {
                    "preferred": ["mini-codex-gpt55-medium-builder-1"],
                    "forbidden": [],
                    "default_operator_profile": "mini-codex-gpt55-medium-builder-1",
                },
            }

        monkeypatch.setattr(caps, "resolve_capability_capsule_for_task", _resolve)

        captured: dict[str, object] = {}
        fake_operator_runtime = types.ModuleType("operator_runtime")

        def _submit(envelope):
            captured["envelope"] = dict(envelope)
            return {
                "lease_id": "lease-1",
                "inbox_path": str(root / "run" / "operator-inbox" / "mini-codex-gpt55-medium-builder-1" / "pm.json"),
            }

        fake_operator_runtime.submit = _submit  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "operator_runtime", fake_operator_runtime)
        monkeypatch.setenv("SOLAR_PM_DISPATCH_ALLOW_DIRECT", "1")
        monkeypatch.setenv("SOLAR_PM_DEFAULT_PROVIDERS", "openai")

        args = argparse.Namespace(
            role="builder",
            objective="Author focused tests for the implementation.",
            operator="",
            sprint="sprint-tests",
            node="S2",
            task_type="",
            context="",
            dry_run=False,
        )
        rc = pm_dispatch.cmd_submit(args)
        assert rc == 0
        assert resolve_call["task"]["task_type"] == "implementation"
        envelope = captured["envelope"]
        assert envelope["operator_id"] == "mini-codex-gpt55-medium-builder-1"
        assert envelope["capability_capsule_id"] == "cap.requirement-compiler-implementation"
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


def test_cmd_compile_request_reports_typed_request_size_error(monkeypatch, tmp_path, capsys):
    pm_dispatch = _load_pm_dispatch()
    monkeypatch.setenv("SOLAR_PM_DISPATCH_ALLOW_DIRECT", "1")
    monkeypatch.setattr(pm_dispatch, "SPRINTS_DIR", tmp_path / "sprints")
    monkeypatch.setattr(pm_dispatch, "HARNESS_DIR", tmp_path / "harness")

    class _RequestTooLargeError(ValueError):
        def __init__(self, actual_chars, max_chars):
            self.actual_chars = actual_chars
            self.max_chars = max_chars

    def _reject_request(*args, **kwargs):
        raise _RequestTooLargeError(12_001, 12_000)

    router = types.SimpleNamespace(
        RequestTooLargeError=_RequestTooLargeError,
        build_pm_intake=_reject_request,
    )

    class _Loader:
        def exec_module(self, module):
            return None

    fake_spec = types.SimpleNamespace(loader=_Loader())
    monkeypatch.setattr(pm_dispatch.importlib.util, "spec_from_file_location", lambda *args, **kwargs: fake_spec)
    monkeypatch.setattr(pm_dispatch.importlib.util, "module_from_spec", lambda spec: router)

    args = argparse.Namespace(
        text="x" * 12_001,
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

    assert pm_dispatch.cmd_compile_request(args) == 2
    captured = capsys.readouterr()
    assert captured.err == ""
    assert json.loads(captured.out) == {
        "ok": False,
        "error": "request_too_long",
        "actual_chars": 12_001,
        "max_chars": 12_000,
    }


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


def test_codex_operator_health_accepts_path_resolved_codex(monkeypatch):
    pm_dispatch = _load_pm_dispatch()
    monkeypatch.setattr(pm_dispatch, "_read_health_cache", lambda *args, **kwargs: (False, "command_path_missing:/opt/homebrew/bin/codex"))
    captured: dict[str, object] = {}

    def fake_write_health_cache(operator_id, ok, reason):
        captured.update({"operator_id": operator_id, "ok": ok, "reason": reason})

    monkeypatch.setattr(pm_dispatch, "_write_health_cache", fake_write_health_cache)
    monkeypatch.setattr(pm_dispatch.shutil, "which", lambda cmd: "/tmp/bin/codex" if cmd == "codex" else None)
    ok, reason = pm_dispatch._operator_external_health(
        {
            "operator_id": "mini-codex-gpt55-medium-builder-1",
            "provider": "openai",
            "model": "gpt-5.5",
            "command_path": "/opt/homebrew/bin/codex",
            "health_check": {
                "type": "command",
                "command_path": "/opt/homebrew/bin/codex",
                "cache_seconds": 300,
            },
        }
    )
    assert ok is True
    assert reason == "command_path_resolved_via_path:/tmp/bin/codex"
    assert captured == {
        "operator_id": "mini-codex-gpt55-medium-builder-1",
        "ok": True,
        "reason": "command_path_resolved_via_path:/tmp/bin/codex",
    }


def test_codex_operator_health_accepts_wsl_desktop_materialization(monkeypatch, tmp_path):
    pm_dispatch = _load_pm_dispatch()
    materialized = tmp_path / "run" / "codex-cli-runtime" / "fixture" / "codex"
    monkeypatch.setattr(pm_dispatch.shutil, "which", lambda _cmd: None)
    monkeypatch.setattr(
        pm_dispatch,
        "resolve_codex_cli",
        lambda *_args, **_kwargs: (materialized, "windows_desktop_wsl_copy"),
    )

    ok, reason = pm_dispatch._command_path_available(
        "/opt/homebrew/bin/codex",
        {
            "provider": "openai",
            "model": "gpt-5.5",
            "command_path": "/opt/homebrew/bin/codex",
        },
    )

    assert ok is True
    assert reason == (
        "command_path_resolved_via_windows_desktop_wsl_copy:"
        f"{materialized}"
    )


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


def test_builder_pool_snapshot_separates_provider_policy_capacity(monkeypatch):
    """Idle operators from a forbidden provider are not product capacity.

    RC9 live-install replay: the run policy allowed only Anthropic.  The sole
    Anthropic builder was running, while two OpenAI builders were idle.  The
    all-provider pool total was therefore two, but dispatch had zero eligible
    capacity and correctly returned ``builder_pool_depleted``.
    """

    pm_dispatch = _load_pm_dispatch()
    monkeypatch.setattr(pm_dispatch, "DEFAULT_OPERATOR_PROVIDERS", frozenset({"anthropic"}))
    monkeypatch.setattr(
        pm_dispatch,
        "load_registry",
        lambda: {
            "operators": {
                "claude-builder": {
                    "enabled": True,
                    "available": True,
                    "provider": "anthropic",
                },
                "codex-builder-1": {
                    "enabled": True,
                    "available": True,
                    "provider": "openai",
                },
                "codex-builder-2": {
                    "enabled": True,
                    "available": True,
                    "provider": "openai",
                },
            }
        },
    )
    policy_mod = types.SimpleNamespace(
        load_policy=lambda: {},
        builder_pool_config=lambda policy: {"groups": {"builders": {"desired": 3}}},
        pool_group_desired=lambda group, policy: 3,
        is_pool_member=lambda op: True,
        infer_builder_group=lambda op: "builders",
        builder_pool_desired_total=lambda policy: 3,
        recovery_settings=lambda policy: {},
        active_level=lambda policy: "test",
    )
    monkeypatch.setattr(pm_dispatch, "_load_concurrency_policy_module", lambda: policy_mod)
    monkeypatch.setattr(
        pm_dispatch,
        "is_dispatchable",
        lambda op: (
            (False, "runtime_state_running")
            if op["provider"] == "anthropic"
            else (True, "")
        ),
    )
    monkeypatch.setattr(
        pm_dispatch,
        "get_operator_runtime_state",
        lambda op_id: "running" if op_id == "claude-builder" else "idle",
    )
    monkeypatch.setattr(
        pm_dispatch,
        "_operator_block_info",
        lambda op_id, op, state, reason: {
            "block_type": "busy" if state == "running" else "none"
        },
    )
    monkeypatch.setattr(
        pm_dispatch,
        "_builder_pool_backlog_breakdown",
        lambda: {"pending_pm": 0, "latent_builder_ready": 0, "total": 0},
    )
    monkeypatch.setattr(pm_dispatch, "_rate_limit_pruner_status", lambda: {})

    snapshot = pm_dispatch.builder_pool_snapshot()

    assert snapshot["total_available"] == 2
    assert snapshot["total_policy_available"] == 0
    assert snapshot["provider_policy"] == "anthropic"
    eligibility = {
        row["operator_id"]: row["provider_policy_eligible"]
        for row in snapshot["operators"]
    }
    assert eligibility == {
        "claude-builder": True,
        "codex-builder-1": False,
        "codex-builder-2": False,
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
    graph_scheduler = pm_dispatch._load_graph_scheduler_module()
    assert graph_scheduler is not None
    graph_scheduler.SPRINTS_DIR = sprints
    graph = graph_scheduler.load_graph(sprints / "sprint-drain.task_graph.json")
    assert graph["nodes"][0]["status"] == "dispatched"
    assert graph["node_results"]["B1"]["dispatched_via"] == "pm_dispatch"
    assert graph["node_results"]["B1"]["pm_task_id"] == "pm-sprint-drain-B1-test"
