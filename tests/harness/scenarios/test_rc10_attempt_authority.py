"""rc.10 A3 — one canonical execution attempt owns each graph node.

The published rc.9 run kept the first failed builder task/operator identity on
S3 after replacement work had been dispatched.  Reconciliation repeatedly
queried that stale result, so an obsolete failure remained authoritative while
newer work existed.  These regressions define the class-level boundary:

* every real execution dispatch activates one versioned node attempt;
* replacement supersedes and archives the prior attempt;
* only an exact result for the current attempt can converge it;
* graph reconciliation ignores superseded multi-task rows; and
* two launches in the same second still receive different task ids.

Evaluation assignments retain their existing repair-generation fence.  This
file concerns execution attempts only; it deliberately does not treat a later
evaluator result as a successful replacement builder result.
"""
from __future__ import annotations

import argparse
import datetime
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


HARNESS = (Path(__file__).resolve().parents[3] / 'harness')
LIB = HARNESS / "lib"
TOOLS = HARNESS / "tools"
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))

import graph_node_dispatcher as gnd  # noqa: E402
import graph_scheduler as gs  # noqa: E402
import multi_task_runner as mtr  # noqa: E402
import operator_runtime as optime  # noqa: E402
import task_lifecycle as lifecycle  # noqa: E402
import workflow_contract as workflow_contract  # noqa: E402


SID = "sprint-attempt-authority"
NODE_ID = "S3"


def _attempt(
    task_id: str,
    operator_id: str,
    *,
    sequence: int = 1,
    status: str = "submitted",
    source: str = "pm_dispatch",
) -> dict:
    return {
        "schema_version": "solar.node_attempt.v1",
        "phase": "execution",
        "sequence": sequence,
        "repair_generation": 0,
        "task_id": task_id,
        "dispatch_id": task_id,
        "operator_id": operator_id,
        "source": source,
        "logical_role": "builder",
        "status": status,
        "requires_operator_result": True,
        "sprint_id": SID,
        "node_id": NODE_ID,
        "activated_at": "2026-07-15T12:00:00Z",
        "updated_at": "2026-07-15T12:00:00Z",
    }


def _write_result(
    root: Path,
    task_id: str,
    operator_id: str,
    *,
    status: str,
    exit_code: int,
) -> Path:
    path = root / "run" / "operator-results" / operator_id / task_id / "result.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "task_id": task_id,
                "operator_id": operator_id,
                "sprint_id": SID,
                "node_id": NODE_ID,
                "status": status,
                "exit_code": exit_code,
                "started_at": "2026-07-15T12:00:00Z",
                "finished_at": "2026-07-15T12:01:00Z",
            }
        ),
        encoding="utf-8",
    )
    return path


def test_same_second_multi_task_ids_are_unique(monkeypatch: pytest.MonkeyPatch) -> None:
    class FrozenDateTime(datetime.datetime):
        @classmethod
        def now(cls, tz=None):  # noqa: ANN001
            return cls(2026, 7, 15, 12, 0, 0, tzinfo=tz)

    monkeypatch.setattr(mtr._dt, "datetime", FrozenDateTime)

    first = mtr.task_id(SID, NODE_ID)
    second = mtr.task_id(SID, NODE_ID)

    assert first != second
    assert first.startswith("mt-20260715-120000-")
    assert second.startswith("mt-20260715-120000-")


def test_execution_attempt_fields_do_not_invalidate_fixed_contract_hash() -> None:
    graph = {
        "sprint_id": SID,
        "workflow_contract_id": "test.fixed.v1",
        "workflow_contract_version": "1.0",
        "nodes": [
            {
                "id": NODE_ID,
                "goal": "verify",
                "depends_on": [],
                "task_type": "implementation",
                "status": "pending",
            }
        ],
        "node_results": {},
        "gate_results": {},
    }
    expected = workflow_contract.graph_contract_hash(graph)
    node = graph["nodes"][0]
    node.update(
        {
            "status": "dispatched",
            "updated_at": "2026-07-15T12:00:00Z",
            "assigned_to": "operator:operator-current",
            "dispatch_id": "graph-current",
            "dispatched_via": "pm_dispatch",
            "pm_task_id": "pm-current",
            "operator_id": "operator-current",
            "repair_attempts": 1,
            "execution_attempt": _attempt("pm-current", "operator-current"),
            "execution_attempt_history": [
                {
                    **_attempt("pm-old", "operator-old", status="failed"),
                    "superseded": True,
                }
            ],
            "last_operator_closeout_failure": {"reason": "operator_result_failed"},
            "dispatch_retry_reason": "operator_result_failed",
            "dispatch_failure_streak": 2,
        }
    )

    assert workflow_contract.graph_contract_hash(graph) == expected


