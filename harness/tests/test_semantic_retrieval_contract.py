"""Offline boundary tests: no provider calls, status mutations, or old sessions."""
from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
sys.path.insert(0, str(ROOT))
from requirement_compiler import compile_requirement_ir, evaluate_requirement_ir_format
from requirement_compiler.semantic import semantic_defects, RequirementCompilationError
from plugins.autosci.services.retrieval_contract import filter_candidates
import elastic_planner
import scheduler_input


def retrieval(subject="marine heatwaves"):
    return {"contract_id": "retrieval-1", "subject": subject,
            "search_queries": [subject], "source_refs": ["G1", "C1"],
            "inclusion_criteria": [{"field": "title_abstract", "any_of": [subject], "source_refs": ["C1"]}],
            "exclusion_criteria": [{"field": "title_abstract", "any_of": ["review", "survey"], "source_refs": ["C3"]}],
            "coverage": [{"label": subject, "any_of": [subject], "required": True}],
            "time_range": {"start_year": None, "end_year": None}, "minimum_candidates": 1}


def intent():
    return {"intent_ir_id": "intent-ir-test", "raw_intent_ref": {"raw_intent_id": "test"},
            "goals": [{"goal_id": "G1", "statement": "Research marine heatwaves"}],
            "outcomes": [{"outcome_id": "D1", "class": "artifact", "description": "A research report"}],
            "constraints": [
                {"constraint_id": "C1", "category": "scope", "statement": "Study marine heatwaves", "expression": {"op": "equals", "args": [{"ref": "topic"}, {"literal": "marine heatwaves"}]}},
                {"constraint_id": "C2", "category": "preference", "statement": "Research workflow rather than a one-off answer", "expression": {"op": "not_equals", "args": [{"ref": "mode"}, {"literal": "one-off answer"}]}},
                {"constraint_id": "C3", "category": "scope", "statement": "Exclude review papers", "expression": {"op": "not_equals", "args": [{"ref": "publication_type"}, {"literal": "review"}]}}],
            "ambiguities": [], "unknowns": [], "conflicts": []}


def body():
    rows = []
    for index, (refs, role, kind, values, priority) in enumerate([
        (["G1", "D1"], "outcome", "artifact_fields", ["deliverable", "supporting_evidence"], "must"),
        (["C1"], "research_scope", "scope_coverage", ["marine heatwaves"], "must"),
        (["C2"], "process", "process", ["Use a research workflow, not a one-off answer"], "should"),
        (["C3"], "research_scope", "constraint", ["Exclude reviews"], "must"),
    ], 1):
        rows.append({"requirement_id": f"R{index}", "origin": "user:" + refs[0], "statement": values[0],
                     "priority": priority, "source_refs": refs, "acceptance": {"kind": kind, "required_values": values},
                     "check": "check.artifact_outcome_completeness.v1" if index == 1 else "check.intent_constraint_coverage.v1",
                     "checkable": True, "disposition": None, "semantic_role": role})
    authority = [{"field_path": path, "basis": "explicit_source_selection", "source_refs": [ref],
                  "justification": "Fixture explicitly requests this source selection."} for path, ref in (
        ("/discovery/inclusion_criteria/0", "C1"), ("/discovery/exclusion_criteria/0", "C3"),
        ("/discovery/coverage/0/required", "C1"))]
    return {"requirements": rows, "assumptions": [], "discovery": retrieval(), "selection_authority": authority}


class Model:
    provider = "offline-fixture"
    model = "no-network"

    def __init__(self, value):
        self.value, self.calls = value, []

    def generate(self, prompt, schema_path, work_dir):
        self.calls.append((prompt, schema_path, work_dir))
        return copy.deepcopy(self.value)


def compiled(tmp_path):
    return compile_requirement_ir(intent(), intent_ir_sha256="a" * 64, work_dir=tmp_path,
                                  model=Model(body()), reviewer=Model({"accepted": True, "errors": []}))


def test_requirement_provider_schema_preserves_typed_true_constraint(tmp_path, monkeypatch):
    """Exercise the real schema projection/CLI boundary without a provider call."""
    import subprocess
    from jsonschema import Draft202012Validator
    from intent_compiler import CodexJsonModel, write_json
    from requirement_compiler.semantic import BODY_SCHEMA

    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        schema_path = Path(command[command.index("--output-schema") + 1])
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        checkable = schema["properties"]["requirements"]["items"]["properties"]["checkable"]
        assert checkable == {"type": "boolean", "const": True}
        validator = Draft202012Validator(checkable)
        assert validator.is_valid(True)
        assert all(not validator.is_valid(value) for value in (False, 1, "true", None))
        assert Path(kwargs["cwd"]) == schema_path.parent
        output_path = Path(command[command.index("--output-last-message") + 1])
        write_json(output_path, body())
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = CodexJsonModel(model="offline-fixture").generate(
        "Compile source-linked requirements", BODY_SCHEMA, tmp_path / "compile"
    )
    assert len(calls) == 1
    assert result == body()
    assert (tmp_path / "compile/model_call_receipt.json").is_file()


