#!/usr/bin/env python3
"""Regression tests for graph-node patch proof sidecars."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = (Path(__file__).resolve().parents[3] / 'harness')


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _exercise_patch_proof(module, tmp_path: Path, monkeypatch) -> None:
    harness = tmp_path / "harness"
    sprints = harness / "sprints"
    sid = "sprint-patch-proof"
    workdir = sprints / sid / "workdir"
    workdir.mkdir(parents=True)
    target = workdir / "uniqwords.py"
    target.write_text("print('ok')\n", encoding="utf-8")
    monkeypatch.setattr(module, "HARNESS_DIR", harness)
    monkeypatch.setattr(module, "SPRINTS_DIR", sprints)
    node = {
        "id": "S1",
        "write_scope": [f"harness/sprints/{sid}/workdir/uniqwords.py"],
        "proof_obligations": [
            {"kind": "pass_condition", "requirement": "patch_diff exists"},
            {"kind": "postcondition", "requirement": "output_present", "field": "patch_diff"},
        ],
    }

    emitted = module._emit_node_proof_sidecars(sid, node)
    patch_path = sprints / f"{sid}.S1-patch.diff"

    assert emitted["patch_diff"] == str(patch_path)
    assert patch_path.exists()
    patch = patch_path.read_text(encoding="utf-8")
    assert "diff --git a/harness/sprints/sprint-patch-proof/workdir/uniqwords.py" in patch
    assert "--- /dev/null" in patch
    assert "+print('ok')" in patch
    assert module._proof_artifact_presence(sid, node)["patch_diff"] is True
    assert module._evaluate_proof_obligations(sid, node)["ok"] is True


def _configure_module(module, tmp_path: Path, monkeypatch):
    harness = tmp_path / "harness"
    sprints = harness / "sprints"
    monkeypatch.setattr(module, "HARNESS_DIR", harness)
    monkeypatch.setattr(module, "SPRINTS_DIR", sprints)
    return harness, sprints


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_lib_dispatcher_emits_patch_diff_from_write_scope(tmp_path, monkeypatch):
    monkeypatch.delenv("HARNESS_DIR", raising=False)
    monkeypatch.delitem(sys.modules, "graph_scheduler", raising=False)
    module = _load_module("graph_node_dispatcher_lib_patch_proof", ROOT / "lib" / "graph_node_dispatcher.py")
    _exercise_patch_proof(module, tmp_path, monkeypatch)


def test_tools_dispatcher_emits_patch_diff_from_write_scope(tmp_path, monkeypatch):
    monkeypatch.delenv("HARNESS_DIR", raising=False)
    monkeypatch.delitem(sys.modules, "graph_scheduler", raising=False)
    monkeypatch.setenv("HARNESS_DIR", str(ROOT))
    module = _load_module("graph_node_dispatcher_tools_patch_proof", ROOT / "tools" / "graph_node_dispatcher.py")

    assert module._IMPL.__file__ == str(ROOT / "lib" / "graph_node_dispatcher.py")
    assert module.main is module._IMPL.main


def test_patch_sidecar_emits_from_requirement_without_field(tmp_path, monkeypatch):
    module = _load_module("graph_node_dispatcher_patch_requirement", ROOT / "lib" / "graph_node_dispatcher.py")
    _, sprints = _configure_module(module, tmp_path, monkeypatch)
    sid = "sprint-requirement-only"
    workdir = sprints / sid / "workdir"
    workdir.mkdir(parents=True)
    (workdir / "uniqwords.py").write_text("print('words')\n", encoding="utf-8")
    capsule = sprints / f"{sid}.S1-capsule-plan.json"
    _write_json(capsule, {"proof_obligations": [{"kind": "pass_condition", "requirement": "patch_diff exists"}]})
    node = {
        "id": "S1",
        "write_scope": ["uniqwords.py"],
        "outputs": ["uniqwords.py"],
        "artifacts": {"capsule_plan_ir": str(capsule)},
    }

    emitted = module._emit_node_proof_sidecars(sid, node)

    patch_path = sprints / f"{sid}.S1-patch.diff"
    assert emitted["patch_diff"] == str(patch_path)
    assert patch_path.exists()
    assert "uniqwords.py" in patch_path.read_text(encoding="utf-8")
    assert not (sprints / f"{sid}.S1-patch_diff_not_emitted.json").exists()
    assert module._evaluate_proof_obligations(sid, node)["ok"] is True


def test_patch_sidecar_emits_from_field_obligation(tmp_path, monkeypatch):
    module = _load_module("graph_node_dispatcher_patch_field", ROOT / "lib" / "graph_node_dispatcher.py")
    _, sprints = _configure_module(module, tmp_path, monkeypatch)
    sid = "sprint-field"
    workdir = sprints / sid / "workdir"
    workdir.mkdir(parents=True)
    (workdir / "uniqwords.py").write_text("print('field')\n", encoding="utf-8")
    node = {
        "id": "S1",
        "write_scope": ["uniqwords.py"],
        "proof_obligations": [
            {"kind": "postcondition", "requirement": "output_present", "check": "output_present", "field": "patch_diff"}
        ],
    }

    emitted = module._emit_node_proof_sidecars(sid, node)

    assert emitted["patch_diff"] == str(sprints / f"{sid}.S1-patch.diff")
    assert module._proof_artifact_presence(sid, node)["patch_diff"] is True
    assert module._evaluate_proof_obligations(sid, node)["ok"] is True


def test_patch_presence_requires_actual_patch_file(tmp_path, monkeypatch):
    module = _load_module("graph_node_dispatcher_patch_presence", ROOT / "lib" / "graph_node_dispatcher.py")
    _, sprints = _configure_module(module, tmp_path, monkeypatch)
    sid = "sprint-no-patch"
    workdir = sprints / sid / "workdir"
    workdir.mkdir(parents=True)
    (workdir / "uniqwords.py").write_text("print('no patch yet')\n", encoding="utf-8")
    (sprints / f"{sid}.S1-handoff.md").write_text("# Handoff\n", encoding="utf-8")
    node = {
        "id": "S1",
        "write_scope": ["uniqwords.py"],
        "proof_obligations": [{"kind": "pass_condition", "requirement": "patch_diff exists"}],
    }

    presence = module._proof_artifact_presence(sid, node)
    result = module._evaluate_proof_obligations(sid, node)

    assert presence["handoff_md"] is True
    assert presence["patch_diff"] is False
    assert result["ok"] is False
    assert result["missing"][0]["reason"] == "patch_diff_missing"


def test_failed_sprint_node_shape_emits_patch_sidecar(tmp_path, monkeypatch):
    module = _load_module("graph_node_dispatcher_failed_shape", ROOT / "lib" / "graph_node_dispatcher.py")
    _, sprints = _configure_module(module, tmp_path, monkeypatch)
    sid = "sprint-20260701-174448-intent-write-a-python-command-line--c2fcb93a"
    workdir = sprints / sid / "workdir"
    workdir.mkdir(parents=True)
    (workdir / "uniqwords.py").write_text("print('failed sprint shape')\n", encoding="utf-8")
    capsule = sprints / f"{sid}.S1-capsule-plan.json"
    physical = sprints / f"{sid}.S1-physical-plan.json"
    obligations = [
        {"kind": "pass_condition", "source_capsule_id": "cap.requirement-compiler-implementation", "requirement": "patch_diff exists"},
        {
            "kind": "postcondition",
            "source_capsule_id": "cap.requirement-compiler-implementation",
            "requirement": "output_present",
            "check": "output_present",
            "field": "patch_diff",
        },
    ]
    _write_json(capsule, {"proof_obligations": obligations})
    _write_json(physical, {"selected_operator_id": "mini-claude-sonnet-builder", "proof_obligations": obligations})
    node = {
        "id": "S1",
        "write_scope": ["uniqwords.py"],
        "outputs": ["uniqwords.py"],
        "artifacts": {
            "capsule_plan_ir": str(capsule),
            "physical_plan_ir": str(physical),
            "selected_operator_id": "mini-claude-sonnet-builder",
        },
    }

    emitted = module._emit_node_proof_sidecars(sid, node)

    patch_path = sprints / f"{sid}.S1-patch.diff"
    assert emitted["patch_diff"] == str(patch_path)
    assert patch_path.exists()
    assert module._evaluate_proof_obligations(sid, node)["ok"] is True


def test_patch_not_emitted_records_no_write_scope_reason(tmp_path, monkeypatch):
    module = _load_module("graph_node_dispatcher_no_scope_reason", ROOT / "lib" / "graph_node_dispatcher.py")
    _, sprints = _configure_module(module, tmp_path, monkeypatch)
    sid = "sprint-no-targets"
    node = {
        "id": "S1",
        "write_scope": ["missing.py"],
        "proof_obligations": [{"kind": "pass_condition", "requirement": "patch_diff exists"}],
    }

    emitted = module._emit_node_proof_sidecars(sid, node)

    reason_file = sprints / f"{sid}.S1-patch_diff_not_emitted.json"
    assert "patch_diff" not in emitted
    reason = json.loads(reason_file.read_text(encoding="utf-8"))
    assert reason["reason"] == "patch_diff_not_emitted_no_write_scope_targets"
    assert module._proof_artifact_presence(sid, node)["patch_diff"] is False


def test_repair_archives_failed_evidence_and_repair_can_emit_patch(tmp_path, monkeypatch):
    module = _load_module("graph_node_dispatcher_repair_archive_patch", ROOT / "lib" / "graph_node_dispatcher.py")
    _, sprints = _configure_module(module, tmp_path, monkeypatch)
    sid = "sprint-repair"
    node = {
        "id": "S1",
        "write_scope": ["uniqwords.py"],
        "proof_obligations": [{"kind": "pass_condition", "requirement": "patch_diff exists"}],
        "max_repair_attempts": 1,
    }
    graph = {"nodes": [node]}
    handoff = sprints / f"{sid}.S1-handoff.md"
    eval_json = sprints / f"{sid}.S1-eval.json"
    eval_md = sprints / f"{sid}.S1-eval.md"
    handoff.parent.mkdir(parents=True, exist_ok=True)
    handoff.write_text("# failed handoff\n", encoding="utf-8")
    _write_json(eval_json, {"verdict": "FAIL", "summary": "missing patch"})
    eval_md.write_text("# failed eval\n", encoding="utf-8")

    repair_context = module._start_node_repair_from_eval_fail(
        graph,
        node,
        sid,
        "S1",
        handoff,
        str(eval_json),
        {"summary": "missing patch", "failed_conditions": ["proof:patch_diff exists"]},
    )

    archive_dir = sprints / sid / "attempts" / "S1" / "1"
    assert repair_context is not None
    assert (archive_dir / "handoff_md.md").exists()
    assert (archive_dir / "eval_json.json").exists()
    assert (archive_dir / "eval_md.md").exists()
    workdir = sprints / sid / "workdir"
    workdir.mkdir(parents=True)
    (workdir / "uniqwords.py").write_text("print('repair')\n", encoding="utf-8")

    emitted = module._emit_node_proof_sidecars(sid, node)

    assert emitted["patch_diff"] == str(sprints / f"{sid}.S1-patch.diff")