def test_replacement_supersedes_prior_attempt_and_clears_stale_active_failure() -> None:
    node = {
        "id": NODE_ID,
        "repair_attempts": 2,
        "last_operator_closeout_failure": {"reason": "operator_result_failed"},
        "dispatch_retry_reason": "operator_result_failed",
    }
    lifecycle.activate_execution_attempt(
        node,
        task_id="pm-original",
        dispatch_id="graph-original",
        operator_id="operator-original",
        source="pm_dispatch",
        logical_role="builder",
        status="submitted",
        requires_operator_result=True,
        sprint_id=SID,
        node_id=NODE_ID,
        now="2026-07-15T12:00:00Z",
    )
    failed = lifecycle.converge_execution_attempt_result(
        node,
        {
            "task_id": "pm-original",
            "operator_id": "operator-original",
            "sprint_id": SID,
            "node_id": NODE_ID,
            "status": "failed",
            "exit_code": 1,
            "finished_at": "2026-07-15T12:01:00Z",
        },
        now="2026-07-15T12:01:00Z",
    )
    assert failed["matched"] is True

    replacement = lifecycle.activate_execution_attempt(
        node,
        task_id="pm-replacement",
        dispatch_id="graph-replacement",
        operator_id="operator-replacement",
        source="pm_dispatch",
        logical_role="builder",
        status="submitted",
        requires_operator_result=True,
        sprint_id=SID,
        node_id=NODE_ID,
        now="2026-07-15T12:02:00Z",
    )

    assert replacement["sequence"] == 2
    assert replacement["repair_generation"] == 2
    assert replacement["task_id"] == "pm-replacement"
    assert node["pm_task_id"] == "pm-replacement"
    assert node["operator_id"] == "operator-replacement"
    assert "last_operator_closeout_failure" not in node
    assert "dispatch_retry_reason" not in node
    history = node["execution_attempt_history"]
    assert len(history) == 1
    assert history[0]["task_id"] == "pm-original"
    assert history[0]["status"] == "failed"
    assert history[0]["superseded_by"] == "pm-replacement"


def test_stale_result_cannot_converge_current_replacement() -> None:
    node = {
        "id": NODE_ID,
        "execution_attempt": _attempt("pm-replacement", "operator-replacement", sequence=2),
    }

    stale = lifecycle.converge_execution_attempt_result(
        node,
        {
            "task_id": "pm-original",
            "operator_id": "operator-original",
            "sprint_id": SID,
            "node_id": NODE_ID,
            "status": "failed",
            "exit_code": 1,
        },
    )

    assert stale == {"matched": False, "reason": "task_id_mismatch"}
    assert node["execution_attempt"]["status"] == "submitted"

    current = lifecycle.converge_execution_attempt_result(
        node,
        {
            "task_id": "pm-replacement",
            "operator_id": "operator-replacement",
            "sprint_id": SID,
            "node_id": NODE_ID,
            "status": "completed",
            "exit_code": 0,
            "finished_at": "2026-07-15T12:03:00Z",
        },
    )
    assert current["matched"] is True
    assert current["ok"] is True
    assert node["execution_attempt"]["status"] == "completed"


