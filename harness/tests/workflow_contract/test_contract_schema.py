"""Deterministic test 1 (stage_contract_schema_valid, generalized; AC-R3.2):
the shipped contracts schema-validate, and structural defects are rejected."""
from __future__ import annotations

import copy
from pathlib import Path

import pytest

HARNESS_DIR = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = HARNESS_DIR / "config" / "workflows"

import workflow_contract as wc


def test_module_imports_from_this_checkout():
    """No installed-harness imports (R9)."""
    assert Path(wc.__file__).resolve().is_relative_to(HARNESS_DIR.resolve()), wc.__file__


def test_all_shipped_contracts_schema_valid(shipped_contracts):
    assert set(shipped_contracts) == {
        "research.deepdive.rsi_demo",
        "code.cli_smoke",
        "code.cli_smoke_anthropic",
        "pm.generic.v1",
    }
    for contract in shipped_contracts.values():
        assert wc.validate_contract_schema(contract) == []


def test_rsi_contract_declares_research_dag_variant(shipped_contracts):
    assert shipped_contracts["research.deepdive.rsi_demo"]["dag_variant"] == "research"
    assert shipped_contracts["code.cli_smoke"]["dag_variant"] == "short"
    assert shipped_contracts["code.cli_smoke_anthropic"]["dag_variant"] == "short"


def _mutate(contract, path, value):
    doc = copy.deepcopy(contract)
    cursor = doc
    for key in path[:-1]:
        cursor = cursor[key]
    if value is _DELETE:
        del cursor[path[-1]]
    else:
        cursor[path[-1]] = value
    doc.pop("_source_path", None)
    return doc


_DELETE = object()

_MUTATIONS = [
    ("missing workflow_id", ["workflow_id"], _DELETE),
    ("bad schema_version", ["schema_version"], "solar.workflow_contract.v0"),
    ("empty version", ["version"], ""),
    # The C1+C2 regression: contract identity must NEVER ride in dag_variant.
    ("workflow id smuggled into dag_variant", ["dag_variant"], "research.deepdive.rsi_demo"),
    ("legacy deepdive_research dag_variant", ["dag_variant"], "deepdive_research"),
    ("invalid node_kind", ["stages", 0, "node_kind"], "report"),
    ("missing task_type", ["stages", 0, "task_type"], ""),
    ("empty allowed_capsules", ["stages", 0, "allowed_capsules"], []),
    ("unknown depends_on", ["stages", 1, "depends_on"], ["NOPE"]),
    ("invalid evaluator gate kind", ["stages", 0, "evaluator_gate"], {"kind": "vibes"}),
    ("invalid on_human_review", ["stages", 2, "evaluator_gate", "on_human_review"], "ignore"),
    ("missing timeouts", ["stages", 0, "timeouts"], {}),
    ("zero timeout", ["stages", 0, "timeouts"], {"result_timeout_sec": 0}),
]


@pytest.mark.parametrize("label,path,value", _MUTATIONS, ids=[m[0] for m in _MUTATIONS])
def test_structural_defects_rejected(shipped_contracts, label, path, value):
    doc = _mutate(shipped_contracts["research.deepdive.rsi_demo"], path, value)
    assert wc.validate_contract_schema(doc), f"mutation not rejected: {label}"


def test_duplicate_stage_ids_rejected(shipped_contracts):
    doc = copy.deepcopy(shipped_contracts["research.deepdive.rsi_demo"])
    doc["stages"][1]["id"] = doc["stages"][0]["id"]
    errors = wc.validate_contract_schema(doc)
    assert any("duplicate" in e for e in errors)


def test_dependency_cycle_rejected(shipped_contracts):
    doc = copy.deepcopy(shipped_contracts["research.deepdive.rsi_demo"])
    doc["stages"][0]["depends_on"] = [doc["stages"][5]["id"]]
    errors = wc.validate_contract_schema(doc)
    assert any("cycle" in e for e in errors)


def test_planner_generated_contract_must_not_declare_stages(shipped_contracts):
    doc = copy.deepcopy(shipped_contracts["pm.generic.v1"])
    doc["stages"] = [{"id": "X1"}]
    assert wc.validate_contract_schema(doc)


def test_load_contract_rejects_malformed_file(tmp_path):
    bad = tmp_path / "broken.workflow.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(wc.ContractSchemaError):
        wc.load_contract(bad)


def test_load_all_contracts_is_sorted_and_stable():
    first = [c["workflow_id"] for c in wc.load_all_contracts(WORKFLOWS_DIR)]
    second = [c["workflow_id"] for c in wc.load_all_contracts(WORKFLOWS_DIR)]
    assert first == second == sorted(first)
