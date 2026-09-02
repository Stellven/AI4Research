"""Template ownership and shared semantics; no live providers or runtime sessions."""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "requirement_test_fixtures", Path(__file__).with_name("test_semantic_retrieval_contract.py")
)
_fixtures = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_fixtures)
Model, body, intent = _fixtures.Model, _fixtures.body, _fixtures.intent
from evaluation_plan import load_evaluation_check_registry
from requirement_compiler import compile_requirement_ir
from requirement_compiler.compiler import RequirementCompilationError
from requirement_compiler.template_contract import fill_template, make_template


def payload(call):
    return json.loads(call[0].split("\n", 1)[1])


def test_compiler_and_reviewer_receive_identical_program_owned_contract(tmp_path):
    model = Model(body())
    reviewer = Model({"accepted": True, "errors": []})
    ir = compile_requirement_ir(intent(), intent_ir_sha256="a" * 64, work_dir=tmp_path,
                                model=model, reviewer=reviewer)
    blank = payload(model.calls[0])["template"]
    filled = payload(reviewer.calls[0])["filled_template"]
    assert blank["read_only"] == filled["read_only"]
    assert blank["contract_ref"] == filled["contract_ref"]
    assert blank["values"] == {
        "requirements": [],
        "assumptions": [],
        "discovery": None,
        "selection_authority": [],
        "delivery_manifest": None,
    }
    assert filled["values"] == body()
    fixed = filled["read_only"]
    assert fixed["source_constraints"] == intent()["constraints"]
    assert fixed["evaluation_check_registry"] == load_evaluation_check_registry()
    policy = fixed["contract"]["policies"]["discovery_nonempty_handoff"]
    assert blank["contract_ref"]["version"] == 3
    assert policy["default"] == 1 and policy["origin"] == "runtime_validity_policy"
    assert "not an invented user count" in policy["review"]
    assert "never requires candidates to exist before Requirement or Planner admission" in policy["override"]
    assert "final corpus or report requirement" in policy["review"]
    assert fixed["item_templates"]["discovery"]["minimum_candidates"] == 1
    assert fixed["item_templates"]["requirements"]["checkable"] is True
    assert fixed["item_templates"]["delivery_manifest_file"]["required"] is True
    assert ir["semantic_contract"]["source_constraints"] == fixed["source_constraints"]
    assert json.loads((tmp_path / "generation-0/filled_template.json").read_text()) == filled
    verdict = json.loads((tmp_path / "generation-0/validation.json").read_text())
    assert verdict["contract_ref"] == blank["contract_ref"]


@pytest.mark.parametrize("protected", ["read_only", "contract_ref", "description", "policies"])
def test_model_cannot_return_protected_template_fields(tmp_path, protected):
    candidate = body()
    candidate[protected] = {"default": 0}
    reviewer = Model({"accepted": True, "errors": []})
    model = Model(candidate)
    with pytest.raises(RequirementCompilationError, match="REQUIREMENT_VALUES_INVALID"):
        compile_requirement_ir(intent(), intent_ir_sha256="a" * 64, work_dir=tmp_path,
                               model=model, reviewer=reviewer)
    assert len(model.calls) == 2 and reviewer.calls == []
    assert not (tmp_path / "generation-0/filled_template.json").exists()


@pytest.mark.parametrize("field,value", [("minimum_candidates", None), ("minimum_candidates", 0),
                                         ("description", "replace policy")])
def test_fill_rejects_invalid_or_extra_nested_fields(field, value):
    template = make_template(intent(), load_evaluation_check_registry())
    candidate = body()
    candidate["discovery"][field] = value
    with pytest.raises(ValueError, match="REQUIREMENT_VALUES_INVALID"):
        fill_template(template, candidate)


def test_fixed_constant_and_template_integrity_are_enforced():
    template = make_template(intent(), load_evaluation_check_registry())
    candidate = body()
    candidate["requirements"][0]["checkable"] = False
    with pytest.raises(ValueError, match="REQUIREMENT_VALUES_INVALID"):
        fill_template(template, candidate)
    template["read_only"]["contract"]["policies"]["discovery_nonempty_handoff"]["default"] = 0
    with pytest.raises(ValueError, match="READ_ONLY_TEMPLATE_CHANGED"):
        fill_template(template, body())