def test_llm_compilation_preserves_polarity_category_strength(tmp_path):
    ir = compiled(tmp_path)
    assert ir["semantic_contract"]["source_constraints"] == intent()["constraints"]
    assert ir["requirements"][2]["priority"] == "should"
    assert ir["requirements"][2]["acceptance"]["kind"] == "process"
    assert "one-off" not in json.dumps(ir["semantic_contract"]["discovery"])
    assert evaluate_requirement_ir_format(ir, intent_ir=intent(), intent_ir_sha256="a" * 64)["status"] == "pass"


def test_no_silent_deterministic_fallback():
    with pytest.raises(RequirementCompilationError, match="work_dir"):
        compile_requirement_ir(intent(), intent_ir_sha256="a" * 64)


def test_semantic_reviewer_failure_is_bounded_and_fail_closed(tmp_path):
    model, reviewer = Model(body()), Model({"accepted": False, "errors": [{
        "rule_id": "F02", "field_path": "/requirements/2/priority", "evidence_refs": ["C2"],
        "reason": "POLARITY_WRONG"}]})
    with pytest.raises(RequirementCompilationError, match="POLARITY_WRONG"):
        compile_requirement_ir(intent(), intent_ir_sha256="a" * 64, work_dir=tmp_path, model=model, reviewer=reviewer)
    assert len(model.calls) == len(reviewer.calls) == 2
    assert "POLARITY_WRONG" in model.calls[1][0]


def test_source_ast_tamper_is_rejected(tmp_path):
    ir = compiled(tmp_path)
    ir["semantic_contract"]["source_constraints"][1]["expression"]["op"] = "equals"
    assert "SOURCE_CONSTRAINT_POLARITY_OR_CATEGORY_CHANGED" in semantic_defects(ir, intent())


def test_missing_source_and_misclassified_scope_rejected(tmp_path):
    ir = compiled(tmp_path)
    ir["requirements"][2]["acceptance"]["kind"] = "scope_coverage"
    ir["requirements"][0]["source_refs"] = ["D1"]
    errors = semantic_defects(ir, intent())
    assert any("SOURCE_COVERAGE_MISMATCH" in row for row in errors)
    assert "NON_SCOPE_REQUIREMENT_MARKED_AS_RETRIEVAL_COVERAGE" in errors


@pytest.mark.parametrize("subject", ["marine heatwaves", "KV cache", "电池回收"])
def test_structured_selection_positive_negative_and_other_domains(subject):
    rows, audit = filter_candidates(retrieval(subject), [
        {"title": subject + " measured study", "year": 2024},
        {"title": subject + " review", "year": 2024},
        {"title": "irrelevant project workflow auditable answer"}])
    assert len(rows) == 1
    assert audit["status"] == "passed"
    assert "explicit_exclusion" in audit["decisions"][1]["reasons"][0]


def test_unknown_and_out_of_range_dates_fail_closed():
    contract = retrieval()
    contract["time_range"] = {"start_year": 2020, "end_year": 2025}
    rows, audit = filter_candidates(contract, [{"title": "marine heatwaves"}, {"title": "marine heatwaves", "year": 2010}])
    assert rows == [] and audit["status"] == "failed"


def test_scheduler_schema_embeds_exact_retrieval_shape():
    expected = json.loads((ROOT / "schemas/compiler/retrieval-contract.v1.schema.json").read_text())
    expected.pop("$id")
    expected.pop("$schema")
    actual = json.loads(scheduler_input.SCHEMA_PATH.read_text())
    assert actual["$defs"]["node"]["properties"]["retrieval_contract"] == expected


def test_planner_binding_preserves_model_text_and_contract(tmp_path):
    ir = compiled(tmp_path)
    graph = {"nodes": [{"id": "D", "goal": "Do discovery; don't write the report", "logical_operator": "ScientificLiteratureDiscoverer"}]}
    plan = {"nodes": [{"node_id": "D", "retrieval_contract_ref": "retrieval-1"}]}
    elastic_planner._bind_retrieval_contracts(graph, ir, plan)
    assert graph["nodes"][0]["goal"] == "Do discovery; don't write the report"
    assert graph["nodes"][0]["retrieval_contract"] == ir["semantic_contract"]["discovery"]
    plan["nodes"][0]["retrieval_contract_ref"] = "wrong"
    with pytest.raises(elastic_planner.ElasticPlannerError):
        elastic_planner._bind_retrieval_contracts(graph, ir, plan)


@pytest.mark.parametrize("objective", ["Not a one-off answer; write an auditable report", "进行研究流程，而不是直接回答"])
def test_bridge_ignores_process_paraphrases(objective):
    from plugins.autosci.adapters.solar_envelope_to_autosci import normalize_envelope
    envelope = normalize_envelope({"objective": objective, "retrieval_contract": retrieval(),
                                   "inputs": {"topic": "untrusted override"}}, action="discover_literature")
    assert envelope["inputs"]["topic"] == "marine heatwaves"
    assert envelope["inputs"]["query"] == "marine heatwaves"