def test_duplicate_activation_cannot_downgrade_terminal_current_attempt() -> None:
    node = {
        "id": NODE_ID,
        "execution_attempt": {
            **_attempt("pm-current", "operator-current", status="completed"),
            "exit_code": 0,
            "result_ok": True,
            "finished_at": "2026-07-15T12:03:00Z",
        },
    }

    repeated = lifecycle.activate_execution_attempt(
        node,
        task_id="pm-current",
        dispatch_id="graph-current",
        operator_id="operator-current",
        source="pm_dispatch",
        logical_role="builder",
        status="submitted",
        requires_operator_result=True,
        sprint_id=SID,
        node_id=NODE_ID,
        now="2026-07-15T12:04:00Z",
    )

    assert repeated["status"] == "completed"
    assert repeated["exit_code"] == 0
    assert repeated["result_ok"] is True
    assert repeated["finished_at"] == "2026-07-15T12:03:00Z"

    repeated_terminal = lifecycle.activate_execution_attempt(
        node,
        task_id="pm-current",
        dispatch_id="graph-current",
        operator_id="operator-current",
        source="pm_dispatch",
        logical_role="builder",
        status="failed",
        requires_operator_result=True,
        sprint_id=SID,
        node_id=NODE_ID,
        now="2026-07-15T12:05:00Z",
    )
    assert repeated_terminal["status"] == "completed"
    assert repeated_terminal["result_ok"] is True


def test_duplicate_activation_cannot_change_attempt_authority() -> None:
    node = {
        "id": NODE_ID,
        "execution_attempt": _attempt("pm-current", "operator-current"),
    }

    with pytest.raises(ValueError, match="same task_id cannot change source"):
        lifecycle.activate_execution_attempt(
            node,
            task_id="pm-current",
            dispatch_id="graph-current",
            operator_id="operator-current",
            source="direct_pane",
            logical_role="builder",
            status="dispatched",
            requires_operator_result=False,
            sprint_id=SID,
            node_id=NODE_ID,
        )

    assert node["execution_attempt"]["source"] == "pm_dispatch"
    assert node["execution_attempt"]["requires_operator_result"] is True


def test_late_duplicate_result_cannot_reverse_terminal_attempt() -> None:
    node = {
        "id": NODE_ID,
        "execution_attempt": {
            **_attempt("pm-current", "operator-current", status="completed"),
            "exit_code": 0,
            "result_ok": True,
            "finished_at": "2026-07-15T12:03:00Z",
        },
    }

    outcome = lifecycle.converge_execution_attempt_result(
        node,
        {
            "task_id": "pm-current",
            "operator_id": "operator-current",
            "sprint_id": SID,
            "node_id": NODE_ID,
            "status": "failed",
            "exit_code": 1,
            "finished_at": "2026-07-15T12:06:00Z",
        },
    )

    assert outcome == {
        "matched": False,
        "reason": "attempt_already_terminal",
        "status": "completed",
        "task_id": "pm-current",
    }
    assert node["execution_attempt"]["status"] == "completed"
    assert node["execution_attempt"]["exit_code"] == 0
    assert node["execution_attempt"]["result_ok"] is True


def test_builder_result_gate_uses_current_attempt_not_legacy_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(gnd, "HARNESS_DIR", tmp_path)
    node = {
        "id": NODE_ID,
        "dispatched_via": "pm_dispatch",
        "pm_task_id": "pm-original",
        "operator_id": "operator-original",
        "execution_attempt": _attempt("pm-replacement", "operator-replacement", sequence=2),
    }
    _write_result(
        tmp_path,
        "pm-original",
        "operator-original",
        status="failed",
        exit_code=1,
    )

    pending = gnd._builder_operator_result_gate(SID, node)
    assert pending["reason"] == "builder_operator_result_pending"
    assert pending["task_id"] == "pm-replacement"

    _write_result(
        tmp_path,
        "pm-replacement",
        "operator-replacement",
        status="completed",
        exit_code=0,
    )
    passed = gnd._builder_operator_result_gate(SID, node)
    assert passed["ok"] is True
    assert passed["task_id"] == "pm-replacement"


