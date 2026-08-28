from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "harness"
sys.path.insert(0, str(HARNESS / "lib"))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_planner_persona_is_requirements_handoff_only() -> None:
    text = (HARNESS / "personas" / "planner.md").read_text(encoding="utf-8")
    assert "planner-requirements.md" in text
    assert "planner-handoff.md" in text
    assert "不创建、修改或验证 `task_graph.json`" in text
    assert "不检索网页" in text
    assert "不创建 `design.md`" in text
    assert "不运行 Builder 工作、测试、评估" in text


def test_planner_closeout_does_not_accept_dag_or_html(tmp_path: Path, monkeypatch) -> None:
    pm = _load("pm_dispatch_boundary", HARNESS / "tools" / "pm_dispatch.py")
    monkeypatch.setattr(pm, "SPRINTS_DIR", tmp_path)
    record = {
        "requested_role": "planner",
        "task_type": "requirements_handoff",
        "closeout_kind": "planner",
        "sprint_id": "sprint-boundary",
        "node_id": "N0",
    }
    assert pm._pm_expected_artifacts(record) == [
        tmp_path / "sprint-boundary.planner-requirements.md",
        tmp_path / "sprint-boundary.planner-handoff.md",
    ]


def test_graph_compiler_has_distinct_closeout(tmp_path: Path, monkeypatch) -> None:
    pm = _load("pm_dispatch_graph_compiler", HARNESS / "tools" / "pm_dispatch.py")
    monkeypatch.setattr(pm, "SPRINTS_DIR", tmp_path)
    record = {
        "requested_role": "builder",
        "task_type": "task_graph_compilation",
        "closeout_kind": "task_graph_compiler",
        "sprint_id": "sprint-boundary",
        "node_id": "GC0",
    }
    assert pm._pm_expected_artifacts(record) == [
        tmp_path / "sprint-boundary.design.md",
        tmp_path / "sprint-boundary.plan.md",
        tmp_path / "sprint-boundary.task_graph.json",
    ]


def test_planner_capability_injection_filters_downstream_work() -> None:
    import solar_skills

    dispatch = """
    # Solar PM Dispatch
    Closeout contract: `planner`
    Research a PDF with browser and deep research, compile a report and HTML,
    create a DAG, run evaluation, and use autoresearch.
    """
    selected = solar_skills._select_capabilities(dispatch)
    providers = {str(item.get("provider")) for item in selected}
    assert providers.issubset(solar_skills.PLANNER_CAPABILITY_ALLOWLIST)
    assert not any("DeepResearch" in provider for provider in providers)
    assert "Autoresearch" not in providers
    assert "Browser-use MCP" not in providers
    assert "MarkItDown" not in providers


