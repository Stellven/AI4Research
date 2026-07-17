"""AC-R5.1 — route records at the operatord seam (round-2 F7, design §1.4).

Route facts are produced in the operator process and never pass through the
scheduler, so the ledger hooks live in operator_runtime: the envelope write in
``submit()`` emits a ``phase=submitted`` route record (proof the stage started)
and ``write_result()`` emits ``phase=completed`` (exit_code + finished_at).
A run killed between the two already has its route evidence.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_HARNESS = Path(__file__).resolve().parents[2]
_HARNESS_LIB = str(_HARNESS / "lib")
if _HARNESS_LIB not in sys.path:
    sys.path.insert(0, _HARNESS_LIB)

import gate_ledger as gl  # noqa: E402
import operator_runtime as opr  # noqa: E402


SID = "lane3-route-sprint"
OP = "mini-codex-gpt55-medium-builder-1"


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setenv("SOLAR_GATE_LEDGER", "1")
    # Route records resolve via gate_ledger.default_sprints_dir() (round-4 G7)
    # — env-driven, so the sandbox must be pinned in the environment too.
    monkeypatch.setenv("HARNESS_DIR", str(tmp_path))
    monkeypatch.delenv("HARNESS_SPRINTS_DIR", raising=False)
    monkeypatch.setattr(opr, "HARNESS_DIR", tmp_path)
    monkeypatch.setattr(opr, "OPERATOR_RESULTS_DIR", tmp_path / "run" / "operator-results")
    return tmp_path


def _sprints(tmp_path):
    return tmp_path / "sprints"


def test_write_result_emits_completed_route_record(sandbox):
    opr.write_result(
        operator_id=OP,
        task_id="task-1",
        sprint_id=SID,
        node_id="S2",
        status="succeeded",
        exit_code=0,
        started_at="2026-07-07T00:00:00Z",
        finished_at="2026-07-07T00:03:00Z",
        log_tail="done",
        model_route={"effective_provider": "openai", "effective_model": "gpt-5.5-medium"},
    )
    rows = gl.read_records(_sprints(sandbox), SID, kind="route_record")
    assert len(rows) == 1
    row = rows[0]
    assert row["phase"] == "completed"
    assert row["node_id"] == "S2"
    assert row["task_id"] == "task-1"
    route = row["route"]
    assert route["provider"] == "openai"
    assert route["model"] == "gpt-5.5-medium"
    assert route["operator_id"] == OP
    assert route["exit_code"] == 0
    assert route["started_at"] == "2026-07-07T00:00:00Z"
    assert route["finished_at"] == "2026-07-07T00:03:00Z"


def test_write_result_flag_off_writes_no_route_record(tmp_path, monkeypatch):
    monkeypatch.setenv("SOLAR_GATE_LEDGER", "0")
    monkeypatch.setenv("HARNESS_DIR", str(tmp_path))
    monkeypatch.setattr(opr, "HARNESS_DIR", tmp_path)
    monkeypatch.setattr(opr, "OPERATOR_RESULTS_DIR", tmp_path / "run" / "operator-results")
    opr.write_result(
        operator_id=OP, task_id="t", sprint_id=SID, node_id="S1",
        status="succeeded", exit_code=0,
        started_at="2026-07-07T00:00:00Z", finished_at="2026-07-07T00:01:00Z",
        log_tail="",
    )
    assert not (_sprints(tmp_path) / f"{SID}.gate-ledger.jsonl").exists()
    # result.json itself still written (flag-off behavior unchanged)
    assert (tmp_path / "run" / "operator-results" / OP / "t" / "result.json").exists()


def test_submit_emits_submitted_route_record_kill_mid_run_evidence(sandbox, monkeypatch):
    """AC-R5.1: the envelope write alone leaves route evidence — no result needed."""
    monkeypatch.setattr(opr, "get_operator_config",
                        lambda operator_id: {"provider": "openai", "backend": "command",
                                             "model": "gpt-5.5-medium"})
    monkeypatch.setattr(opr, "get_operator_runtime_state", lambda operator_id: "idle")
    monkeypatch.setattr(opr, "resolve_persona", lambda *a, **k: {"persona": "stub"})
    monkeypatch.setattr(opr, "acquire_operator_lease",
                        lambda **k: {"expires_at": "2026-07-07T01:00:00Z",
                                     "leased_at": "2026-07-07T00:00:00Z"})
    monkeypatch.setattr(opr, "_auto_kick_enabled", lambda: False)

    result = opr.submit({
        "task_id": "task-9",
        "sprint_id": SID,
        "node_id": "S3",
        "operator_id": OP,
        "task_type": "code",
        "objective": "build the thing",
    })
    assert result["status"] == "submitted"

    # The run is now "killed" — no write_result ever happens. Route proof exists.
    rows = gl.read_records(_sprints(sandbox), SID, kind="route_record")
    assert len(rows) == 1
    row = rows[0]
    assert row["phase"] == "submitted"
    assert row["node_id"] == "S3"
    assert row["task_id"] == "task-9"
    assert row["route"]["provider"] == "openai"
    assert row["route"]["backend"] == "command"
    assert row["route"]["operator_id"] == OP
    assert row["route"]["started_at"]


def test_submit_bootstrap_failure_leaves_no_untruthful_submitted_record(sandbox, monkeypatch):
    """Round-4 G8: when the operatord auto-kick fails, submit() unlinks the
    envelope, releases the lease and raises — a 'submitted' route record for a
    stage that never ran must not survive the rollback."""
    monkeypatch.setattr(opr, "get_operator_config",
                        lambda operator_id: {"provider": "openai", "backend": "command",
                                             "model": "gpt-5.5-medium"})
    monkeypatch.setattr(opr, "get_operator_runtime_state", lambda operator_id: "idle")
    monkeypatch.setattr(opr, "resolve_persona", lambda *a, **k: {"persona": "stub"})
    monkeypatch.setattr(opr, "acquire_operator_lease",
                        lambda **k: {"expires_at": "2026-07-07T01:00:00Z",
                                     "leased_at": "2026-07-07T00:00:00Z"})
    released = []
    monkeypatch.setattr(opr, "release_operator_lease",
                        lambda operator_id, reason="": released.append(reason))
    monkeypatch.setattr(opr, "_auto_kick_enabled", lambda: True)

    def _boom(operator_id):
        raise RuntimeError("bootstrap boom")

    monkeypatch.setattr(opr, "_kick_operatord_once", _boom)
    monkeypatch.setattr(opr, "OPERATOR_INBOX_DIR", sandbox / "run" / "operator-inbox")

    with pytest.raises(RuntimeError, match="submit bootstrap failed"):
        opr.submit({"task_id": "task-g8", "sprint_id": SID, "node_id": "S1",
                    "operator_id": OP, "task_type": "code", "objective": "x"})

    assert released == ["submit_bootstrap_failed"]
    assert not (sandbox / "run" / "operator-inbox" / OP / "task-g8.json").exists()
    rows = gl.read_records(_sprints(sandbox), SID, kind="route_record")
    submitted = [r for r in rows if r.get("phase") == "submitted"
                 and r.get("task_id") == "task-g8"]
    assert not submitted, f"untruthful submitted record survived rollback: {submitted}"


def test_submit_with_auto_kick_success_still_records_submitted(sandbox, monkeypatch):
    """The record moved AFTER the auto-kick block — a successful kick (and the
    no-kick path, covered above) must still leave the AC-R5.1 evidence."""
    monkeypatch.setattr(opr, "get_operator_config",
                        lambda operator_id: {"provider": "openai", "backend": "command",
                                             "model": "gpt-5.5-medium"})
    monkeypatch.setattr(opr, "get_operator_runtime_state", lambda operator_id: "idle")
    monkeypatch.setattr(opr, "resolve_persona", lambda *a, **k: {"persona": "stub"})
    monkeypatch.setattr(opr, "acquire_operator_lease",
                        lambda **k: {"expires_at": "2026-07-07T01:00:00Z",
                                     "leased_at": "2026-07-07T00:00:00Z"})
    monkeypatch.setattr(opr, "_auto_kick_enabled", lambda: True)
    monkeypatch.setattr(opr, "_kick_operatord_once", lambda operator_id: 4242)
    monkeypatch.setattr(opr, "OPERATOR_INBOX_DIR", sandbox / "run" / "operator-inbox")

    result = opr.submit({"task_id": "task-g8b", "sprint_id": SID, "node_id": "S1",
                         "operator_id": OP, "task_type": "code", "objective": "x"})
    assert result["status"] == "submitted"
    assert result["daemon_pid"] == 4242
    rows = [r for r in gl.read_records(_sprints(sandbox), SID, kind="route_record")
            if r.get("task_id") == "task-g8b"]
    assert len(rows) == 1 and rows[0]["phase"] == "submitted"


def test_route_records_never_break_the_result_write(sandbox, monkeypatch):
    """Ledger failure must not take down write_result (best-effort contract)."""
    monkeypatch.setattr(gl, "append_route_record", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    path = opr.write_result(
        operator_id=OP, task_id="t2", sprint_id=SID, node_id="S1",
        status="failed", exit_code=3,
        started_at="2026-07-07T00:00:00Z", finished_at="2026-07-07T00:01:00Z",
        log_tail="err",
    )
    assert path.exists()