def test_malformed_declared_attempt_cannot_resurrect_legacy_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(gnd, "HARNESS_DIR", tmp_path)
    node = {
        "id": NODE_ID,
        "dispatched_via": "pm_dispatch",
        "pm_task_id": "pm-original",
        "operator_id": "operator-original",
        "execution_attempt": {
            **_attempt("pm-replacement", "operator-replacement", sequence=2),
            "schema_version": "corrupt-schema",
        },
    }
    _write_result(
        tmp_path,
        "pm-original",
        "operator-original",
        status="failed",
        exit_code=1,
    )

    blocked = gnd._builder_operator_result_gate(SID, node)

    assert blocked["ok"] is False
    assert blocked["complete"] is False
    assert blocked["reason"] == "builder_execution_attempt_invalid"


def test_active_multi_task_status_ignores_superseded_task_and_converged_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = tmp_path / "run" / "multi-task"
    monkeypatch.setattr(gnd, "MULTI_TASK_RUN_DIR", run_dir)
    node = {
        "id": NODE_ID,
        "execution_attempt": _attempt(
            "mt-current",
            "operator-current",
            sequence=2,
            source="multi_task_operatord",
        ),
    }
    for task_id, updated_at in (
        ("mt-superseded", "2026-07-15T12:02:00Z"),
        ("mt-current", "2026-07-15T12:01:00Z"),
    ):
        status_path = run_dir / task_id / "status.json"
        status_path.parent.mkdir(parents=True, exist_ok=True)
        status_path.write_text(
            json.dumps(
                {
                    "id": task_id,
                    "sprint_id": SID,
                    "node_id": NODE_ID,
                    "operator_id": "operator-current",
                    "status": "submitted",
                    "updated_at": updated_at,
                }
            ),
            encoding="utf-8",
        )

    active = gnd._active_multi_task_status_for(SID, NODE_ID, node)
    assert active is not None
    assert active["id"] == "mt-current"

    result = _write_result(
        tmp_path,
        "mt-current",
        "operator-current",
        status="completed",
        exit_code=0,
    )
    status_path = run_dir / "mt-current" / "status.json"
    payload = json.loads(status_path.read_text(encoding="utf-8"))
    payload["result_path"] = str(result)
    status_path.write_text(json.dumps(payload), encoding="utf-8")

    assert gnd._active_multi_task_status_for(SID, NODE_ID, node) is None


def test_terminal_legacy_multi_task_status_converges_current_attempt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = tmp_path / "run" / "multi-task"
    monkeypatch.setattr(gnd, "MULTI_TASK_RUN_DIR", run_dir)
    node = {
        "id": NODE_ID,
        "execution_attempt": {
            **_attempt(
                "mt-current",
                "test-builder",
                source="multi_task_tmux",
            ),
            "requires_operator_result": False,
        },
    }
    status_path = run_dir / "mt-current" / "status.json"
    status_path.parent.mkdir(parents=True)
    status_path.write_text(
        json.dumps(
            {
                "id": "mt-current",
                "sprint_id": SID,
                "node_id": NODE_ID,
                "operator_id": "test-builder",
                "status": "completed",
                "exit_code": 0,
                "updated_at": "2026-07-15T12:05:00Z",
            }
        ),
        encoding="utf-8",
    )

    assert gnd._active_multi_task_status_for(SID, NODE_ID, node) is None
    assert node["execution_attempt"]["status"] == "completed"
    assert node["execution_attempt"]["result_ok"] is True


