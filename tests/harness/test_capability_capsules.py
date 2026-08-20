#!/usr/bin/env python3
"""Tests for capability_capsules.py."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
import sys

import yaml

ROOT = (Path(__file__).resolve().parents[2] / 'harness')
sys.path.insert(0, str(ROOT / "lib"))

import capability_capsules as caps


def test_grounded_research_compiler_uses_governed_synthesis_capsule():
    plan = caps.default_capability_plan_for_logical_operator(
        "GroundedResearchCompiler",
        request_type="research",
        node={"goal": "Compile a grounded Chinese research report."},
        registry_path=ROOT / "config" / "capability-capsules.registry.yaml",
    )

    assert plan["capability_capsule_id"] == "cap.requirement-research-synthesizer"
    assert plan["dispatch_task_type"] == "research"
    assert plan["selected_skills"] == []


def _write_yaml(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def test_normalize_legacy_execution_capsule_maps_to_capability_shape():
    legacy = {
        "execution_capsule_id": "ecap-legacy-debugger",
        "skill_id": "skill.root-cause-debug",
        "skill_version": "0.1.0",
        "mcp_bindings": {"git.read": "provider-a"},
        "verification_rules": [{"check_name": "artifact_exists"}],
        "operator_id": "mini-claude-sonnet-builder",
        "created_at": "2026-05-24T00:00:00Z",
        "sprint_id": "sprint-x",
        "node_id": "N1",
    }
    normalized = caps.normalize_capability_capsule(legacy)
    assert normalized["capability_capsule_id"] == "ecap-legacy-debugger"
    assert normalized["bindings"]["skills"]["required"] == ["skill.root-cause-debug"]
    assert "git.read" in normalized["bindings"]["mcp_capabilities"]
    assert normalized["compatibility"]["legacy_execution_capsule_id"] == "ecap-legacy-debugger"


def test_validate_sample_capability_capsule_manifest_has_no_errors():
    manifest_path = ROOT / "config" / "capability-capsules" / "cap.flashmlx-performance-debugger.yaml"
    manifest = caps.load_capability_capsule_manifest(manifest_path)
    errors = caps.validate_capability_capsule(manifest, schema_path=ROOT / "schemas" / "draft" / "capability-capsule.v1.draft.json")
    assert errors == []


def test_validate_audit_capability_capsule_manifest_has_no_errors():
    manifest_path = ROOT / "config" / "capability-capsules" / "cap.requirement-compiler-audit.yaml"
    manifest = caps.load_capability_capsule_manifest(manifest_path)
    errors = caps.validate_capability_capsule(
        manifest,
        schema_path=ROOT / "schemas" / "draft" / "capability-capsule.v1.draft.json",
    )
    assert errors == []


def test_registry_loader_and_query_skip_non_stable_by_default():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        stable_manifest = root / "stable.yaml"
        deprecated_manifest = root / "deprecated.yaml"
        base_manifest = {
            "capability_capsule_id": "cap.example",
            "version": "0.1.0",
            "capsule_kind": "capability",
            "metadata": {"name": "Example", "description": "desc"},
            "applicability": {"task_types": ["CODE_IMPL"], "positive_signals": [], "negative_signals": []},
            "contract": {
                "inputs": {"required": [], "optional": []},
                "outputs": {"required": [], "optional": []},
                "preconditions": [{"check": "task_type_in", "values": ["CODE_IMPL"]}],
                "postconditions": [{"check": "output_present", "field": "x"}],
                "invariants": ["inv"],
            },
            "composition": {"consumes": [], "produces": [], "compatible_with": [], "incompatible_with": [], "requires_after": []},
            "effects": {"read": [], "write": [], "execute": [], "network": [], "cost": [], "risk": []},
            "bindings": {"skills": {"required": [], "optional": []}, "mcp_capabilities": {}, "data_refs": [], "secret_refs": []},
            "verification": {"self_check": ["x"], "external_verifier": {"required": False}, "pass_conditions": ["ok"]},
            "operator_compatibility": {"preferred": [], "forbidden": []},
            "provenance": {"owner": "tester"},
        }
        _write_yaml(stable_manifest, base_manifest)
        deprecated_payload = dict(base_manifest)
        deprecated_payload["capability_capsule_id"] = "cap.old"
        _write_yaml(deprecated_manifest, deprecated_payload)
        registry = {
            "version": 1,
            "capsules": {
                "capability": [
                    {
                        "capability_capsule_id": "cap.example",
                        "version": "0.1.0",
                        "capsule_kind": "capability",
                        "status": "stable",
                        "schema_ref": "schemas/draft/capability-capsule.v1.draft.json",
                        "manifest_path": str(stable_manifest),
                        "tags": [],
                        "owner": "tester",
                    },
                    {
                        "capability_capsule_id": "cap.old",
                        "version": "0.1.0",
                        "capsule_kind": "capability",
                        "status": "deprecated",
                        "schema_ref": "schemas/draft/capability-capsule.v1.draft.json",
                        "manifest_path": str(deprecated_manifest),
                        "tags": [],
                        "owner": "tester",
                    },
                ],
                "guard": [],
                "resource": [],
            },
        }
        registry_path = root / "registry.yaml"
        _write_yaml(registry_path, registry)
        stable_only = caps.iter_registry_entries(path=registry_path)
        assert [entry.capability_capsule_id for entry in stable_only] == ["cap.example"]
        all_entries = caps.iter_registry_entries(path=registry_path, include_deprecated=True)
        assert sorted(entry.capability_capsule_id for entry in all_entries) == ["cap.example", "cap.old"]


def test_resolution_gate_attaches_guard_and_resource_capsules(monkeypatch):
    monkeypatch.setattr(
        caps,
        "_query_capability_providers",
        lambda capability, min_level=3: [{"capability": capability, "provider": "plugin.test", "level": 4}],
    )
    envelope = {
        "capability_native": True,
        "capability_capsule_id": "cap.flashmlx-performance-debugger",
        "task_type": "PERFORMANCE_REGRESSION",
        "objective": "Investigate flashmlx throughput regression with benchmark evidence",
        "repo_path": "/tmp/repo",
        "benchmark_log": "/tmp/bench.log",
        "operator_id": "mini-claude-sonnet-builder",
    }
    resolved = caps.resolve_capability_capsule_for_envelope(
        envelope,
        registry_path=ROOT / "config" / "capability-capsules.registry.yaml",
    )
    assert resolved["capability_capsule_id"] == "cap.flashmlx-performance-debugger"
    assert resolved["attached_guard_capsules"] == ["guard.secret-leak-guard"]
    assert resolved["attached_resource_capsules"] == ["resource.github-readonly"]
    assert resolved["resolved_mcp_bindings"]["git.read"] == "plugin.test"


def test_resolution_gate_blocks_missing_resource(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        cap_manifest = ROOT / "config" / "capability-capsules" / "cap.flashmlx-performance-debugger.yaml"
        guard_manifest = ROOT / "config" / "capability-capsules" / "guard.secret-leak-guard.yaml"
        local_manifest = root / "cap.yaml"
        local_guard = root / "guard.yaml"
        local_manifest.write_text(cap_manifest.read_text(encoding="utf-8"), encoding="utf-8")
        local_guard.write_text(guard_manifest.read_text(encoding="utf-8"), encoding="utf-8")
        registry = {
            "version": 1,
            "capsules": {
                "capability": [
                    {
                        "capability_capsule_id": "cap.flashmlx-performance-debugger",
                        "version": "0.1.0",
                        "capsule_kind": "capability",
                        "status": "stable",
                        "schema_ref": "schemas/draft/capability-capsule.v1.draft.json",
                        "manifest_path": str(local_manifest),
                        "tags": [],
                        "owner": "tester",
                    }
                ],
                "guard": [
                    {
                        "capability_capsule_id": "guard.secret-leak-guard",
                        "version": "0.1.0",
                        "capsule_kind": "guard",
                        "status": "stable",
                        "schema_ref": "schemas/draft/capability-capsule.v1.draft.json",
                        "manifest_path": str(local_guard),
                        "tags": [],
                        "owner": "tester",
                    }
                ],
                "resource": [],
            },
        }
        registry_path = root / "registry.yaml"
        _write_yaml(registry_path, registry)
        monkeypatch.setattr(
            caps,
            "_query_capability_providers",
            lambda capability, min_level=3: [{"capability": capability, "provider": "plugin.test", "level": 4}],
        )
        envelope = {
            "capability_native": True,
            "capability_capsule_id": "cap.flashmlx-performance-debugger",
            "task_type": "PERFORMANCE_REGRESSION",
            "objective": "Investigate flashmlx throughput regression with benchmark evidence",
            "repo_path": "/tmp/repo",
            "benchmark_log": "/tmp/bench.log",
            "operator_id": "mini-claude-sonnet-builder",
        }
        try:
            caps.resolve_capability_capsule_for_envelope(envelope, registry_path=registry_path)
            assert False, "expected CapsuleResolutionError"
        except caps.CapsuleResolutionError as exc:
            assert "missing_resource" in str(exc)


def test_default_capability_plan_for_logical_operator_maps_requirement_nodes():
    planner = caps.default_capability_plan_for_logical_operator(
        "DeepArchitect",
        request_type="full_prd",
        lane_hint="strategy",
        node={"goal": "Lock implementation approach."},
        registry_path=ROOT / "config" / "capability-capsules.registry.yaml",
    )
    builder = caps.default_capability_plan_for_logical_operator(
        "ImplementationWorker",
        request_type="implementation",
        lane_hint="execution",
        node={"goal": "Implement approved scope."},
        registry_path=ROOT / "config" / "capability-capsules.registry.yaml",
    )
    assert planner["capability_capsule_id"] == "cap.requirement-compiler-planner"
    assert planner["dispatch_task_type"] == "planning"
    assert builder["capability_capsule_id"] == "cap.requirement-compiler-implementation"
    assert builder["required_resource_capsules"] == ["resource.repo-workspace"]


def test_read_only_audit_nodes_use_audit_capsule_not_patch_capsule():
    audit = caps.default_capability_plan_for_logical_operator(
        "ImplementationWorker",
        request_type="implementation",
        lane_hint="execution",
        node={
            "id": "A1",
            "goal": "Inventory backend entrypoints for packaging readiness without modifying source code.",
            "type": "audit_inventory",
            "required_skills": ["documentation", "harness.reporting"],
            "write_scope": ["harness/sprints/sprint-x.audit-backend-entrypoints.md"],
            "architecture_policy": {
                "package_boundary": "sprint-artifacts-only",
                "core_patch_allowed": False,
            },
        },
        registry_path=ROOT / "config" / "capability-capsules.registry.yaml",
    )
    assert audit["capability_capsule_id"] == "cap.requirement-compiler-audit"
    assert audit["dispatch_task_type"] == "audit_inventory"
    assert audit["selection_mode"] == "read_only_audit_heuristic"


def test_read_only_analysis_scope_node_canonicalizes_to_admitted_audit_type():
    audit = caps.default_capability_plan_for_logical_operator(
        "ImplementationWorker",
        request_type="analysis",
        lane_hint="",
        node={
            "id": "S1",
            "goal": "Inspect repository scope and confirm the targeted CLI placement before implementation.",
            "type": "analysis",
            "dispatch_task_type": "analysis",
            "required_skills": ["python", "cli-design"],
            "write_scope": ["sprints/sprint-x.S1.scope.md"],
        },
        registry_path=ROOT / "config" / "capability-capsules.registry.yaml",
    )
    assert audit["capability_capsule_id"] == "cap.requirement-compiler-audit"
    assert audit["dispatch_task_type"] == "audit_inventory"
    assert audit["selection_mode"] == "read_only_audit_heuristic"

    resolved = caps.resolve_capability_capsule_for_task(
        {
            "task_type": audit["dispatch_task_type"],
            "objective": "Inspect repository scope and report the chosen CLI placement.",
            "capability_capsule_id": audit["capability_capsule_id"],
        },
        registry_path=ROOT / "config" / "capability-capsules.registry.yaml",
    )
    assert resolved["capability_capsule_id"] == "cap.requirement-compiler-audit"


def test_skill_execution_bridge_is_registered_for_runtime_admission():
    registry_path = ROOT / "config" / "capability-capsules.registry.yaml"

    entry = caps.get_registry_entry(
        "cap.skill-execution-bridge",
        path=registry_path,
    )

    assert entry is not None
    assert Path(entry.manifest_path).name == "cap.skill-execution-bridge.yaml"
    resolved = caps.resolve_capability_capsule_for_task(
        {
            "task_type": "research",
            "objective": "Compile the grounded research report.",
            "selected_skills": ["research_compilation"],
            "capability_capsule_id": "cap.skill-execution-bridge",
        },
        operator_id="mini-codex-gpt55-medium-builder-1",
        registry_path=registry_path,
    )
    assert resolved["capability_capsule_id"] == "cap.skill-execution-bridge"
