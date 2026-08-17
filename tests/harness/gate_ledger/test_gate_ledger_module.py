"""Gate ledger module unit tests (Lane 3, design §1.4 / R4).

Pure-module tests: append-only records, tolerant reads, status projection with
terminal-absorbing semantics, and gate-consumability classification. No graph
runtime involved — the interception tests live in test_status_writer_surface.py.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

_HARNESS_LIB = str((Path(__file__).resolve().parents[3] / 'harness') / "lib")
if _HARNESS_LIB not in sys.path:
    sys.path.insert(0, _HARNESS_LIB)

import gate_ledger as gl  # noqa: E402


SID = "lane3-test-sprint"


def _append(tmp_path, **kwargs):
    defaults = {"node_id": "S1", "kind": "status_transition"}
    defaults.update(kwargs)
    return gl.append_record(tmp_path, SID, **defaults)


# ---------------------------------------------------------------------------
# Append / read round-trip
# ---------------------------------------------------------------------------

def test_append_and_read_roundtrip(tmp_path):
    rec = gl.append_record(
        tmp_path,
        SID,
        node_id="S2",
        kind="eval_verdict",
        author={"type": "evaluator", "operator_id": "mini-codex-gpt55-medium-evaluator-1"},
        verdict="FAIL",
        verdict_kind="content",
        eval_generation=1,
        repair_attempt=0,
        pm_task_id="pm-123",
        evidence_snapshot_at="2026-07-07T00:00:00Z",
    )
    assert rec is not None
    assert rec["record_id"]
    assert rec["created_at"]
    assert rec["sid"] == SID

    rows = gl.read_records(tmp_path, SID)
    assert len(rows) == 1
    row = rows[0]
    assert row["node_id"] == "S2"
    assert row["kind"] == "eval_verdict"
    assert row["author"]["type"] == "evaluator"
    assert row["verdict"] == "FAIL"
    assert row["verdict_kind"] == "content"
    assert row["eval_generation"] == 1
    assert row["repair_attempt"] == 0
    assert row["pm_task_id"] == "pm-123"
    assert (Path(tmp_path) / f"{SID}.gate-ledger.jsonl").exists()


def test_record_ids_unique_and_appends_accumulate(tmp_path):
    ids = set()
    for i in range(5):
        rec = _append(tmp_path, from_status="pending", to_status="running")
        ids.add(rec["record_id"])
    assert len(ids) == 5
    assert len(gl.read_records(tmp_path, SID)) == 5


def test_append_never_raises_on_unwritable_dir(tmp_path):
    target = tmp_path / "blocked"
    target.mkdir()
    os.chmod(target, 0o500)
    try:
        rec = gl.append_record(target / "sub", SID, node_id="S1", kind="gate_check")
        assert rec is None
    finally:
        os.chmod(target, 0o700)


def test_invalid_kind_dropped(tmp_path):
    assert _append(tmp_path, kind="not_a_kind") is None
    assert gl.read_records(tmp_path, SID) == []


def test_invalid_verdict_kind_dropped(tmp_path):
    rec = _append(tmp_path, kind="eval_verdict", verdict="PASS", verdict_kind="vibes")
    assert rec is None
    assert gl.read_records(tmp_path, SID) == []


def test_read_skips_malformed_lines(tmp_path):
    _append(tmp_path, from_status="pending", to_status="running")
    ledger = Path(tmp_path) / f"{SID}.gate-ledger.jsonl"
    with ledger.open("a", encoding="utf-8") as fh:
        fh.write("{ this is not json\n")
        fh.write(json.dumps({"kind": "status_transition"}) + "\n")  # missing node_id: tolerated on read
    _append(tmp_path, from_status="running", to_status="passed")
    rows = gl.read_records(tmp_path, SID)
    assert len(rows) >= 2  # the two good appends survive


def test_read_filters_by_node_and_kind(tmp_path):
    _append(tmp_path, node_id="S1", from_status="pending", to_status="running")
    _append(tmp_path, node_id="S2", from_status="pending", to_status="running")
    _append(tmp_path, node_id="S1", kind="eval_verdict", verdict="PASS", verdict_kind="content")
    assert len(gl.read_records(tmp_path, SID, node_id="S1")) == 2
    assert len(gl.read_records(tmp_path, SID, kind="eval_verdict")) == 1
    assert len(gl.read_records(tmp_path, SID, node_id="S1", kind="status_transition")) == 1


# ---------------------------------------------------------------------------
# Projection (R4: status is a projection of the ledger)
# ---------------------------------------------------------------------------

def test_projection_follows_applied_transitions(tmp_path):
    assert gl.project_node_status(tmp_path, SID, "S1") == ""
    for old, new in [("", "pending"), ("pending", "dispatched"), ("dispatched", "running"),
                     ("running", "reviewing"), ("reviewing", "passed")]:
        _append(tmp_path, from_status=old, to_status=new,
                author={"type": "scheduler"}, writer="set_node_status")
    assert gl.project_node_status(tmp_path, SID, "S1") == "passed"


def test_projection_applies_recorded_passed_to_failed(tmp_path):
    # Round-4 G6 (reviewer probe): a REAL recorded passed->failed force-write
    # (mark_node_result on a content FAIL / parent failure) must project
    # "failed" — the old pass-only reopen rule laundered it into a stale
    # "passed", a status-truth lie inside the truth mechanism itself.
    _append(tmp_path, from_status="reviewing", to_status="passed",
            author={"type": "scheduler"}, writer="mark_node_result")
    _append(tmp_path, from_status="passed", to_status="failed",
            author={"type": "scheduler"}, writer="mark_node_result")
    assert gl.project_node_status(tmp_path, SID, "S1") == "failed"


def test_projection_applies_any_applied_post_terminal_record(tmp_path):
    # Absorbing means "no exit from terminal without an APPLIED audited
    # record" — not "the projection may contradict a recorded write". Applied
    # records exist only via audited writers; they always project.
    _append(tmp_path, from_status="reviewing", to_status="failed",
            author={"type": "scheduler"}, writer="mark_node_result")
    _append(tmp_path, from_status="failed", to_status="pending",
            author={"type": "scheduler"}, writer="recover_quota_failed_nodes")
    assert gl.project_node_status(tmp_path, SID, "S1") == "pending"


def test_projection_terminal_absorbing_against_unapplied_records(tmp_path):
    # The absorbing guarantee that REMAINS: neutralized (applied=False)
    # would-be writes never project, terminal or not.
    _append(tmp_path, from_status="reviewing", to_status="failed", author={"type": "scheduler"})
    _append(tmp_path, from_status="failed", to_status="running",
            author={"type": "doctor"}, applied=False)
    assert gl.project_node_status(tmp_path, SID, "S1") == "failed"


def test_projection_human_verdict_reopens_terminal(tmp_path):
    _append(tmp_path, from_status="reviewing", to_status="failed", author={"type": "scheduler"})
    _append(tmp_path, from_status="failed", to_status="reviewing", author={"type": "human"})
    assert gl.project_node_status(tmp_path, SID, "S1") == "reviewing"


def test_projection_reopen_flag_allows_legacy_pass_reopen(tmp_path):
    # set_node_status legitimately reopens passed -> reviewing (reopening_from_pass);
    # the recorded transition carries reopen=True and the projection honors it.
    _append(tmp_path, from_status="running", to_status="passed", author={"type": "scheduler"})
    _append(tmp_path, from_status="passed", to_status="reviewing",
            author={"type": "scheduler"}, reopen=True)
    assert gl.project_node_status(tmp_path, SID, "S1") == "reviewing"


def test_projection_ignores_unapplied_doctor_records(tmp_path):
    _append(tmp_path, from_status="pending", to_status="running", author={"type": "scheduler"})
    _append(tmp_path, from_status="running", to_status="reviewing",
            author={"type": "doctor"}, applied=False, gate_consumable=False)
    assert gl.project_node_status(tmp_path, SID, "S1") == "running"


def test_projection_is_per_node(tmp_path):
    _append(tmp_path, node_id="S1", from_status="pending", to_status="passed")
    _append(tmp_path, node_id="S2", from_status="pending", to_status="failed")
    assert gl.project_node_status(tmp_path, SID, "S1") == "passed"
    assert gl.project_node_status(tmp_path, SID, "S2") == "failed"


# ---------------------------------------------------------------------------
# Consumability (R4: only assigned-evaluator, current-generation records feed gates)
# ---------------------------------------------------------------------------

def test_evaluator_current_generation_is_consumable():
    rec = {"kind": "eval_verdict", "author": {"type": "evaluator", "operator_id": "op-1"},
           "verdict": "PASS", "verdict_kind": "content", "eval_generation": 2}
    assert gl.is_gate_consumable(rec, current_generation=2) is True


def test_doctor_author_never_consumable():
    rec = {"kind": "eval_verdict", "author": {"type": "doctor"},
           "verdict": "PASS", "verdict_kind": "content", "eval_generation": 2}
    assert gl.is_gate_consumable(rec, current_generation=2) is False


def test_backfilled_eval_never_consumable():
    rec = {"kind": "eval_verdict", "author": {"type": "evaluator", "operator_id": "op-1"},
           "verdict": "PASS", "verdict_kind": "content", "eval_generation": 2,
           "generation_mode": "repair_backfill"}
    assert gl.is_gate_consumable(rec, current_generation=2) is False


def test_self_graded_eval_never_consumable():
    rec = {"kind": "eval_verdict", "author": {"type": "evaluator", "operator_id": "op-1"},
           "verdict": "PASS", "verdict_kind": "content", "eval_generation": 2,
           "self_graded": True}
    assert gl.is_gate_consumable(rec, current_generation=2) is False


def test_neutralized_record_never_consumable():
    """A record marked applied=False must not feed a gate decision.

    Every other test that sets applied=False also sets a doctor author or
    gate_consumable=False, so each of those would still be rejected with this
    guard deleted. Mutating `applied is False` to a no-op survived the whole
    gate_ledger suite; this is the case that kills it: an assigned evaluator,
    current generation, not self-graded, neutralized only by applied.
    """
    rec = {"kind": "eval_verdict", "author": {"type": "evaluator", "operator_id": "op-1"},
           "verdict": "PASS", "verdict_kind": "content", "eval_generation": 2,
           "applied": False}
    assert gl.is_gate_consumable(rec, current_generation=2) is False


def test_stale_generation_not_consumable():
    rec = {"kind": "eval_verdict", "author": {"type": "evaluator", "operator_id": "op-1"},
           "verdict": "PASS", "verdict_kind": "content", "eval_generation": 1}
    assert gl.is_gate_consumable(rec, current_generation=2) is False


def test_missing_generation_with_current_generation_not_consumable():
    # Round-4 G9: a record that cannot prove WHICH generation it evaluated must
    # not be consumable at any specific generation (fail-closed, AC-R4.4).
    rec = {"kind": "eval_verdict", "author": {"type": "evaluator", "operator_id": "op-1"},
           "verdict": "PASS", "verdict_kind": "content"}
    assert gl.is_gate_consumable(rec, current_generation=5) is False


def test_missing_generation_without_current_generation_still_consumable():
    # No generation filter requested -> the generation check is not in play.
    rec = {"kind": "eval_verdict", "author": {"type": "evaluator", "operator_id": "op-1"},
           "verdict": "PASS", "verdict_kind": "content"}
    assert gl.is_gate_consumable(rec) is True


def test_explicit_flag_wins():
    rec = {"kind": "eval_verdict", "author": {"type": "evaluator", "operator_id": "op-1"},
           "verdict": "PASS", "verdict_kind": "content", "eval_generation": 2,
           "gate_consumable": False}
    assert gl.is_gate_consumable(rec, current_generation=2) is False


def test_latest_consumable_verdict_skips_archived_and_stale(tmp_path):
    gl.append_record(tmp_path, SID, node_id="S1", kind="eval_verdict",
                     author={"type": "evaluator", "operator_id": "op-1"},
                     verdict="PASS", verdict_kind="content", eval_generation=1)
    gl.append_record(tmp_path, SID, node_id="S1", kind="eval_verdict",
                     author={"type": "doctor"},
                     verdict="PASS", verdict_kind="mechanical", eval_generation=2,
                     gate_consumable=False)
    gl.append_record(tmp_path, SID, node_id="S1", kind="eval_verdict",
                     author={"type": "evaluator", "operator_id": "op-2"},
                     verdict="FAIL", verdict_kind="content", eval_generation=2)
    latest = gl.latest_consumable_verdict(tmp_path, SID, "S1", current_generation=2)
    assert latest is not None
    assert latest["verdict"] == "FAIL"
    assert latest["author"]["operator_id"] == "op-2"


def test_latest_consumable_verdict_none_when_only_backfill(tmp_path):
    gl.append_record(tmp_path, SID, node_id="S1", kind="eval_verdict",
                     author={"type": "evaluator", "operator_id": "op-1"},
                     verdict="PASS", verdict_kind="content", eval_generation=1,
                     generation_mode="repair_backfill")
    assert gl.latest_consumable_verdict(tmp_path, SID, "S1", current_generation=1) is None


# ---------------------------------------------------------------------------
# Route records (R5 / AC-R5.1)
# ---------------------------------------------------------------------------

def test_route_record_roundtrip(tmp_path):
    rec = gl.append_route_record(
        tmp_path, SID, node_id="S1", task_id="task-9",
        phase="completed",
        route={"provider": "openai", "model": "gpt-5.5", "operator_id": "mini-codex-1",
               "backend": "command", "exit_code": 0,
               "started_at": "2026-07-07T00:00:00Z", "finished_at": "2026-07-07T00:01:00Z"},
    )
    assert rec is not None
    rows = gl.read_records(tmp_path, SID, kind="route_record")
    assert len(rows) == 1
    route = rows[0]["route"]
    for key in ("provider", "model", "operator_id", "backend", "exit_code", "started_at", "finished_at"):
        assert key in route
    assert rows[0]["phase"] == "completed"
    assert rows[0]["task_id"] == "task-9"


def test_route_record_requires_route_payload(tmp_path):
    assert gl.append_route_record(tmp_path, SID, node_id="S1", task_id="t", phase="submitted", route={}) is None
    assert gl.append_route_record(tmp_path, SID, node_id="S1", task_id="t", phase="submitted",
                                  route={"provider": "openai"}) is not None  # partial allowed at submit
    rows = gl.read_records(tmp_path, SID, kind="route_record")
    assert len(rows) == 1


# ---------------------------------------------------------------------------
# Flag gate
# ---------------------------------------------------------------------------

def test_enabled_reads_env(monkeypatch):
    # G4 default-on (owner decision 2026-07-10): unset means ON;
    # only the explicit kill switch disables the ledger.
    monkeypatch.delenv("SOLAR_GATE_LEDGER", raising=False)
    assert gl.enabled() is True
    monkeypatch.setenv("SOLAR_GATE_LEDGER", "1")
    assert gl.enabled() is True
    monkeypatch.setenv("SOLAR_GATE_LEDGER", "0")
    assert gl.enabled() is False


def test_record_status_transition_noop_when_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("SOLAR_GATE_LEDGER", "0")
    out = gl.record_status_transition(
        tmp_path, SID, "S1", from_status="pending", to_status="running",
        author_type="scheduler", writer="set_node_status")
    assert out is None
    assert not (Path(tmp_path) / f"{SID}.gate-ledger.jsonl").exists()


def test_record_status_transition_writes_when_enabled(tmp_path, monkeypatch):
    monkeypatch.setenv("SOLAR_GATE_LEDGER", "1")
    out = gl.record_status_transition(
        tmp_path, SID, "S1", from_status="reviewing", to_status="needs_human_review",
        author_type="scheduler", writer="_account_eval_dispatch_failures")
    assert out is not None
    rows = gl.read_records(tmp_path, SID, kind="status_transition")
    assert rows and rows[-1]["to_status"] == "needs_human_review"
    assert rows[-1]["writer"] == "_account_eval_dispatch_failures"


def test_record_status_transition_skips_noop_same_status(tmp_path, monkeypatch):
    monkeypatch.setenv("SOLAR_GATE_LEDGER", "1")
    out = gl.record_status_transition(
        tmp_path, SID, "S1", from_status="passed", to_status="passed",
        author_type="scheduler", writer="node_verdict")
    assert out is None
    assert gl.read_records(tmp_path, SID) == []