def test_merge_copies_values_without_changing_fixed_definitions():
    original_intent = intent()
    template = make_template(original_intent, load_evaluation_check_registry())
    before = copy.deepcopy(template)
    values = body()
    filled = fill_template(template, values)
    values["requirements"][0]["statement"] = "later caller mutation"
    original_intent["constraints"].clear()
    assert template == before
    assert filled["values"] == body()
    assert filled["read_only"] == before["read_only"]


def test_explicit_user_minimum_is_preserved_and_reaches_runtime_filter(tmp_path):
    from plugins.autosci.services.retrieval_contract import filter_candidates
    source = intent()
    source["constraints"].append({"constraint_id": "C4", "category": "scope",
        "statement": "Discover at least 5 relevant papers", "expression": {
            "op": "greater_than_or_equal", "args": [{"ref": "candidate_count"}, {"literal": 5}]}})
    candidate = body()
    candidate["discovery"]["minimum_candidates"] = 5
    candidate["discovery"]["source_refs"].append("C4")
    candidate["selection_authority"].append({"field_path": "/discovery/minimum_candidates",
        "basis": "explicit_source_selection", "source_refs": ["C4"],
        "justification": "User explicitly requests at least five discovered papers."})
    row = copy.deepcopy(candidate["requirements"][1])
    row.update(requirement_id="R5", origin="user:C4", statement="Discover at least 5 papers",
               source_refs=["C4"], acceptance={"kind": "constraint", "required_values": ["at least 5 papers"]})
    candidate["requirements"].append(row)
    ir = compile_requirement_ir(source, intent_ir_sha256="a" * 64, work_dir=tmp_path,
                                model=Model(candidate), reviewer=Model({"accepted": True, "errors": []}))
    contract = ir["semantic_contract"]["discovery"]
    assert contract["minimum_candidates"] == 5
    rows = [{"source_id": str(i), "title": "marine heatwaves measured study"} for i in range(5)]
    assert filter_candidates(contract, rows[:4])[1]["status"] == "failed"
    assert filter_candidates(contract, rows)[1]["status"] == "passed"


def test_final_source_lower_bound_can_authorize_future_discovery_minimum(tmp_path):
    source = intent()
    source["constraints"].append({"constraint_id": "C4", "category": "limit",
        "statement": "Use 8–12 total sources in the final report", "expression": {
            "op": "bounded_by", "args": [{"ref": "workflow.sources.total"}, {"set": [8, 12]}]}})
    candidate = body()
    candidate["discovery"]["minimum_candidates"] = 8
    candidate["discovery"]["source_refs"].append("C4")
    candidate["selection_authority"].append({"field_path": "/discovery/minimum_candidates",
        "basis": "explicit_source_selection", "source_refs": ["C4"],
        "justification": "Eight accepted candidates are a necessary upstream condition for using at least eight final sources."})
    row = copy.deepcopy(candidate["requirements"][1])
    row.update(requirement_id="R5", origin="user:C4", statement="Use 8–12 total sources",
               source_refs=["C4"], acceptance={"kind": "constraint", "required_values": ["8–12 total sources"]})
    candidate["requirements"].append(row)
    ir = compile_requirement_ir(source, intent_ir_sha256="a" * 64, work_dir=tmp_path,
                                model=Model(candidate), reviewer=Model({"accepted": True, "errors": []}))
    assert ir["semantic_contract"]["discovery"]["minimum_candidates"] == 8
    assert ir["semantic_contract"]["template_ref"]["version"] == 3


def test_default_floor_still_rejects_empty_handoff():
    from plugins.autosci.services.retrieval_contract import filter_candidates
    _, audit = filter_candidates(body()["discovery"], [])
    assert audit["status"] == "failed"
    assert "minimum_candidates_not_met" in audit["blocking_reasons"]


