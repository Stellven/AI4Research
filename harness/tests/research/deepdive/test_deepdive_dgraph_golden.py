"""Lane 4 — the vendored DeepDive D-graph is byte-stable, and the shipped
research.deepdive.rsi_demo contract is admissible under the real registries.

Two ties are locked here:
  1. R3 for the engine front-end — the vendored ``build_deepdive_evidence_dag``
     is deterministic (byte-identical twice + committed golden).
  2. The shipped contract compiles clean against the REAL capsule/operator
     registries per the Lane 1 remap (scout admits knowledge-extraction only,
     synthesizer admits evidence/research), and its D1-D6 stages are a faithful
     compression of the native D1-D9 D-graph (operators are a subset).

Env is pinned to THIS checkout (R9): HARNESS_DIR + sys.path at this lib.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_HARNESS = _HERE.parents[2]
_LIB = _HARNESS / "lib"
_CONFIG = _HARNESS / "config"
os.environ.setdefault("HARNESS_DIR", str(_HARNESS))
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

import workflow_contract as wc  # noqa: E402
from research.deepdive_requirement_compiler import (  # noqa: E402
    build_deepdive_evidence_dag,
    extract_research_questions,
    validate_deepdive_contract,
    compile_deepdive_brief,
)

GOLDEN = _HERE / "fixtures" / "deepdive_dgraph.golden.json"
CONTRACT = _CONFIG / "workflows" / "research.deepdive.rsi_demo.workflow.json"

# The exact brief the committed golden was generated from.
BRIEF = (
    "DeepDive: deep research report on Recursive Self-Improving Models.\n"
    "What is recursive self-improvement and why now?\n"
    "What evidence supports or contradicts it?\n"
    "What are the limits and safety implications?"
)


def _canonical(graph: dict) -> str:
    return json.dumps(graph, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _dgraph() -> dict:
    return build_deepdive_evidence_dag(extract_research_questions(BRIEF), insight_mode=False)


# ---------------------------------------------------------------------------
# R3: the vendored compiler's D-graph is deterministic.
# ---------------------------------------------------------------------------

def test_dgraph_byte_identical_twice():
    assert _canonical(_dgraph()) == _canonical(_dgraph())


def test_dgraph_matches_committed_golden():
    assert GOLDEN.is_file(), f"golden missing: {GOLDEN}"
    assert _canonical(_dgraph()) == GOLDEN.read_text(encoding="utf-8"), (
        "vendored build_deepdive_evidence_dag drifted from its committed golden — "
        "a compiler change must update the golden deliberately"
    )


def test_dgraph_native_invariants():
    dag = _dgraph()
    assert dag["dag_variant"] == "deepdive_research"
    ids = [n["id"] for n in dag["nodes"]]
    assert ids == ["D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8", "D9"]
    assert all(n["id"].startswith("D") for n in dag["nodes"])
    assert all(n["logical_operator"].startswith("DeepDive") for n in dag["nodes"])
    # The compiler's own validator agrees the full contract is well-formed.
    contract = compile_deepdive_brief(BRIEF)
    assert validate_deepdive_contract(contract)["ok"], validate_deepdive_contract(contract)


# ---------------------------------------------------------------------------
# Admissibility: the shipped contract compiles clean under the real registries.
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def registries():
    cap = wc.load_capsule_registry(_CONFIG)
    op = wc.load_operator_registry(_CONFIG / "physical-operators.json")
    return cap, op


@pytest.fixture(scope="module")
def contract():
    return wc.load_contract(CONTRACT)


def test_shipped_contract_compiles_clean(registries, contract):
    cap, op = registries
    assert wc.compile_checks(contract, cap, op, provider_policy=contract["provider_policy"]) == []
    assert wc.compile_checks(contract, cap, op) == []


def test_lane1_remap_capsule_admissions(registries):
    cap, _op = registries
    assert set(cap["cap.requirement-research-scout"]["task_type_in"]) == {"knowledge-extraction"}
    assert set(cap["cap.requirement-research-synthesizer"]["task_type_in"]) == {
        "evidence",
        "report-writing",
        "research",
    }
    assert "reporting" in cap["cap.requirement-compiler-audit"]["task_type_in"]
    # research capsules never produce patches (no implementation obligations on research stages)
    assert cap["cap.requirement-research-scout"]["produces_patch"] is False
    assert cap["cap.requirement-research-synthesizer"]["produces_patch"] is False
    assert cap["cap.requirement-compiler-implementation"]["produces_patch"] is True


def test_remap_is_load_bearing_scout_rejects_audit_inventory(registries, contract):
    # The example vocabulary paired the scout with audit_inventory; the real
    # registry rejects it. This proves the remap is enforced, not cosmetic.
    import copy

    cap, op = registries
    bad = copy.deepcopy(contract)
    for stage in bad["stages"]:
        if stage["id"] == "D2":
            stage["task_type"] = "audit_inventory"
    errors = wc.compile_checks(bad, cap, op, provider_policy=bad["provider_policy"])
    codes = {(e["code"], e["stage_id"]) for e in errors}
    assert ("TASK_TYPE_NOT_ADMITTED", "D2") in codes, errors


def test_shipped_stages_are_a_compression_of_the_native_dgraph(contract):
    native_ops = {n["logical_operator"] for n in _dgraph()["nodes"]}
    shipped_ops = {s["logical_operator"] for s in contract["stages"]}
    # Every shipped D1-D6 operator is one of the native D1-D9 operators (the
    # documented D1-D9 -> D1-D6 compression drops planner/verifier stages).
    assert shipped_ops <= native_ops, shipped_ops - native_ops
    assert {"DeepDiveBriefCapture", "DeepDiveSourceCollector", "DeepDiveClaimCompiler",
            "DeepDiveContradictionScanner", "DeepDiveChiefEditor",
            "DeepDiveArtifactPublisher"} <= shipped_ops


def test_shipped_contract_forbids_implementation_capsule_and_patch_obligations(contract):
    forbidden = contract["forbidden"]
    assert "cap.requirement-compiler-implementation" in forbidden["capsules"]
    assert "patch_diff" in forbidden["proof_obligations"]
    for stage in contract["stages"]:
        assert "cap.requirement-compiler-implementation" not in stage["allowed_capsules"]
