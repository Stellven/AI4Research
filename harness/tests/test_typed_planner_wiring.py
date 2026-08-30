from __future__ import annotations

import argparse
import importlib.util
import inspect
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


def test_elastic_planner_validates_without_optional_referencing(tmp_path):
    planner = _load("typed_elastic_planner_runtime_compat", LIB / "elastic_planner.py")
    schema = tmp_path / "minimal.schema.json"
    schema.write_text(
        json.dumps(
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "properties": {"value": {"type": "string"}},
                "required": ["value"],
                "additionalProperties": False,
            }
        ),
        encoding="utf-8",
    )

    assert planner._schema_errors({"value": "ok"}, schema) == []
    assert planner._schema_errors({"value": 7}, schema)


def test_plan_repair_may_add_fidelity_required_requirement_ownership():
    planner = _load("typed_elastic_planner_repair_ownership", LIB / "elastic_planner.py")
    previous = {
        "nodes": [
            {"node_id": "discover_literature", "requirement_ids": ["R5"]},
            {"node_id": "synthesize_report", "requirement_ids": ["R1", "R4"]},
        ]
    }
    repaired = {
        "nodes": [
            {"node_id": "discover_literature", "requirement_ids": ["R4", "R5"]},
            {"node_id": "synthesize_report", "requirement_ids": ["R1", "R4"]},
        ]
    }

    assert planner._repair_preservation_errors(previous, repaired) == []


def test_fidelity_ignores_duplicate_discovery_ownership_for_downstream_requirements(tmp_path):
    planner = _load("typed_elastic_planner_fidelity_ownership", LIB / "elastic_planner.py")

    class Reviewer:
        provider = "stub"
        model = "stub"

        def generate(self, _prompt, _schema, _work_dir):
            return {
                "checks": [
                    {"kind": "requirement_preservation", "status": "fail", "reason": "Discovery omits downstream requirements."},
                    {"kind": "smallest_sufficient_plan", "status": "pass", "reason": "Smallest plan."},
                    {"kind": "dependency_soundness", "status": "pass", "reason": "Dependencies are sound."},
                    {"kind": "no_unrequested_effects", "status": "pass", "reason": "No extra effects."},
                ],
                "errors": [
                    {
                        "code": "MISSING_DISCOVERY_REQUIREMENT_BINDINGS",
                        "path": "plan_ir.nodes[0].requirement_ids",
                        "message": "The discovery requirement bindings omit R2, R3, and R6.",
                        "repairable": True,
                        "requirement_ids": ["R2", "R3", "R6"],
                    }
                ],
                "warnings": [],
            }

    plan_ir = {
        "plan_ir_id": "plan-1",
        "generation": 0,
        "nodes": [
            {
                "node_id": "discover_literature",
                "logical_operator": "ScientificLiteratureDiscoverer",
                "requirement_ids": ["R4", "R5"],
            },
            {
                "node_id": "synthesize_report",
                "logical_operator": "ScientificReportDrafter",
                "requirement_ids": ["R1", "R2", "R3", "R6"],
            },
        ],
    }
    fidelity = planner.review_plan_fidelity(
        {"requirement_ir_id": "req-1", "requirements": []},
        {"decision": "generate"},
        plan_ir,
        {},
        Reviewer(),
        tmp_path,
    )

    assert fidelity["status"] == "pass_with_warnings"
    assert fidelity["errors"] == []
    assert fidelity["warnings"][0]["code"] == "REDUNDANT_DISCOVERY_OWNERSHIP_REQUEST_IGNORED"


def test_fidelity_keeps_missing_discovery_ownership_when_no_downstream_owner():
    planner = _load("typed_elastic_planner_fidelity_missing_scope", LIB / "elastic_planner.py")
    error = {
        "code": "MISSING_DISCOVERY_REQUIREMENT_BINDING",
        "message": "Discovery requirement binding omits R4.",
        "requirement_ids": ["R4"],
    }
    kept, ignored = planner._filter_redundant_discovery_ownership_errors(
        {
            "nodes": [
                {
                    "node_id": "discover_literature",
                    "logical_operator": "ScientificLiteratureDiscoverer",
                    "requirement_ids": [],
                },
                {
                    "node_id": "report",
                    "logical_operator": "ScientificReportDrafter",
                    "requirement_ids": ["R2"],
                },
            ]
        },
        [error],
    )

    assert kept == [error]
    assert ignored == []


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


def test_typed_planner_active_state_bypasses_legacy_prd_gate():
    coordinator = (ROOT / "coordinator.sh").read_text(encoding="utf-8")
    gate_start = coordinator.index("gate_check() {")
    missing_prd = coordinator.index('dispatch_to_pm "$sid" "gate_missing_prd"', gate_start)
    gate_prefix = coordinator[gate_start:missing_prd]

    typed_bypass = '''if typed_planner_required "$sid"; then
    # Formal RequirementIR v2 is the authority for the typed planning lane.'''
    assert typed_bypass in gate_prefix
    assert 'legacy PRD/plan gate must not demote planning_complete back to PM' in gate_prefix
    assert gate_prefix.index(typed_bypass) < gate_prefix.index('case "$st" in')


