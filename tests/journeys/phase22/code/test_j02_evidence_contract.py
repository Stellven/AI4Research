from __future__ import annotations

import copy
import importlib.util
import subprocess
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("test_j02_live_coding_task.py")
SPEC = importlib.util.spec_from_file_location("j02_live_evidence_contract", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


SID = "sprint-j02-evidence"


def _valid_inputs():
    status = {
        "id": SID,
        "status": "passed",
        "phase": "eval_passed",
        "history": [
            {
                "event": "eval_completed",
                "by": "evaluator",
                "verdict": "PASS",
                "reason": "implementation reviewed after tests and diff checks",
            }
        ],
    }
    events = [{"event": "eval_passed", "by": "evaluator", "verdict": "pass", "sid": SID}]
    decisions = [
        {
            "sid": SID,
            "action_requested": "status_transition:reviewing->passed",
            "decision": {"action": "allow", "reason": "status_transition_allowed"},
        }
    ]
    return status, events, decisions


def _evaluate(status, events, decisions):
    return MODULE._canonical_eval_verdict_evidence(
        sprint_id=SID,
        status_payload=status,
        session_events=events,
        gate_decisions=decisions,
    )


def test_canonical_eval_verdict_requires_three_consistent_product_records() -> None:
    status, events, decisions = _valid_inputs()

    result = _evaluate(status, events, decisions)

    assert result["valid"] is True
    assert len(result["status_verdicts"]) == 1
    assert len(result["session_verdicts"]) == 1
    assert len(result["gate_verdicts"]) == 1


def test_canonical_eval_verdict_fails_closed_on_tampering_or_missing_evidence() -> None:
    status, events, decisions = _valid_inputs()
    variants = []

    wrong_status = copy.deepcopy(status)
    wrong_status["status"] = "reviewing"
    variants.append((wrong_status, events, decisions))

    missing_reason = copy.deepcopy(status)
    missing_reason["history"][0]["reason"] = ""
    variants.append((missing_reason, events, decisions))

    wrong_actor = copy.deepcopy(events)
    wrong_actor[0]["by"] = "builder"
    variants.append((status, wrong_actor, decisions))

    wrong_sprint = copy.deepcopy(events)
    wrong_sprint[0]["sid"] = "sprint-other"
    variants.append((status, wrong_sprint, decisions))

    aborted_gate = copy.deepcopy(decisions)
    aborted_gate[0]["decision"] = {"action": "abort", "reason": "status_transition_from_mismatch"}
    variants.append((status, events, aborted_gate))

    duplicate_status_verdict = copy.deepcopy(status)
    duplicate_status_verdict["history"].append(copy.deepcopy(duplicate_status_verdict["history"][0]))
    variants.append((duplicate_status_verdict, events, decisions))

    for candidate_status, candidate_events, candidate_decisions in variants:
        assert _evaluate(candidate_status, candidate_events, candidate_decisions)["valid"] is False


def test_operator_result_lookup_selects_the_physical_builder(tmp_path: Path) -> None:
    result_root = tmp_path / "run" / "operator-results"
    planner = result_root / "mini-codex-builder-pool-1" / "pm-sprint-1-wake-planner-new"
    builder = result_root / "mini-codex-builder-1" / "mt-20260812-sprint-1-S1"
    planner.mkdir(parents=True)
    builder.mkdir(parents=True)
    with (planner / "result.json").open("w", encoding="utf-8") as handle:
        MODULE.json.dump(
            {
                "sprint_id": "sprint-1",
                "task_id": "pm-sprint-1-wake-planner-new",
                "operator_id": "mini-codex-builder-pool-1",
                "status": "completed",
                "exit_code": 0,
            },
            handle,
        )
    with (builder / "result.json").open("w", encoding="utf-8") as handle:
        MODULE.json.dump(
            {
                "sprint_id": "sprint-1",
                "task_id": "mt-20260812-sprint-1-S1",
                "operator_id": "mini-codex-builder-1",
                "status": "completed",
                "exit_code": 0,
            },
            handle,
        )

    task_dir, payload = MODULE._latest_operator_result_for_sprint(
        tmp_path,
        "sprint-1",
        excluded_task_id_fragment="-wake-planner-",
        operator_id_fragment="builder",
    )

    assert task_dir == builder
    assert payload["task_id"] == "mt-20260812-sprint-1-S1"


def test_workflow_route_waits_for_certified_builder(monkeypatch, tmp_path: Path) -> None:
    results = iter(
        [
            subprocess.CompletedProcess([], 0, stdout="planner\n", stderr=""),
            subprocess.CompletedProcess([], 0, stdout="builder_main\n", stderr=""),
        ]
    )
    monkeypatch.setattr(MODULE.subprocess, "run", lambda *args, **kwargs: next(results))
    monkeypatch.setattr(MODULE.time, "sleep", lambda seconds: None)

    route, observations = MODULE._wait_for_workflow_route(tmp_path, "sprint-1", {}, 5)

    assert route == "builder_main"
    assert [item["route"] for item in observations] == ["planner", "builder_main"]


def test_fixture_python_caches_are_removed_before_git_baseline(tmp_path: Path) -> None:
    cache = tmp_path / "pkg" / "__pycache__"
    cache.mkdir(parents=True)
    (cache / "module.cpython-312.pyc").write_bytes(b"bytecode")
    loose_bytecode = tmp_path / "loose.pyo"
    loose_bytecode.write_bytes(b"bytecode")
    source = tmp_path / "module.py"
    source.write_text("VALUE = 1\n", encoding="utf-8")

    MODULE._remove_python_cache_artifacts(tmp_path)

    assert not cache.exists()
    assert not loose_bytecode.exists()
    assert source.exists()


def test_journey_submits_verified_handoff_before_eval_verdict() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")
    handoff_call = source.index('"handoff-submit", sprint_id')
    eval_call = source.index('"eval-verdict", sprint_id')

    assert handoff_call < eval_call
