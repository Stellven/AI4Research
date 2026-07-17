"""rc.10: one contract-owned policy governs generic control-plane reads."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


HARNESS = Path(__file__).resolve().parents[2]
LIB = HARNESS / "lib"
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))

import plan_validator as pv  # noqa: E402
import workflow_contract as wc  # noqa: E402


SID = "sprint-rc10-generic-control-policy"
EXPECTED_LIVE_SUFFIXES = {
    "requirement_ir.json",
    "product-brief.md",
    "contract.md",
    "design.md",
    "plan.md",
    "task_graph.json",
}
MUTABLE_RUNTIME_PROJECTIONS = {
    "requirement_trace.json",
    "coverage_report.json",
    "acceptance_verdict.json",
}


def _contract() -> dict:
    contract = wc.find_contract(pv.GENERIC_CONTRACT_ID)
    assert contract is not None
    return contract


def _graph(read_scope: list[str]) -> dict:
    return {
        "sprint_id": SID,
        "workflow_contract_id": pv.GENERIC_CONTRACT_ID,
        "workflow_contract_version": "1.0",
        "nodes": [
            {
                "id": "S1",
                "depends_on": [],
                "task_type": "implementation",
                "read_scope": read_scope,
                "write_scope": ["workspace/result.py"],
                "evaluator_gate": {"kind": "llm_eval", "on_fail": "fail"},
                "max_repair_attempts": 0,
            }
        ],
    }


def _codes(graph: dict) -> set[str]:
    return {
        str(item.get("code") or "")
        for item in pv.validate_plan(graph, None, None, contract=_contract())
    }


def test_generic_contract_declares_all_live_control_plane_inputs() -> None:
    policy = _contract().get("control_plane_read_policy") or {}
    assert policy.get("root_policy") == "exact_current_sprint_file"
    assert EXPECTED_LIVE_SUFFIXES <= set(policy.get("suffixes") or [])
    assert MUTABLE_RUNTIME_PROJECTIONS.isdisjoint(set(policy.get("suffixes") or []))


@pytest.mark.parametrize("suffix", sorted(MUTABLE_RUNTIME_PROJECTIONS))
def test_plan_compile_rejects_mutable_runtime_projection_reads(suffix: str) -> None:
    declared = f"sprints/{SID}.{suffix}"
    assert "PLAN_READ_SCOPE_UNRESOLVED" in _codes(_graph([declared]))


@pytest.mark.parametrize(
    "declared",
    [
        f"sprints/{SID}.private.json",
        "sprints/sprint-foreign.requirement_ir.json",
        f"sprints/./{SID}.requirement_ir.json",
        f"sprints/{SID}.requirement_ir.json/",
        f"/tmp/{SID}.requirement_ir.json",
        "sprints/<sid>/workdir/upstream.py",
        "sprints/sprint-foreign/workdir/upstream.py",
    ],
)
def test_plan_compile_rejects_unowned_or_noncanonical_reads(declared: str) -> None:
    assert "PLAN_READ_SCOPE_UNRESOLVED" in _codes(_graph([declared]))


def test_plan_compile_accepts_workspace_and_contract_control_reads() -> None:
    reads = ["workspace/upstream.py"] + [
        f"sprints/{SID}.{suffix}" for suffix in sorted(EXPECTED_LIVE_SUFFIXES)
    ]
    assert "PLAN_READ_SCOPE_UNRESOLVED" not in _codes(_graph(reads))


def test_plan_compile_rejects_foreign_sprint_write_alias() -> None:
    graph = _graph([])
    graph["nodes"][0]["write_scope"] = [
        "sprints/sprint-foreign/workdir/result.py"
    ]
    assert wc.ERROR_ARTIFACT_ROOT_UNRESOLVED in _codes(graph)


@pytest.mark.parametrize("invalid_sid", ["", "../foreign", "sprint/foreign"])
def test_plan_compile_does_not_leave_sprint_alias_as_a_wildcard(
    invalid_sid: str,
) -> None:
    graph = _graph([])
    graph["sprint_id"] = invalid_sid
    graph["nodes"][0]["write_scope"] = [
        "sprints/sprint-foreign/workdir/result.py"
    ]
    assert wc.ERROR_ARTIFACT_ROOT_UNRESOLVED in _codes(graph)


def test_plan_compile_accepts_schema_legal_string_write_scope() -> None:
    graph = _graph([])
    graph["nodes"][0]["write_scope"] = "workspace/result.py"
    assert wc.ERROR_ARTIFACT_ROOT_UNRESOLVED not in _codes(graph)


def test_planner_policy_block_names_the_contract_control_namespace() -> None:
    block = pv.planner_compile_policy_block(sid=SID)
    assert "current-sprint control-plane" in block
    assert f"sprints/{SID}.requirement_ir.json" in block
    assert f"sprints/{SID}.task_graph.json" in block


def test_compile_generic_rejects_internal_sprint_identity_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SOLAR_PLAN_VALIDATOR", "1")
    graph = _graph([])
    graph["sprint_id"] = "sprint-foreign"
    graph["nodes"][0].update(
        {
            "dispatch_task_type": "implementation",
            "capability_capsule_id": "cap.requirement-compiler-implementation",
            "allowed_operators": {"role": "builder", "providers": ["openai"]},
        }
    )
    (tmp_path / f"{SID}.task_graph.json").write_text(
        json.dumps(graph, indent=2) + "\n",
        encoding="utf-8",
    )

    result = pv.compile_planner_graph(tmp_path, SID)

    assert result["ok"] is False, result
    assert "PLAN_SPRINT_ID_MISMATCH" in {
        str(item.get("code") or "") for item in result["errors"]
    }


def test_compile_generic_does_not_trust_self_stamped_invalid_graph(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SOLAR_PLAN_VALIDATOR", "1")
    graph = _graph([f"sprints/{SID}.private.json"])
    graph["nodes"][0].update(
        {
            "dispatch_task_type": "implementation",
            "capability_capsule_id": "cap.requirement-compiler-implementation",
            "allowed_operators": {"role": "builder", "providers": ["openai"]},
        }
    )
    graph["plan_certificate"] = {
        "schema": pv.PLAN_CERTIFICATE_SCHEMA,
        "validator": "plan_validator",
        "verdict": "PASS",
        "graph_hash": pv.plan_certificate_hash(graph),
        "validated_at": "2026-07-16T00:00:00Z",
    }
    (tmp_path / f"{SID}.task_graph.json").write_text(
        json.dumps(graph, indent=2) + "\n",
        encoding="utf-8",
    )

    result = pv.compile_planner_graph(tmp_path, SID)

    assert result["ok"] is False, result
    assert "PLAN_READ_SCOPE_UNRESOLVED" in {
        str(item.get("code") or "") for item in result["errors"]
    }