def test_completed_typed_planner_result_wakes_and_reconciles_coordinator():
    coordinator = (ROOT / "coordinator.sh").read_text(encoding="utf-8")

    assert '"$SPRINTS_DIR"/sprint-*/planning/adapter_result.json' in coordinator
    assert (
        'has a completed typed Planner result; reconciling without a '
        'status-fingerprint change'
    ) in coordinator
    assert 'typed_planner_required "$sid" && [[ -s "$(typed_planner_result_path "$sid")" ]]' in coordinator


def test_typed_scheduler_state_wakes_and_repeats_frozen_scheduler_ticks():
    coordinator = (ROOT / "coordinator.sh").read_text(encoding="utf-8")

    assert (
        '"$SPRINTS_DIR"/sprint-*/planning/runtime/'
        'sprint-*.task_graph_state.json'
    ) in coordinator
    assert 'runtime_state_sid="$(get_field "$f" "sprint_id")"' in coordinator
    assert 'admission_status_file="$SPRINTS_DIR/${runtime_state_sid}.status.json"' in coordinator
    assert 'typed_scheduler_state_requires_tick "$sid"' in coordinator
    assert 'has nonterminal typed Scheduler state; driving the next frozen SchedulerInput tick' in coordinator
    assert 'has terminal typed Scheduler state; reconciling the top-level sprint status' in coordinator
    assert 'reconcile_typed_scheduler_state "$sid"' in coordinator
    assert 'if ! reconcile_typed_scheduler_state "$sid"; then' in coordinator


def test_typed_scheduler_terminal_reconciliation_is_portable_and_authoritative():
    coordinator = (ROOT / "coordinator.sh").read_text(encoding="utf-8")
    helper_start = coordinator.index("reconcile_typed_scheduler_state() {")
    helper_end = coordinator.index("\nreconcile_typed_planner_result() {", helper_start)
    helper = coordinator[helper_start:helper_end]

    assert '"typed_scheduler_completed"' in helper
    assert '"typed_scheduler_failed"' in helper
    assert '"scheduler_state_revision"' in helper
    assert '"failed_nodes"' in helper
    assert "D:\\demo only version\\harness" not in helper
    assert "172.19.127.84" not in helper
    assert "8767" not in helper


def test_typed_scheduler_state_path_is_derived_from_adapter_result():
    coordinator = (ROOT / "coordinator.sh").read_text(encoding="utf-8")
    helper_start = coordinator.index("typed_scheduler_state_path() {")
    helper_end = coordinator.index("\ntyped_scheduler_state_requires_tick() {", helper_start)
    helper = coordinator[helper_start:helper_end]

    assert 'payload.get("runtime_projection")' in helper
    assert 'payload["scheduler_runtime_dir"]' in helper
    assert "D:\\demo only version\\harness" not in helper
    assert "172.19.127.84" not in helper
    assert "8767" not in helper


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


def test_research_registry_adapter_admits_claim_verify_with_all_routed_documents():
    adapter = _load(
        "typed_research_registry_claim_verify",
        TOOLS / "research_operator_registry_adapter.py",
    )
    runtime_binding = {
        "registry": "plugins.autosci.operators.scientific_lifecycle.registry",
        "node_id": "claim_verify",
        "implementation_operator_id": "autosci-claim-verification-physical",
    }

    expected = adapter._validated_binding(
        {
            "operator_id": "claim_verify_worker",
            "runtime_binding": runtime_binding,
        }
    )
    claims = {"schema": "research_claims.v1", "outputs": {"claims": []}}
    paper = {"schema": "research_paper.v1", "outputs": {"paper": {}}}

    payload = adapter._inline_operator_payload(expected, [claims, paper])

    assert expected["node_id"] == "claim_verify"
    assert payload == {"claims": [claims, paper]}