def test_strict_workflow_routes_planner_handoff_to_graph_compiler(tmp_path: Path, monkeypatch) -> None:
    import workflow_guard

    monkeypatch.setattr(workflow_guard, "SPRINTS_DIR", tmp_path)
    sid = "sprint-boundary"
    (tmp_path / f"{sid}.status.json").write_text(
        json.dumps(
            {
                "id": sid,
                "status": "drafting",
                "phase": "prd_ready",
                "handoff_to": "planner",
                "planner_role_boundary_version": 2,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / f"{sid}.prd.md").write_text("# PRD\n", encoding="utf-8")
    (tmp_path / f"{sid}.planner-requirements.md").write_text("# Requirements\n", encoding="utf-8")
    (tmp_path / f"{sid}.planner-handoff.md").write_text("# Handoff\n", encoding="utf-8")

    route = workflow_guard.route(sid)
    assert route["ok"] is True
    assert route["route_role"] == "graph_compiler"
    assert route["stage"] == "requirements_ready"


def test_graph_compiler_prompt_excludes_downstream_execution(monkeypatch, tmp_path: Path) -> None:
    monitor = _load("autopilot_boundary", HARNESS / "tools" / "solar-autopilot-monitor.py")
    monkeypatch.setattr(monitor, "SPRINTS", tmp_path)
    objective = monitor.graph_compiler_objective("sprint-boundary")
    assert "planner-requirements.md" in objective
    assert "task_graph.json" in objective
    assert "不得执行任何 DAG node" in objective
    assert "不得做研究、生成 HTML/最终报告或评估" in objective
    assert monitor.role_for_handoff_finding("ready_for_graph_compiler") == "builder"


def test_intent_consumer_always_hands_requirements_to_planner() -> None:
    consumer = _load("intent_consumer_boundary", HARNESS / "lib" / "intent_consumer.py")
    objective = consumer.planner_objective_for_compiled_sprint("sprint-boundary")
    assert "planner-requirements.md" in objective
    assert "planner-handoff.md" in objective
    assert "答案必须由下游 direct-response worker 生成" in objective
    assert "Planner 必须亲自生成 direct_response" not in objective
    assert "task_graph.json" in objective
    assert "不得创建或修改" in objective


def test_unified_coordinator_has_explicit_two_stage_boundary() -> None:
    text = (HARNESS / "coordinator.sh").read_text(encoding="utf-8")
    strict_block = text[text.index("# Role-boundary v2 is deliberately two-stage:") :]
    assert "planner_handoff_artifacts_present" in strict_block
    assert "dispatch_graph_compiler_operator" in strict_block
    assert "graph_compiler_operator_state" in strict_block
    assert "ensure_direct_answer_runtime" in strict_block
    assert strict_block.index("planner_handoff_artifacts_present") < strict_block.index(
        "ensure_direct_answer_runtime"
    )
    assert "--closeout-kind task_graph_compiler" in text


def test_direct_response_worker_refuses_to_bypass_planner_handoff(tmp_path: Path) -> None:
    runtime = _load("direct_answer_boundary", HARNESS / "lib" / "direct_answer_runtime.py")
    sid = "sprint-boundary-direct"
    sprints = tmp_path / "sprints"
    sprints.mkdir()
    (sprints / f"{sid}.requirement_ir.json").write_text(
        json.dumps(
            {
                "request_type": "direct_answer",
                "planner_hints": {
                    "preferred_outcome": "direct_answer",
                    "runtime_handoff_allowed": False,
                },
            }
        ),
        encoding="utf-8",
    )
    (sprints / f"{sid}.status.json").write_text(
        json.dumps(
            {
                "id": sid,
                "status": "drafting",
                "planner_role_boundary_version": 2,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="Planner requirements handoff"):
        runtime.run_direct_answer(harness_dir=tmp_path, sprint_id=sid)


def test_graph_compiler_gate_requires_its_own_durable_result(tmp_path: Path) -> None:
    gate = _load("operator_gate_boundary", HARNESS / "lib" / "planner_operator_gate.py")
    sid = "sprint-boundary-compiler"
    task_id = f"pm-{sid}-GC0-abc123"
    inbox = tmp_path / "run" / "pm-inbox"
    inbox.mkdir(parents=True)
    (inbox / f"{task_id}.json").write_text(
        json.dumps(
            {
                "task_id": task_id,
                "sprint_id": sid,
                "node_id": "GC0",
                "requested_role": "builder",
                "closeout_kind": "task_graph_compiler",
                "status": "submitted",
            }
        ),
        encoding="utf-8",
    )

    pending = gate.operator_task_state(
        tmp_path,
        sid,
        "GC0",
        role="builder",
        closeout_kind="task_graph_compiler",
    )
    assert pending["state"] == "pending"
    assert pending["ready_for_compile"] is False

    result = tmp_path / "run" / "operator-results" / "builder-a" / task_id / "result.json"
    result.parent.mkdir(parents=True)
    result.write_text(
        json.dumps({"status": "completed", "exit_code": 0}),
        encoding="utf-8",
    )
    completed = gate.operator_task_state(
        tmp_path,
        sid,
        "GC0",
        role="builder",
        closeout_kind="task_graph_compiler",
    )
    assert completed["state"] == "completed"
    assert completed["ready_for_compile"] is True
