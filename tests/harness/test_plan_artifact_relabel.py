from __future__ import annotations

import importlib.util
import json
import sys
import time
from pathlib import Path


ROOT = (Path(__file__).resolve().parents[2] / 'harness')
if str(ROOT / "lib") not in sys.path:
    sys.path.insert(0, str(ROOT / "lib"))

import apo_plan_compiler as apo  # noqa: E402
import route_proof  # noqa: E402


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _load_status_server(tmp_path: Path):
    harness = tmp_path / "harness"
    (harness / "sprints").mkdir(parents=True, exist_ok=True)
    name = f"status_server_relabel_{time.time_ns()}"
    module_path = ROOT / "lib" / "symphony" / "status-server.py"
    spec = importlib.util.spec_from_file_location(name, module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.HARNESS_DIR = harness
    module.SPRINTS_DIR = harness / "sprints"
    return module, harness


def _load_tools_apo():
    tools_dir = ROOT / "tools"
    if str(tools_dir) not in sys.path:
        sys.path.insert(0, str(tools_dir))
    name = f"tools_apo_plan_compiler_relabel_{time.time_ns()}"
    module_path = tools_dir / "apo_plan_compiler.py"
    spec = importlib.util.spec_from_file_location(name, module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_tools_status_server(tmp_path: Path):
    harness = tmp_path / "harness"
    (harness / "sprints").mkdir(parents=True, exist_ok=True)
    name = f"tools_status_server_relabel_{time.time_ns()}"
    module_path = ROOT / "tools" / "symphony" / "status-server.py"
    spec = importlib.util.spec_from_file_location(name, module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.HARNESS_DIR = harness
    module.SPRINTS_DIR = harness / "sprints"
    return module, harness


def _seed_route_registry(harness: Path) -> None:
    _write_json(
        harness / "config" / "physical-operators.json",
        {
            "version": 1,
            "operators": {
                "codex-builder": {
                    "role": "builder",
                    "provider": "openai",
                    "backend": "command",
                    "model": "gpt-5.3-codex-spark",
                    "enabled": True,
                }
            },
        },
    )


def _seed_pm_record(harness: Path, sid: str, task_id: str, operator_id: str) -> None:
    _write_json(
        harness / "run" / "pm-inbox" / f"{task_id}.json",
        {
            "task_id": task_id,
            "sprint_id": sid,
            "node_id": "S1",
            "requested_role": "builder",
            "runtime_mode": "codex",
            "provider_policy": "openai",
            "operator_id": operator_id,
            "status": "completed",
        },
    )


def _seed_result(harness: Path, sid: str, task_id: str, operator_id: str) -> None:
    _write_json(
        harness / "run" / "operator-results" / operator_id / task_id / "result.json",
        {
            "task_id": task_id,
            "sprint_id": sid,
            "node_id": "S1",
            "operator_id": operator_id,
            "status": "completed",
            "exit_code": 0,
            "effective_provider": "openai",
            "effective_model": "gpt-5.5",
        },
    )


def test_product_mode_materialized_physical_plan_relabels_operator_suggestion(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SOLAR_PRODUCT_MODE", "1")
    physical_plan = {
        "schema_version": "solar.physical_plan_node.v1",
        "node_id": "S1",
        "selected_operator_id": "mini-codex-builder",
        "execution_candidates": [
            {"operator_id": "mini-codex-builder", "host_type": "codex_worktree"},
            {"operator_id": "mini-codex-evaluator", "host_type": "codex_worktree"},
        ],
    }

    paths = apo.materialize_execution_plan_artifacts(
        "sprint-relabel",
        "S1",
        capsule_plan={"schema_version": "solar.capsule_plan_node.v1", "node_id": "S1"},
        physical_plan=physical_plan,
        base_dir=tmp_path / "sprints",
    )
    written = json.loads(Path(paths["physical_plan_ir_path"]).read_text(encoding="utf-8"))

    assert "selected_operator_id" not in written
    assert written["suggested_operator_id"] == "mini-codex-builder"
    assert written["host_type"] == "codex_worktree"


def test_tools_product_mode_materialized_physical_plan_relabels_operator_suggestion(tmp_path: Path, monkeypatch):
    tools_apo = _load_tools_apo()
    monkeypatch.setenv("SOLAR_PRODUCT_MODE", "1")
    physical_plan = {
        "schema_version": "solar.physical_plan_node.v1",
        "node_id": "S1",
        "selected_operator_id": "mini-codex-builder",
        "execution_candidates": [
            {"operator_id": "mini-codex-builder", "host_type": "codex_worktree"},
            {"operator_id": "mini-codex-evaluator", "host_type": "codex_worktree"},
        ],
    }

    paths = tools_apo.materialize_execution_plan_artifacts(
        "sprint-tools-relabel",
        "S1",
        capsule_plan={"schema_version": "solar.capsule_plan_node.v1", "node_id": "S1"},
        physical_plan=physical_plan,
        base_dir=tmp_path / "sprints",
    )
    written = json.loads(Path(paths["physical_plan_ir_path"]).read_text(encoding="utf-8"))

    assert "selected_operator_id" not in written
    assert written["suggested_operator_id"] == "mini-codex-builder"
    assert written["host_type"] == "codex_worktree"


def test_flag_off_materialized_physical_plan_keeps_legacy_key_bit_shape(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("SOLAR_PRODUCT_MODE", raising=False)
    physical_plan = {
        "schema_version": "solar.physical_plan_node.v1",
        "node_id": "S1",
        "selected_operator_id": "mini-codex-builder",
        "execution_candidates": [{"operator_id": "mini-codex-builder", "host_type": "codex_worktree"}],
    }

    paths = apo.materialize_execution_plan_artifacts(
        "sprint-legacy",
        "S1",
        capsule_plan={"schema_version": "solar.capsule_plan_node.v1", "node_id": "S1"},
        physical_plan=physical_plan,
        base_dir=tmp_path / "sprints",
    )
    written = json.loads(Path(paths["physical_plan_ir_path"]).read_text(encoding="utf-8"))

    assert written == physical_plan


def test_status_server_execution_plan_summary_reads_suggested_operator_id(tmp_path: Path):
    module, harness = _load_status_server(tmp_path)
    sid = "sprint-summary-suggested"
    _write_json(
        harness / "sprints" / f"{sid}.N1-physical-plan.json",
        {
            "schema_version": "solar.physical_plan_node.v1",
            "node_id": "N1",
            "suggested_operator_id": "mini-codex-builder",
            "host_type": "codex_worktree",
        },
    )

    summary = module._execution_plan_summary(sid)

    assert summary["items"][0]["selected_operator_id"] == "mini-codex-builder"
    assert "N1->mini-codex-builder" in summary["summary"]


def test_tools_status_server_execution_plan_summary_reads_suggested_operator_id(tmp_path: Path):
    module, harness = _load_tools_status_server(tmp_path)
    sid = "sprint-tools-summary-suggested"
    _write_json(
        harness / "sprints" / f"{sid}.N1-physical-plan.json",
        {
            "schema_version": "solar.physical_plan_node.v1",
            "node_id": "N1",
            "suggested_operator_id": "mini-codex-builder",
            "host_type": "codex_worktree",
        },
    )

    summary = module._execution_plan_summary(sid)

    assert summary["items"][0]["selected_operator_id"] == "mini-codex-builder"
    assert "N1->mini-codex-builder" in summary["summary"]


def test_route_proof_reads_suggested_operator_id_for_stale_diagnostic(tmp_path: Path):
    harness = tmp_path / "harness"
    sid = "sprint-route-suggested"
    _seed_route_registry(harness)
    _seed_pm_record(harness, sid, "task-builder", "codex-builder")
    _seed_result(harness, sid, "task-builder", "codex-builder")
    physical_plan = harness / "sprints" / f"{sid}.S1-physical-plan.json"
    _write_json(physical_plan, {"suggested_operator_id": "mini-claude-sonnet-builder"})
    _write_json(
        harness / "sprints" / f"{sid}.task_graph.json",
        {
            "sprint_id": sid,
            "nodes": [
                {
                    "id": "S1",
                    "artifacts": {
                        "suggested_operator_id": "mini-claude-sonnet-builder",
                        "physical_plan_ir": str(physical_plan),
                    },
                }
            ],
        },
    )

    proof = route_proof.write_route_proof(harness, sid)

    warnings = proof["diagnostics"]["attribution_warnings"]
    assert warnings
    assert warnings[0]["selected_operator_id"] == "mini-claude-sonnet-builder"
    assert "suggested_operator_id" in warnings[0]["selected_operator_source"]