def test_composition_support_step_preserves_parent_plan_objective():
    planner = _load("typed_composition_parent_context", LIB / "elastic_planner.py")
    parent_objective = (
        "Discover evidence about a named technical subject.\n\n"
        "Authoritative discovery scope:\n"
        "- [R1] Cover named method families. Required coverage: method alpha; method beta"
    )
    graph = planner._generated_composition_task_graph_proposal(
        {"requirement_ir_id": "requirement-context", "requirements": []},
        {
            "nodes": [
                {
                    "node_id": "research",
                    "objective": parent_objective,
                    "logical_operator": "ScientificLiteratureDiscoverer",
                    "depends_on": [],
                    "consumes": ["schema:request-envelope.schema.json"],
                    "produces": [
                        {
                            "artifact_type": "schema:paper.v1",
                            "materialization": {"kind": "file", "path": "paper.json"},
                            "verifier_ids": [],
                        }
                    ],
                    "requirement_ids": ["R1"],
                    "operator_requirements": {},
                }
            ]
        },
        {
            "nodes": [
                {
                    "node_id": "research",
                    "search": {
                        "candidates": [
                            {
                                "candidate_id": "composition-1",
                                "steps": [
                                    {
                                        "capsule_id": "cap.discover",
                                        "consumes": ["schema:request-envelope.schema.json"],
                                        "produces": ["schema:shortlist.v1"],
                                    },
                                    {
                                        "capsule_id": "cap.ingest",
                                        "consumes": ["schema:shortlist.v1"],
                                        "produces": ["schema:paper.v1"],
                                    },
                                ],
                            }
                        ]
                    },
                }
            ]
        },
        {
            "nodes": [
                {
                    "node_id": "research",
                    "selected_candidate_id": "composition-1",
                    "rationale": "typed chain",
                    "step_bindings": [
                        {"dispatch_task_type": "literature-discovery"},
                        {"dispatch_task_type": "paper-ingest"},
                    ],
                }
            ]
        },
        {
            "capsules": [
                {"capsule_id": "cap.discover", "description": "Discover a shortlist."},
                {"capsule_id": "cap.ingest", "description": "Normalize papers."},
            ]
        },
        sprint_id="sprint-context",
    )

    support, terminal = graph["nodes"]
    assert support["goal"].startswith("Discover a shortlist.")
    assert "Composition parent objective:" in support["goal"]
    assert parent_objective in support["goal"]
    assert terminal["goal"] == parent_objective


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


def test_rapid_smoke_budget_blocks_semantic_evaluators_but_keeps_hard_gates():
    import evaluation_budget

    graph = {
        "nodes": [
            {"id": "build", "logical_operator": "ImplementationWorker", "depends_on": [], "evaluator_gate": {"kind": "llm_eval"}},
            {"id": "verify", "logical_operator": "Verifier", "depends_on": ["build"], "evaluator_gate": {"kind": "llm_eval"}},
            {"id": "hard-check", "logical_operator": "TestRunner", "depends_on": ["build"], "evaluator_gate": {"kind": "deterministic_command", "command": "python -m pytest -q"}},
        ]
    }
    policy = {"mode": "rapid_smoke", "semantic_evaluation_budget": 0, "deterministic_gates_required": True}

    bounded = evaluation_budget.apply_evaluation_budget(graph, {}, test_policy=policy)

    by_id = {node["id"]: node for node in bounded["nodes"]}
    assert bounded["evaluation_policy"]["semantic_evaluation_budget"] == 0
    assert bounded["test_policy"] == policy
    assert by_id["build"]["evaluator_gate"] == {"kind": "none", "on_fail": "fail", "test_policy_mode": "rapid_smoke"}
    assert by_id["verify"]["evaluator_gate"]["kind"] == "none"
    assert by_id["hard-check"]["evaluator_gate"]["kind"] == "deterministic_command"


def test_adapter_injects_rapid_smoke_only_from_trusted_environment(tmp_path, monkeypatch):
    adapter = _load("rapid_adapter_test", TOOLS / "elastic_planner_adapter.py")
    requirement = tmp_path / "requirement_ir.json"
    requirement.write_text(json.dumps({"schema_version": "solar.requirement_ir.v2"}), encoding="utf-8")
    captured = {}

    def planning_stub(*_args, **kwargs):
        captured.update(kwargs)
        return {"status": "direct_response", "verification_errors": []}

    monkeypatch.setenv("SOLAR_TEST_MODE", "rapid_smoke")
    monkeypatch.setattr(adapter, "run_elastic_planning_request", planning_stub)

    result = adapter.run_adapter(
        requirement_ir_path=requirement,
        output_root=tmp_path / "planning",
        sprint_id="sprint-rapid",
        workspace_root="workspace",
        planner_model=object(),
        reviewer_model=object(),
    )

    assert captured["test_policy"] == result["test_policy"]
    assert result["test_policy"]["mode"] == "rapid_smoke"
    assert result["test_policy"]["semantic_evaluation_budget"] == 0


def test_rapid_smoke_none_gate_records_explicit_bypass_provenance(tmp_path):
    import contract_gate_executor

    result = contract_gate_executor.execute_gate(
        tmp_path,
        "sprint-rapid",
        {"id": "build", "repair_attempts": 0},
        {"kind": "none", "test_policy_mode": "rapid_smoke"},
        harness_dir=ROOT,
    )
    payload = json.loads(Path(result["eval_json"]).read_text(encoding="utf-8"))

    assert result["ok"] is True
    assert payload["generation_mode"] == "rapid_smoke_bypass"
    assert payload["duration_seconds"] == 0.0


def test_composition_fit_preserves_explicit_unresolved_alternative():
    planner = _load("typed_composition_fit_unresolved", LIB / "elastic_planner.py")
    source = inspect.getsource(planner.review_composition_fit)

    assert "reporting it as unresolved" in source
    assert "do not require an unregistered" in source
    assert "claims resolution without the necessary operation" in source
