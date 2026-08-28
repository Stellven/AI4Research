from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "lib"
TOOLS = ROOT / "tools"
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _capture_args() -> argparse.Namespace:
    return argparse.Namespace(
        text="Research current battery technology and produce a report.",
        file="",
        stdin=False,
        intent_id="intent-typed-test",
        source_channel="dashboard",
        actor="user",
        device="",
        session_id="",
        thread_ref="",
        repo="",
        knowledge_query="",
        urgency="normal",
        mode="",
        source_trust="user_direct",
        no_autodispatch=False,
        requires_human_confirm=False,
        clarification_answer=[],
        require_research_artifact=False,
        research_artifact="",
        research_project_name="",
        research_conversation_id="",
        research_source_url="",
        sprint_id="",
        json=True,
    )


def test_formal_gateway_never_calls_deterministic_semantic_router(tmp_path, monkeypatch):
    gateway = _load("typed_gateway_test", LIB / "intent_gateway.py")
    gateway.INTENTS_DIR = tmp_path / "intents"

    def forbidden(*_args, **_kwargs):
        raise AssertionError("production formal path called deterministic semantics")

    monkeypatch.setattr(gateway, "infer_mode", forbidden)
    monkeypatch.setattr(gateway, "deterministic_rewrite", forbidden)
    import intent_compiler

    monkeypatch.setattr(intent_compiler, "model_from_environment", lambda _role: object())
    monkeypatch.setattr(
        intent_compiler,
        "run_pipeline",
        lambda *_args, **_kwargs: {
            "intent_ir": {
                "intent_ir_id": "intent-ir-typed-test",
                "goals": [{"statement": "Produce the requested report."}],
            },
            "intent_acceptance": {
                "decision": "accepted",
                "repair": {"attempted": False},
                "clarification_questions": [],
            },
            "intent_validation": {"status": "pass"},
            "intent_fidelity": {"status": "pass"},
        },
    )
    monkeypatch.setattr(
        gateway,
        "compile_and_evaluate_requirement_bundle",
        lambda *_args: (
            {
                "schema_version": "solar.requirement_ir.v2",
                "requirement_ir_id": "requirement-ir-typed-test",
            },
            {"status": "pass", "defects": []},
        ),
    )

    result = gateway.capture(_capture_args())

    raw = json.loads(
        (gateway.INTENTS_DIR / "intent-typed-test" / "raw_intent.json").read_text()
    )
    assert result["ready"] is True
    assert result["lane"] is None
    assert raw["routing_hints"]["mode"] == ""
    assert gateway._llm_intent_compiler_required("codex_pm_router") is True


def test_formal_consumer_dry_run_targets_typed_adapter(tmp_path):
    consumer = _load("typed_consumer_test", LIB / "intent_consumer.py")
    consumer.INTENTS_DIR = tmp_path / "intents"
    consumer.SPRINTS_DIR = tmp_path / "sprints"
    consumer.HARNESS_DIR = ROOT
    base = consumer.INTENTS_DIR / "intent-formal"
    (base / "intent").mkdir(parents=True)
    consumer.write_json(
        base / "raw_intent.json",
        {
            "intent_id": "intent-formal",
            "raw": {"text": "Produce a deep analysis."},
            "source": {"channel": "dashboard"},
            "routing_hints": {"allow_autodispatch": True},
            "trust": {"source_trust": "user_direct"},
        },
    )
    consumer.write_json(
        base / "intent" / "intent_ir.json",
        {
            "intent_ir_id": "intent-ir-formal",
            "goals": [{"statement": "Produce a deep analysis."}],
            "constraints": [],
        },
    )
    consumer.write_json(
        base / "requirement_ir.json",
        {
            "schema_version": "solar.requirement_ir.v2",
            "requirement_ir_id": "requirement-ir-formal",
            "intent_ir_ref": {"intent_ir_id": "intent-ir-formal"},
            "requirements": [],
        },
    )

    result = consumer.consume_one(
        "intent-formal", dry_run=True, dispatch_planner=True
    )

    command = result["planner_handoff"]["cmd"]
    assert result["planner_handoff"]["mode"] == "elastic_planner"
    assert Path(command[1]).name == "elastic_planner_adapter.py"
    assert "compile-request" not in command


def test_adapter_authorizes_only_verified_scheduler_projection(tmp_path, monkeypatch):
    adapter = _load("typed_adapter_test", TOOLS / "elastic_planner_adapter.py")
    requirement = tmp_path / "requirement_ir.json"
    requirement.write_text(
        json.dumps({"schema_version": "solar.requirement_ir.v2"}), encoding="utf-8"
    )
    output_root = tmp_path / "planning"
    execution = output_root / "execution"
    execution.mkdir(parents=True)
    (execution / "scheduler_input.json").write_text("{}", encoding="utf-8")
    (execution / "run_contract.frozen.json").write_text("{}", encoding="utf-8")
    (execution / "plan_acceptance.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        adapter,
        "run_elastic_planning_request",
        lambda *_args, **_kwargs: {
            "status": "accepted",
            "verification_errors": [],
        },
    )

    def prepare(_scheduler_input, runtime_dir, *, run_contract_path):
        runtime_dir.mkdir(parents=True)
        path = runtime_dir / "sprint-typed.task_graph.json"
        path.write_text('{"schema_version":"solar.scheduler_runtime_projection.v1"}')
        assert run_contract_path == execution / "run_contract.frozen.json"
        return path

    monkeypatch.setattr(adapter, "prepare_runtime_graph", prepare)
    monkeypatch.setattr(adapter, "verify_runtime_projection", lambda *_args, **_kwargs: {"ok": True})

    result = adapter.run_adapter(
        requirement_ir_path=requirement,
        output_root=output_root,
        sprint_id="sprint-typed",
        workspace_root="workspace",
        planner_model=object(),
        reviewer_model=object(),
    )

    assert result["status"] == "accepted"
    assert result["runtime_handoff_allowed"] is True
    assert result["scheduler_input"].endswith("scheduler_input.json")
    assert result["runtime_projection"].endswith("sprint-typed.task_graph.json")


def test_legacy_task_graph_schema_violation_is_fail_closed():
    import plan_validator

    graph = {
        "sprint_id": "sprint-invalid-cost",
        "nodes": [
            {
                "id": "N1",
                "goal": "Do work",
                "depends_on": [],
                "acceptance": ["done"],
                "priority": "P1",
                "required_phase": "planning_complete",
                "required_node_id": "N1",
                "required_node_status": "ready",
                "estimated_cost": {"max_calls": 10},
            }
        ],
    }

    errors = plan_validator.validate_task_graph_schema(graph)

    assert errors
    assert {error["code"] for error in errors} == {"PLAN_SCHEMA_INVALID"}
    assert plan_validator.check_planner_graph_dispatchable(graph)["ok"] is False
