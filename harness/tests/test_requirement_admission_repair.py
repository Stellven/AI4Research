"""Final admission regression: frozen identities, provenance and bounded repair."""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("final_requirement_fixtures", Path(__file__).with_name("test_semantic_retrieval_contract.py"))
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)
Model, body, intent = fixtures.Model, fixtures.body, fixtures.intent
from evaluation_plan import load_evaluation_check_registry
from requirement_compiler import compile_requirement_ir
from requirement_compiler.compiler import RequirementCompilationError
from requirement_compiler.template_contract import make_template, fill_template, selection_authority_defects, review_defects


def rejection(reason="Unsupported source filter"):
    return {"accepted": False, "errors": [{"rule_id": "F04", "field_path": "/discovery/inclusion_criteria",
        "evidence_refs": ["C1"], "reason": reason}]}


class Sequence(Model):
    def generate(self, prompt, schema_path, work_dir):
        index = len(self.calls)
        self.calls.append((prompt, schema_path, work_dir))
        return copy.deepcopy(self.value[index])


def test_provider_gets_same_instantiated_schema_as_validator(tmp_path, monkeypatch):
    import subprocess
    from intent_compiler import CodexJsonModel, write_json
    from jsonschema import Draft202012Validator
    observed = []

    def run(command, **kwargs):
        schema = json.loads(Path(command[command.index("--output-schema") + 1]).read_text())
        check = schema["properties"]["requirements"]["items"]["properties"]["check"]
        assert "check.claim_evidence_resolved" in check["enum"]
        assert not Draft202012Validator(check).is_valid("check.claim_evidence_resolved.v1")
        observed.append(schema)
        write_json(Path(command[command.index("--output-last-message") + 1]), body())
        return subprocess.CompletedProcess(command, 0, '{"type":"turn.completed"}\n', "")

    monkeypatch.setattr(subprocess, "run", run)
    compile_requirement_ir(intent(), intent_ir_sha256="a"*64, work_dir=tmp_path,
        model=CodexJsonModel(model="offline-fixture"), reviewer=Model({"accepted": True, "errors": []}))
    template = json.loads((tmp_path / "template.json").read_text())
    assert len(observed) == 1
    assert json.loads((tmp_path / "compiler-output.schema.json").read_text()) == template["read_only"]["compiler_output_schema"]


@pytest.mark.parametrize("field,value", [("check", "check.claim_evidence_resolved.v1"), ("source_refs", ["NOT_AN_INTENT_ID"])])
def test_frozen_id_enums_reject_invented_identifiers(field, value):
    template = make_template(intent(), load_evaluation_check_registry())
    candidate = body()
    candidate["requirements"][0][field] = value
    with pytest.raises(ValueError, match="REQUIREMENT_VALUES_INVALID"):
        fill_template(template, candidate)


def test_structure_gets_one_repair_and_semantic_review_is_advisory(tmp_path):
    invalid = body()
    invalid["requirements"][0]["check"] = "check.claim_evidence_resolved.v1"
    model = Sequence([invalid, body(), body()])
    reviewer = Sequence([rejection(), {"accepted": True, "errors": []}])
    ir = compile_requirement_ir(intent(), intent_ir_sha256="a"*64, work_dir=tmp_path, model=model, reviewer=reviewer)
    assert len(model.calls) == 2 and len(reviewer.calls) == 1
    assert ir["semantic_contract"]["runtime_policies"]["evidence_honesty"]["origin"] == "runtime_validity_policy"
    validation = json.loads((tmp_path / "generation-1/validation.json").read_text())
    assert validation["accepted"] is True
    assert any("Unsupported source filter" in row for row in validation["warnings"])
    assert validation["model_calls"] == 3


def test_semantic_review_does_not_start_another_compiler_generation(tmp_path):
    invalid = body()
    invalid["requirements"][0]["check"] = "unknown"
    model = Sequence([body(), invalid, body()])
    reviewer = Sequence([rejection(), rejection("still unsupported")])
    ir = compile_requirement_ir(
        intent(), intent_ir_sha256="a" * 64, work_dir=tmp_path, model=model, reviewer=reviewer
    )
    assert ir["requirements"]
    assert len(model.calls) == 1 and len(reviewer.calls) == 1
    validation = json.loads((tmp_path / "generation-0/validation.json").read_text())
    assert validation["accepted"] is True
    assert any("Unsupported source filter" in row for row in validation["warnings"])


def test_deadline_exhaustion_does_not_call_another_model(tmp_path, monkeypatch):
    import requirement_compiler.semantic as semantic
    clock = iter([0, 1000])
    monkeypatch.setattr(semantic.time, "monotonic", lambda: next(clock))
    model = Model(body())
    with pytest.raises(RequirementCompilationError, match="BUDGET_EXHAUSTED"):
        compile_requirement_ir(intent(), intent_ir_sha256="a"*64, work_dir=tmp_path, model=model, reviewer=model)
    assert model.calls == []


def test_report_scope_can_be_mandatory_without_hard_source_filters():
    candidate = body()
    original = copy.deepcopy(candidate["requirements"])
    candidate["discovery"]["inclusion_criteria"] = []
    candidate["discovery"]["exclusion_criteria"] = []
    candidate["discovery"]["coverage"][0]["required"] = False
    candidate["selection_authority"] = []
    assert selection_authority_defects(candidate) == []
    assert candidate["requirements"] == original
    candidate["discovery"]["coverage"][0]["required"] = True
    assert "SELECTION_AUTHORITY_TARGET_MISMATCH" in selection_authority_defects(candidate)[0]


def test_explicit_filter_authority_preserved_but_not_semantically_auto_approved():
    candidate = body()
    assert selection_authority_defects(candidate) == []
    template = make_template(intent(), load_evaluation_check_registry())
    assert review_defects(template, rejection(), candidate)
    candidate["selection_authority"][0]["source_refs"] = ["D1"]
    assert any("SOURCE_MISMATCH" in e for e in selection_authority_defects(candidate))


@pytest.mark.parametrize("mutate", ["unknown_rule", "unknown_evidence", "missing_path", "contradiction"])
def test_review_requires_real_rule_evidence_and_target(mutate):
    template = make_template(intent(), load_evaluation_check_registry())
    verdict = rejection()
    if mutate == "unknown_rule": verdict["errors"][0]["rule_id"] = "F999"
    if mutate == "unknown_evidence": verdict["errors"][0]["evidence_refs"] = ["invented"]
    if mutate == "missing_path": verdict["errors"][0]["field_path"] = "/missing/field"
    if mutate == "contradiction": verdict["accepted"] = True
    defects = review_defects(template, verdict, body())
    assert any(e.startswith(("REVIEW_SCHEMA_INVALID", "REVIEW_FIELD_NOT_FOUND", "REVIEW_VERDICT_INCONSISTENT")) for e in defects)


def test_historical_semantic_contract_remains_readable(tmp_path):
    ir = compile_requirement_ir(intent(), intent_ir_sha256="a"*64, work_dir=tmp_path,
        model=Model(body()), reviewer=Model({"accepted": True, "errors": []}))
    for key in ("selection_authority", "runtime_policies", "template_ref"):
        ir["semantic_contract"].pop(key)
    assert fixtures.semantic_defects(ir, intent()) == []