def test_named_delivery_files_are_preserved_as_table_like_contract(tmp_path):
    source = intent()
    source["outcomes"][0]["description"] = "Write report.md and evidence_matrix.csv"
    candidate = body()
    candidate["delivery_manifest"] = {
        "output_root": "Downloads/demo_outputs/landscape",
        "exact_file_set": True,
        "files": [
            {
                "file_id": "report",
                "relative_path": "report.md",
                "media_type": "text/markdown",
                "description": "Evidence-grounded report",
                "content_requirements": ["Answer the research request"],
                "required_fields": [],
                "source_refs": ["D1"],
                "required": True,
            },
            {
                "file_id": "matrix",
                "relative_path": "evidence_matrix.csv",
                "media_type": "text/csv",
                "description": "Evidence matrix",
                "content_requirements": ["One row per source"],
                "required_fields": ["source_id", "claim"],
                "source_refs": ["D1"],
                "required": True,
            },
        ],
    }
    ir = compile_requirement_ir(
        source,
        intent_ir_sha256="a" * 64,
        work_dir=tmp_path,
        model=Model(candidate),
        reviewer=Model({"accepted": True, "errors": []}),
    )
    assert ir["semantic_contract"]["delivery_manifest"] == candidate["delivery_manifest"]


def test_named_delivery_files_cannot_be_collapsed_to_legacy_single_report(tmp_path):
    source = intent()
    source["outcomes"][0]["description"] = "Write report.md and evidence_matrix.csv"
    model = Model(body())
    with pytest.raises(RequirementCompilationError, match="NAMED_DELIVERY_FILE_SET_MISMATCH"):
        compile_requirement_ir(
            source,
            intent_ir_sha256="a" * 64,
            work_dir=tmp_path,
            model=model,
            reviewer=Model({"accepted": True, "errors": []}),
        )
    assert len(model.calls) == 2


@pytest.mark.parametrize("path", ["../report.md", "/tmp/report.md", "C:/tmp/report.md"])
def test_delivery_manifest_rejects_unsafe_paths(path):
    template = make_template(intent(), load_evaluation_check_registry())
    candidate = body()
    candidate["delivery_manifest"] = {
        "output_root": "Downloads/demo_outputs/landscape",
        "exact_file_set": True,
        "files": [{
            "file_id": "report",
            "relative_path": path,
            "media_type": "text/markdown",
            "description": "Report",
            "content_requirements": ["Non-empty"],
            "required_fields": [],
            "source_refs": ["D1"],
            "required": True,
        }],
    }
    filled = fill_template(template, candidate)
    from requirement_compiler.template_contract import delivery_manifest_defects
    assert delivery_manifest_defects(filled["values"])


def test_review_rejection_is_retained_as_advisory_diagnostic(tmp_path):
    reviewer = Model({"accepted": False, "errors": [{"rule_id": "F02",
        "field_path": "/discovery/minimum_candidates", "evidence_refs": ["G1"],
        "reason": "minimum_candidates=1 is an invented user count"}]})
    model = Model(body())
    ir = compile_requirement_ir(
        intent(), intent_ir_sha256="a" * 64, work_dir=tmp_path,
        model=model, reviewer=reviewer,
    )
    assert ir["semantic_contract"]["discovery"]["minimum_candidates"] == 1
    assert len(model.calls) == len(reviewer.calls) == 1
    validation = json.loads((tmp_path / "generation-0/validation.json").read_text())
    assert validation["accepted"] is True
    assert any("invented user count" in row for row in validation["warnings"])
    assert payload(reviewer.calls[0])["filled_template"]["read_only"] == payload(model.calls[0])["template"]["read_only"]


def test_policy_schema_inconsistency_is_rejected_before_any_model_call(tmp_path, monkeypatch):
    import requirement_compiler.template_contract as module
    definition = json.loads(module.CONTRACT_PATH.read_text())
    definition["policies"]["discovery_nonempty_handoff"]["default"] = 0
    fake_contract = tmp_path / "contract.json"
    fake_contract.write_text(json.dumps(definition))
    monkeypatch.setattr(module, "CONTRACT_PATH", fake_contract)
    model = Model(body())
    with pytest.raises(ValueError, match="POLICY_SCHEMA_MISMATCH"):
        compile_requirement_ir(intent(), intent_ir_sha256="a" * 64, work_dir=tmp_path / "compile",
                               model=model, reviewer=Model({"accepted": True, "errors": []}))
    assert model.calls == []