def load_bridge():
    sys.path.insert(0, str(ROOT / "plugins/autosci/bin"))
    spec = importlib.util.spec_from_file_location("semantic_bridge_test", ROOT / "plugins/autosci/bin/autosci_bridge.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_rapid_empty_shortlist_cannot_handoff(tmp_path, monkeypatch):
    bridge = load_bridge()
    monkeypatch.setattr(bridge, "_output_dir", lambda *_args: tmp_path)
    envelope = {"inputs": {"retrieval_contract": retrieval()}, "test_policy": {"mode": "rapid_smoke"}}
    with pytest.raises(ValueError, match="DISCOVERY_HANDOFF_REJECTED"):
        bridge._attach_discover_final_shortlist_boundary(envelope, {"candidates": [], "status": "completed"}, mode="structured_retrieval")
    audit = json.loads((tmp_path / "discover_final_shortlist_boundary.json").read_text())
    assert audit["final_shortlist_ready"] is False


def test_no_workflow_prose_coverage_gate(tmp_path):
    bridge = load_bridge()
    envelope = {"objective": "Authoritative discovery scope: one-off answer; end-to-end", "inputs": {"retrieval_contract": retrieval()}}
    audit = bridge._discover_requested_coverage_audit(envelope, {"relevance_gate": {"status": "passed"}}, [{"title": "marine heatwaves"}])
    assert audit["coverage_ready"] is True and audit["declared_scope"] is False


def test_provider_uses_structured_contract_not_legacy_prose(tmp_path, monkeypatch):
    from plugins.autosci.services import production_research as production
    service = production.LiteratureDiscoveryService(workspace_root=tmp_path, limit=2)
    def rows(provider):
        return [{"source_id": provider, "canonical_id": provider, "title": "marine heatwaves measured study",
                 "provider": provider, "url": "https://example.invalid/" + provider, "metadata": {"year": 2024}}]
    monkeypatch.setattr(service, "_semantic_scholar", lambda query: (rows("semantic_scholar"), {"provider": "semantic_scholar"}, []))
    monkeypatch.setattr(service, "_arxiv", lambda query: (rows("arxiv"), {"provider": "arxiv"}))
    def forbidden(*_args, **_kwargs):
        raise AssertionError("legacy prose inference was used")
    monkeypatch.setattr(production, "_topic_from_snapshot", forbidden)
    monkeypatch.setattr(production, "apply_discovery_relevance_gate", forbidden)
    result = service(seed_snapshot={"seeds": []}, payload={"task_contract": {
        "user_intent": "not one-off; Authoritative discovery scope: end-to-end process",
        "retrieval_contract": retrieval()}})
    assert result["status"] == "completed"
    assert result["query"] == "marine heatwaves"
    assert result["relevance_gate"]["contract_id"] == "retrieval-1"


def test_frozen_projection_transports_and_detects_contract_tampering(tmp_path):
    path = ROOT / "metadata/5-taskgraph compiler and validator output/scheduler_input/scheduler_input.json"
    value = json.loads(path.read_text())
    value["artifact_role"] = "runtime_execution_authority"
    value["graph"]["nodes"][0]["retrieval_contract"] = retrieval()
    external = tmp_path / "input.json"
    external.write_text("{}")
    source = tmp_path / "scheduler_input.json"
    source.write_text(json.dumps(value))
    graph_path = scheduler_input.prepare_runtime_graph(source, tmp_path / "runtime",
                                                       artifact_bindings={"artifact.request.v1": str(external)})
    graph = json.loads(graph_path.read_text())
    assert graph["nodes"][0]["retrieval_contract"] == retrieval()
    assert scheduler_input.verify_runtime_projection(graph, graph_path=graph_path)["ok"]
    graph["nodes"][0]["retrieval_contract"]["subject"] = "tampered workflow text"
    assert not scheduler_input.verify_runtime_projection(graph, graph_path=graph_path)["ok"]


def test_intake_deadline_covers_both_compilers():
    import ast
    source = ast.parse((ROOT / "lib/symphony/status-server.py").read_text())
    selected = [node for node in source.body if
                isinstance(node, ast.FunctionDef) and node.name == "_intake_timeout_seconds" or
                isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id in
                    {"_MAX_INTENT_MODEL_CALLS", "_MAX_REQUIREMENT_MODEL_CALLS"} for target in node.targets)]
    scope = {}
    exec(compile(ast.Module(body=selected, type_ignores=[]), "intake_timeout", "exec"), scope)
    timeout = scope["_intake_timeout_seconds"]
    assert timeout({}) == 4 * 180 + 4 * 240 + 60
    assert timeout({"SOLAR_INTAKE_TIMEOUT_SEC": "100"}) == 100
    assert timeout({"SOLAR_INTAKE_COMPAT_MODE": "legacy"}) == 180
