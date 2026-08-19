"""A stage that recorded its own failure must not be gated PASS.

In the 2026-08-19 Haiku run, `report_revision` and `final_acceptance` both wrote
`"status": "failed"` with `status_is_terminal: true` into their own
`research_node_result.json`. `final_acceptance` said in as many words that it
"rejected the research result". Both were recorded as
`verdict PASS, gate_kind none, duration 0.0`, `failed_nodes` stayed empty, and
the DAG advanced past them to `poc_handoff`.

Their artifacts were present and looked healthy, because a failed dispatch
leaves behind whatever it wrote before raising: `revision/report.md` was written
one second before the operator failed. That is why presence checks cannot cover
this and the operator's recorded status has to be read.

The contract assertion at the bottom is the one that matters over time. The
checker can be perfect and still gate nothing if a stage quietly goes back to
`"kind": "none"`, which is the state this whole workflow started in.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

HARNESS = Path(__file__).resolve().parents[2]
REPO = HARNESS.parent
if str(HARNESS / "scripts") not in sys.path:
    sys.path.insert(0, str(HARNESS / "scripts"))

import validate_evidence_to_poc as gate  # noqa: E402

CONTRACT = HARNESS / "config" / "workflows" / "research.evidence_to_poc.v1.workflow.json"


def _write_result(workspace: Path, stage: str, payload: dict[str, Any] | None) -> None:
    # Contract-declared paths already include the artifact root.
    directory = workspace / gate.NODE_RESULT_DIR_BY_STAGE[stage]
    directory.mkdir(parents=True, exist_ok=True)
    if payload is not None:
        (directory / "research_node_result.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )


def test_completed_stage_passes(tmp_path: Path) -> None:
    _write_result(tmp_path, "report_revision", {"status": "completed"})
    assert gate.check_node_complete(tmp_path, ["report_revision"]) == []


def test_failed_stage_is_caught_and_its_reason_is_reported(tmp_path: Path) -> None:
    _write_result(
        tmp_path,
        "final_acceptance",
        {
            "status": "failed",
            "status_is_terminal": True,
            "errors": [{"message": "Final acceptance gate rejected the research result."}],
        },
    )
    failures = gate.check_node_complete(tmp_path, ["final_acceptance"])
    assert len(failures) == 1
    # A gate that only says "something is wrong" costs as much time as no gate.
    assert "status=failed" in failures[0]
    assert "rejected the research result" in failures[0]


def test_a_missing_result_is_a_failure_not_a_pass(tmp_path: Path) -> None:
    """Silence must not read as success.

    A stage that never wrote a result and a stage whose result was lost are
    indistinguishable here, and both are reasons to stop.
    """
    _write_result(tmp_path, "report_draft", None)
    failures = gate.check_node_complete(tmp_path, ["report_draft"])
    assert len(failures) == 1
    assert "no readable research_node_result.json" in failures[0]


def test_unknown_stage_is_rejected(tmp_path: Path) -> None:
    assert gate.check_node_complete(tmp_path, ["not_a_stage"]) == [
        "not_a_stage: not a stage of this workflow"
    ]


def test_node_complete_alone_does_not_run_the_source_and_claim_checks(tmp_path: Path) -> None:
    """A stage gates on its own completion without re-grading earlier stages."""
    _write_result(tmp_path, "report_revision", {"status": "completed"})
    exit_code = gate.main(
        ["--workspace", str(tmp_path), "--node-complete", "report_revision"]
    )
    assert exit_code == 0


@pytest.mark.parametrize("stage", sorted(gate.NODE_RESULT_DIR_BY_STAGE))
def test_every_stage_with_a_known_result_dir_is_actually_gated(stage: str) -> None:
    """The checker is worthless if the contract does not call it.

    This fails if a stage reverts to `"kind": "none"`, which is the state that
    let two failed nodes be recorded as passes.
    """
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    by_id = {item["id"]: item for item in contract["stages"]}
    evaluator_gate = by_id[stage]["evaluator_gate"]
    assert evaluator_gate["kind"] == "deterministic_command", stage
    assert f"--node-complete {stage}" in evaluator_gate["command"], stage
    assert evaluator_gate["on_fail"] == "fail", stage


def test_the_result_dir_map_is_derived_from_the_contract_not_hardcoded() -> None:
    """Every stage, and the exact directory the contract declares.

    A hardcoded map cost a live run: `poc_handoff` writes to `poc/handoff/`, not
    `poc/`, so the gate reported "no node result on disk" for a stage that had
    completed perfectly, and failed the node. Part B nests all of its
    directories the same way.
    """
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    declared = {}
    for stage in contract["stages"]:
        directory = next(
            (item["path"] for item in stage["outputs"] if item.get("type") == "directory"),
            None,
        )
        assert directory, stage["id"]
        declared[stage["id"]] = Path(directory)
    assert gate.NODE_RESULT_DIR_BY_STAGE == declared
    assert len(declared) == 15


def test_every_stage_in_the_contract_is_gated() -> None:
    """All fifteen, not just the ones that were easy to map."""
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    ungated = [
        stage["id"]
        for stage in contract["stages"]
        if (stage.get("evaluator_gate") or {}).get("kind") != "deterministic_command"
    ]
    assert ungated == [], ungated