def test_operator_result_writer_converges_only_current_graph_attempt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = tmp_path / "harness"
    sprints = harness / "sprints"
    sprints.mkdir(parents=True)
    graph_path = sprints / f"{SID}.task_graph.json"
    graph_path.write_text(
        json.dumps(
            {
                "sprint_id": SID,
                "nodes": [
                    {
                        "id": NODE_ID,
                        "status": "dispatched",
                        "depends_on": [],
                        "execution_attempt": _attempt("pm-current", "operator-current"),
                    }
                ],
                "node_results": {NODE_ID: {"status": "dispatched"}},
                "gate_results": {},
                "required_gates": [],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(optime, "HARNESS_DIR", harness)
    monkeypatch.setattr(optime, "OPERATOR_RESULTS_DIR", harness / "run" / "operator-results")
    monkeypatch.setattr(optime, "_route_sprints_dir", lambda: sprints)
    monkeypatch.setattr(gs, "HARNESS_DIR", harness)
    monkeypatch.setattr(gs, "SPRINTS_DIR", sprints)

    optime.write_result(
        "operator-current",
        "pm-current",
        SID,
        NODE_ID,
        "completed",
        0,
        "2026-07-15T12:00:00Z",
        "2026-07-15T12:03:00Z",
        "worker complete",
    )

    persisted = json.loads(graph_path.read_text(encoding="utf-8"))
    attempt = persisted["nodes"][0]["execution_attempt"]
    assert attempt["task_id"] == "pm-current"
    assert attempt["status"] == "completed"
    assert attempt["exit_code"] == 0


def test_pm_graph_marker_activates_canonical_attempt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = importlib.util.spec_from_file_location("rc10_pm_dispatch", TOOLS / "pm_dispatch.py")
    assert spec is not None and spec.loader is not None
    pm_dispatch = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pm_dispatch)

    sprints = tmp_path / "sprints"
    sprints.mkdir()
    graph_path = sprints / f"{SID}.task_graph.json"
    graph_path.write_text(
        json.dumps(
            {
                "sprint_id": SID,
                "nodes": [{"id": NODE_ID, "status": "pending", "depends_on": []}],
                "node_results": {},
                "gate_results": {},
                "required_gates": [],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(pm_dispatch, "SPRINTS_DIR", sprints)
    monkeypatch.setattr(pm_dispatch, "HARNESS_DIR", tmp_path)
    monkeypatch.setattr(gs, "SPRINTS_DIR", sprints)

    marked = pm_dispatch._mark_graph_node_pm_dispatched(
        {"graph": str(graph_path), "sprint_id": SID, "node_id": NODE_ID},
        {"task_id": "pm-current", "operator_id": "operator-current"},
    )

    assert marked["ok"] is True
    persisted = json.loads(graph_path.read_text(encoding="utf-8"))
    attempt = persisted["nodes"][0]["execution_attempt"]
    assert attempt["schema_version"] == "solar.node_attempt.v1"
    assert attempt["task_id"] == "pm-current"
    assert attempt["operator_id"] == "operator-current"
    assert attempt["requires_operator_result"] is True


def test_multi_task_launch_persists_canonical_legacy_attempt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = tmp_path / "harness"
    sprints = harness / "sprints"
    run_dir = harness / "run" / "multi-task"
    sprints.mkdir(parents=True)
    graph_path = sprints / f"{SID}.task_graph.json"
    graph = {
        "sprint_id": SID,
        "nodes": [{"id": NODE_ID, "status": "pending", "depends_on": [], "goal": "verify"}],
        "node_results": {},
        "gate_results": {},
        "required_gates": [],
    }
    graph_path.write_text(json.dumps(graph), encoding="utf-8")

    profile = {
        "name": "test-builder",
        "role": "builder",
        "persona": "builder",
        "backend": "command",
        "model": "test-model",
        "command": "true",
        "operator_id": "",
    }
    monkeypatch.setattr(mtr, "HARNESS_DIR", harness)
    monkeypatch.setattr(mtr, "SPRINTS_DIR", sprints)
    monkeypatch.setattr(mtr, "RUN_DIR", run_dir)
    monkeypatch.setattr(mtr, "OPERATORD_SUBMIT_ENABLED", False)
    monkeypatch.setattr(mtr, "_plan_validator_launch_refusal", lambda _graph: None)
    monkeypatch.setattr(mtr, "select_profile", lambda *_args, **_kwargs: profile)
    monkeypatch.setattr(mtr, "capability_for_profile", lambda _profile: {"provider": "test", "status": "ready"})
    monkeypatch.setattr(mtr, "build_dispatch_text", lambda *_args, **_kwargs: "# dispatch\n")
    monkeypatch.setattr(mtr, "tmux_start", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mtr, "set_last_launch", lambda: None)
    monkeypatch.setattr(mtr, "_record_node_attribution", lambda *_args, **_kwargs: None)

    payload = mtr.launch_node(
        graph_path,
        graph,
        graph["nodes"][0],
        argparse.Namespace(profile="", model="", backend=""),
        dry_run=False,
    )

    persisted = json.loads(graph_path.read_text(encoding="utf-8"))
    attempt = persisted["nodes"][0]["execution_attempt"]
    assert attempt["task_id"] == payload["id"]
    assert attempt["source"] == "multi_task_tmux"
    assert attempt["status"] == "dispatched"
    assert attempt["requires_operator_result"] is False
    assert persisted["nodes"][0]["dispatch_id"] == payload["id"]


def test_direct_pane_attempt_supersedes_stale_pm_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sprints = tmp_path / "sprints"
    sprints.mkdir()
    graph_path = sprints / f"{SID}.task_graph.json"
    node = {
        "id": NODE_ID,
        "status": "pending",
        "depends_on": [],
        "pm_task_id": "pm-stale",
        "operator_id": "operator-stale",
        "dispatched_via": "pm_dispatch",
        "last_operator_closeout_failure": {"reason": "operator_result_failed"},
        "execution_attempt": _attempt(
            "pm-stale",
            "operator-stale",
            status="failed",
        ),
    }
    graph_path.write_text(
        json.dumps(
            {
                "sprint_id": SID,
                "nodes": [node],
                "node_results": {},
                "gate_results": {},
                "required_gates": [],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(gnd, "SPRINTS_DIR", sprints)
    monkeypatch.setattr(gs, "SPRINTS_DIR", sprints)

    assert gnd._activate_direct_pane_attempt(
        str(graph_path),
        NODE_ID,
        sid=SID,
        pane="solar-test:0.1",
        dispatch_id="graph-replacement",
    ) is True

    persisted = json.loads(graph_path.read_text(encoding="utf-8"))
    updated = persisted["nodes"][0]
    assert updated["execution_attempt"]["task_id"] == "graph-replacement"
    assert updated["execution_attempt"]["source"] == "direct_pane"
    assert updated["execution_attempt_history"][0]["task_id"] == "pm-stale"
    assert "pm_task_id" not in updated
    assert "operator_id" not in updated
    assert "last_operator_closeout_failure" not in updated


def test_failed_current_attempt_is_retained_until_replacement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    node = {
        "id": NODE_ID,
        "status": "dispatched",
        "assigned_to": "operator:operator-current",
        "dispatch_id": "graph-current",
        "execution_attempt": _attempt("pm-current", "operator-current"),
    }
    graph = {
        "sprint_id": SID,
        "nodes": [node],
        "node_results": {NODE_ID: {"status": "dispatched"}},
    }
    monkeypatch.setattr(gnd, "release_lease", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(gnd, "_ledger_transition", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(gnd, "_append_dispatch_ledger", lambda *_args, **_kwargs: None)

    outcome = gnd._requeue_node_after_operator_closeout(
        SID,
        NODE_ID,
        node,
        graph,
        "dispatched",
        {
            "reason": "operator_result_failed",
            "operator_status": "failed",
            "operator_id": "operator-current",
            "exit_code": 1,
        },
    )

    assert outcome["status"] == "pending"
    assert node["status"] == "pending"
    assert node["execution_attempt"]["status"] == "failed"
    assert node["execution_attempt"]["closeout_failure"]["exit_code"] == 1
    assert node["last_operator_closeout_failure"]["reason"] == "operator_result_failed"


def test_operator_pool_success_without_task_identity_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sprints = tmp_path / "sprints"
    sprints.mkdir()
    graph_path = sprints / f"{SID}.task_graph.json"
    graph_path.write_text(
        json.dumps(
            {
                "sprint_id": SID,
                "nodes": [
                    {
                        "id": NODE_ID,
                        "status": "assigned",
                        "depends_on": [],
                        "assigned_to": "operator-pool:builder.0",
                        "dispatch_id": "graph-current",
                    }
                ],
                "node_results": {},
                "gate_results": {},
                "required_gates": [],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(gnd, "HARNESS_DIR", tmp_path)
    monkeypatch.setattr(gnd, "SPRINTS_DIR", sprints)
    monkeypatch.setattr(gnd, "_builder_operator_pool_enabled", lambda: True)
    monkeypatch.setattr(gnd, "_builder_operator_pool_allowed_for_pane", lambda _pane: True)
    monkeypatch.setattr(gnd, "build_dispatch_text", lambda *_args, **_kwargs: "# dispatch\n")
    monkeypatch.setattr(gnd, "_inject_dispatch_context", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(gnd, "_broker_env", lambda _sid: {})
    monkeypatch.setattr(
        gnd.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0,
            stdout="operator = operator-current\ndispatch = dispatch.json\n",
            stderr="",
        ),
    )
    monkeypatch.setattr(gnd, "release_lease", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(gnd, "_write_submit_ack", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(gnd, "_append_dispatch_ledger", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(gnd, "_record_node_attribution", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(gnd, "_append_event", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(gnd, "_ledger_transition", lambda *_args, **_kwargs: None)

    result = gnd._submit_builder_to_operator_pool(
        item={"payload": {}},
        payload={},
        sid=SID,
        node={"id": NODE_ID, "required_capabilities": []},
        node_id=NODE_ID,
        graph_path=str(graph_path),
        pane="operator-pool:builder.0",
        dispatch_id="graph-current",
        dry_run=False,
    )

    assert result["ok"] is False
    assert result["reason"] == "operator_pool_identity_missing"
    assert result["suppress_fallback"] is True
    persisted = gnd.load_graph(graph_path)
    updated = persisted["nodes"][0]
    assert updated["status"] == "needs_human_review"
    assert updated["execution_attempt_error"]["reason"] == "operator_pool_task_id_missing"
    assert "execution_attempt" not in updated
    gate = gnd._builder_operator_result_gate(SID, updated)
    assert gate["ok"] is False
    assert gate["reason"] == "builder_execution_attempt_invalid"


def test_untracked_operator_pool_submission_never_falls_back_to_second_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph_path = tmp_path / f"{SID}.task_graph.json"
    graph_path.write_text(
        json.dumps(
            {
                "sprint_id": SID,
                "nodes": [
                    {
                        "id": NODE_ID,
                        "status": "assigned",
                        "depends_on": [],
                        "assigned_to": "operator-pool:builder.0",
                        "dispatch_id": "graph-current",
                    }
                ],
                "node_results": {},
                "gate_results": {},
                "required_gates": [],
            }
        ),
        encoding="utf-8",
    )
    pool_failure = {
        "ok": False,
        "reason": "operator_pool_identity_missing",
        "suppress_fallback": True,
        "graph_updated": True,
    }
    fallback_calls: list[str] = []
    monkeypatch.setattr(gnd, "_plan_validator_enabled", lambda: False)
    monkeypatch.setattr(gnd, "_prepare_human_search_handoff", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(gnd, "_submit_builder_to_operator_pool", lambda **_kwargs: pool_failure)
    monkeypatch.setattr(
        gnd,
        "_send_to_pane",
        lambda *_args, **_kwargs: fallback_calls.append("sent") or True,
    )
    monkeypatch.setattr(
        gnd,
        "enqueue",
        lambda *_args, **_kwargs: fallback_calls.append("requeued") or {"ok": True},
    )
    monkeypatch.setattr(gnd, "_append_dispatch_ledger", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(gnd, "_mark_graph_node", lambda *_args, **_kwargs: True)

    result = gnd.dispatch_queue_item(
        {
            "intent": f"graph_node|node_id={NODE_ID}",
            "priority": 80,
            "payload": {
                "sprint_id": SID,
                "node": {"id": NODE_ID, "status": "assigned"},
                "assignment": {"pane": "operator-pool:builder.0"},
                "dispatch_id": "graph-current",
                "graph": str(graph_path),
            },
        },
        dry_run=False,
    )

    assert result == pool_failure
    assert fallback_calls == []
