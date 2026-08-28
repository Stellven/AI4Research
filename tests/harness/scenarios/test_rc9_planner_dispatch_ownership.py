"""RC9 planner dispatch must have one durable, recoverable owner.

The installed Codex UI run exposed a real race: the coordinator started a
legacy pane dispatch one second before the autopilot's operator-pool task
became visible.  The first ``prd_ready`` status must therefore carry the
operator-pool ownership claim; observing only later inbox/status files is too
late.  These tests also pin failure recovery so a dead claim cannot stall a
sprint forever.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path

import pytest


_HARNESS = (Path(__file__).resolve().parents[3] / 'harness')
_COORDINATOR = _HARNESS / "coordinator.sh"
_PM_DISPATCH = _HARNESS / "tools" / "pm_dispatch.py"


def _load_pm_dispatch():
    spec = importlib.util.spec_from_file_location("rc9_pm_dispatch_claim", _PM_DISPATCH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _iso_after(seconds: int) -> str:
    return (
        dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=seconds)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")


def _source_coordinator(
    harness: Path,
    script: str,
    *,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    merged = {
        **os.environ,
        "COORD_NO_MAIN": "1",
        "HARNESS_DIR": str(harness),
        "SOLAR_CODEX_ALLOW_PM_OPERATOR_DISPATCH": "1",
    }
    if env:
        merged.update(env)
    return subprocess.run(
        ["bash", "-c", f'source "$1"; {script}', "bash", str(_COORDINATOR)],
        env=merged,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _minimal_harness(tmp_path: Path) -> Path:
    harness = tmp_path / "harness"
    for rel in (
        "sprints",
        "run/pm-inbox",
        "run/operator-status",
        "run/operator-results/op",
    ):
        (harness / rel).mkdir(parents=True, exist_ok=True)
    (harness / "PLANNER-INBOX.md").write_text("", encoding="utf-8")
    return harness


def test_compiled_prd_ready_status_claims_operator_pool_before_dispatch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    pm_dispatch = _load_pm_dispatch()
    sprints = tmp_path / "sprints"
    sprints.mkdir()
    monkeypatch.setattr(pm_dispatch, "SPRINTS_DIR", sprints)
    monkeypatch.setenv("SOLAR_PANE_RUNTIME", "codex")
    monkeypatch.setenv("SOLAR_CODEX_ALLOW_PM_OPERATOR_DISPATCH", "1")

    status_path = pm_dispatch.ensure_compiled_sprint_status(
        "sprint-claim-before-visible",
        "Planner ownership fixture",
        "The first visible status must already name its dispatch owner.",
    )

    status = json.loads(status_path.read_text(encoding="utf-8"))
    claim = status["planner_dispatch_claim"]
    assert claim["owner"] == "operator_pool"
    assert claim["state"] == "pending"
    assert claim["claimed_at"]
    assert dt.datetime.fromisoformat(claim["expires_at"].replace("Z", "+00:00")) > dt.datetime.now(dt.timezone.utc)


def test_pending_operator_pool_claim_suppresses_legacy_planner_dispatch(tmp_path: Path) -> None:
    harness = _minimal_harness(tmp_path)
    sid = "sprint-exact-planner-race"
    status_path = harness / "sprints" / f"{sid}.status.json"
    prd_path = harness / "sprints" / f"{sid}.prd.md"
    dispatch_log = tmp_path / "legacy-dispatch-called"
    status_path.write_text(
        json.dumps(
            {
                "id": sid,
                "status": "drafting",
                "phase": "prd_ready",
                "handoff_to": "planner",
                "planner_dispatch_claim": {
                    "owner": "operator_pool",
                    "state": "pending",
                    "claimed_at": _iso_after(-1),
                    "expires_at": _iso_after(120),
                },
            }
        ),
        encoding="utf-8",
    )
    prd_path.write_text("# PRD\n\nValid fixture.\n", encoding="utf-8")

    script = r'''
pm_requirements_file() { printf '%s\n' "$REQ_FILE"; }
workflow_guard_route_role() { printf '%s\n' planner; }
pm_operator_role_pool_task_seen() { return 1; }
validate_doc() { return 0; }
drafting_flow_marked() { return 1; }
drafting_retry_blocked() { return 1; }
generate_dispatch() { :; }
append_dispatch() { :; }
dispatch_to_planner() { printf '%s\n' called > "$DISPATCH_LOG"; return 0; }
mark_drafting_flow() { :; }
emit_event() { :; }
rollback_state_cache() { :; }
handle_drafting "$SID" "$STATUS_FILE"
[[ ! -e "$DISPATCH_LOG" ]]
'''
    result = _source_coordinator(
        harness,
        script,
        env={
            "SID": sid,
            "STATUS_FILE": str(status_path),
            "REQ_FILE": str(prd_path),
            "DISPATCH_LOG": str(dispatch_log),
        },
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert not dispatch_log.exists()


@pytest.mark.parametrize(
    ("heartbeat_offset", "legacy_expected"),
    [(0, False), (-600, True)],
    ids=("live-worker-suppresses-duplicate", "stale-worker-allows-recovery"),
)
def test_operator_liveness_controls_dispatch_after_planner_outputs_appear(
    tmp_path: Path,
    heartbeat_offset: int,
    legacy_expected: bool,
) -> None:
    """A long planner may write artifacts before its final status handoff.

    The run-3 live red hit this exact interval after the bounded birth claim
    expired: design/plan/graph existed, the submitted PM planner task was still
    running, and the coordinator incorrectly launched the legacy pane planner.
    """
    harness = _minimal_harness(tmp_path)
    sid = "sprint-planner-artifacts-before-handoff"
    task_id = f"pm-{sid}-N0-cafefeed"
    sprints = harness / "sprints"
    status_path = sprints / f"{sid}.status.json"
    prd_path = sprints / f"{sid}.prd.md"
    dispatch_log = tmp_path / "legacy-dispatch-called"

    status_path.write_text(
        json.dumps(
            {
                "id": sid,
                "status": "drafting",
                "phase": "prd_ready",
                "handoff_to": "planner",
                "planner_dispatch_claim": {
                    "owner": "operator_pool",
                    "state": "submitted",
                    "claimed_at": _iso_after(-600),
                    "expires_at": _iso_after(-1),
                    "task_id": task_id,
                },
            }
        ),
        encoding="utf-8",
    )
    prd_path.write_text("# PRD\n\nValid fixture.\n", encoding="utf-8")
    (sprints / f"{sid}.design.md").write_text("# Design\n", encoding="utf-8")
    (sprints / f"{sid}.plan.md").write_text("# Plan\n", encoding="utf-8")
    (sprints / f"{sid}.task_graph.json").write_text(
        json.dumps({"nodes": [{"id": "S1", "status": "pending"}]}),
        encoding="utf-8",
    )
    (harness / "run" / "pm-inbox" / f"{task_id}.json").write_text(
        json.dumps(
            {
                "task_id": task_id,
                "sprint_id": sid,
                "requested_role": "planner",
                "status": "submitted",
            }
        ),
        encoding="utf-8",
    )
    (harness / "run" / "operator-status" / "codex-planner.json").write_text(
        json.dumps(
            {
                "current_task_id": task_id,
                "runtime_state": "running",
                "heartbeat_at": _iso_after(heartbeat_offset),
            }
        ),
        encoding="utf-8",
    )

    script = r'''
pm_requirements_file() { printf '%s\n' "$REQ_FILE"; }
workflow_guard_route_role() { printf '%s\n' planner; }
validate_doc() { return 0; }
drafting_flow_marked() { return 1; }
drafting_retry_blocked() { return 1; }
generate_dispatch() { :; }
append_dispatch() { :; }
dispatch_to_planner() { printf '%s\n' called > "$DISPATCH_LOG"; return 0; }
mark_drafting_flow() { :; }
emit_event() { :; }
rollback_state_cache() { :; }
handle_drafting "$SID" "$STATUS_FILE"
'''
    result = _source_coordinator(
        harness,
        script,
        env={
            "SID": sid,
            "STATUS_FILE": str(status_path),
            "REQ_FILE": str(prd_path),
            "DISPATCH_LOG": str(dispatch_log),
        },
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert dispatch_log.exists() is legacy_expected


def test_terminal_pm_record_and_result_do_not_reclaim_planner_ownership(tmp_path: Path) -> None:
    harness = _minimal_harness(tmp_path)
    sid = "sprint-failed-role-pool"
    task_id = f"pm-{sid}-N0-deadbeef"
    record = harness / "run" / "pm-inbox" / f"{task_id}.json"
    record.write_text(
        json.dumps(
            {
                "task_id": task_id,
                "requested_role": "planner",
                "status": "failed_submit_exception",
            }
        ),
        encoding="utf-8",
    )
    (harness / "run" / "operator-results" / "op" / task_id).mkdir()

    failed = _source_coordinator(
        harness,
        f'if pm_operator_role_pool_task_seen "{sid}" planner; then echo active; else echo released; fi',
    )
    assert failed.returncode == 0, failed.stderr
    assert failed.stdout.strip() == "released"

    record.write_text(
        json.dumps(
            {
                "task_id": task_id,
                "requested_role": "planner",
                "status": "submitted",
            }
        ),
        encoding="utf-8",
    )
    submitted = _source_coordinator(
        harness,
        f'if pm_operator_role_pool_task_seen "{sid}" planner; then echo active; else echo released; fi',
    )
    assert submitted.returncode == 0, submitted.stderr
    assert submitted.stdout.strip() == "active"


def test_newest_successful_planner_result_compiles_despite_older_pending_retry(
    tmp_path: Path,
) -> None:
    """An abandoned older submission must not veto a newer successful plan.

    The live dashboard hit this after a no-capacity retry remained in pm-inbox:
    planner_operator_gate correctly selected the newer durable success, but the
    drafting flow separately treated the older pending record as ownership and
    skipped certification.  The coordinator then fell back to Planner again.
    """
    harness = _minimal_harness(tmp_path)
    (harness / "lib").mkdir(exist_ok=True)
    shutil.copy2(_HARNESS / "lib" / "planner_operator_gate.py", harness / "lib")
    sid = "sprint-newer-planner-success"
    old_task = f"pm-{sid}-N0-00000001"
    new_task = f"pm-{sid}-N0-00000002"
    sprints = harness / "sprints"
    status_path = sprints / f"{sid}.status.json"
    prd_path = sprints / f"{sid}.prd.md"
    compile_marker = tmp_path / "compiled"
    dispatch_marker = tmp_path / "legacy-dispatch"

    status_path.write_text(
        json.dumps(
            {
                "id": sid,
                "status": "drafting",
                "phase": "prd_ready",
                "handoff_to": "planner",
                "planner_dispatch_claim": {
                    "owner": "operator_pool",
                    "state": "failed",
                    "expires_at": _iso_after(-1),
                },
            }
        ),
        encoding="utf-8",
    )
    prd_path.write_text("# PRD\n\nValid fixture.\n", encoding="utf-8")
    for suffix, content in (
        ("design.md", "# Design\n"),
        ("plan.md", "# Plan\n"),
        ("task_graph.json", json.dumps({"nodes": [{"id": "N1"}]})),
    ):
        (sprints / f"{sid}.{suffix}").write_text(content, encoding="utf-8")

    old_record = harness / "run" / "pm-inbox" / f"{old_task}.json"
    old_record.write_text(
        json.dumps(
            {
                "task_id": old_task,
                "sprint_id": sid,
                "requested_role": "planner",
                "status": "submitted",
            }
        ),
        encoding="utf-8",
    )
    old_time = dt.datetime.now().timestamp() - 10
    os.utime(old_record, (old_time, old_time))

    (harness / "run" / "pm-inbox" / f"{new_task}.json").write_text(
        json.dumps(
            {
                "task_id": new_task,
                "sprint_id": sid,
                "requested_role": "planner",
                "status": "completed",
            }
        ),
        encoding="utf-8",
    )
    result_dir = harness / "run" / "operator-results" / "op" / new_task
    result_dir.mkdir(parents=True)
    (result_dir / "result.json").write_text(
        json.dumps({"task_id": new_task, "status": "completed", "exit_code": 0}),
        encoding="utf-8",
    )

    script = r'''
pm_requirements_file() { printf '%s\n' "$REQ_FILE"; }
workflow_guard_route_role() { [[ -e "$COMPILE_MARKER" ]] && printf '%s\n' builder || printf '%s\n' planner; }
annotate_requirement_matrix_for_planning() { return 0; }
compile_generic_plan_graph() { : > "$COMPILE_MARKER"; return 0; }
runtime_status_transition() { return 0; }
validate_doc() { return 0; }
drafting_flow_marked() { return 1; }
drafting_retry_blocked() { return 1; }
generate_dispatch() { :; }
append_dispatch() { :; }
dispatch_to_planner() { : > "$DISPATCH_MARKER"; return 0; }
mark_drafting_flow() { :; }
emit_event() { :; }
rollback_state_cache() { :; }
handle_drafting "$SID" "$STATUS_FILE"
[[ -e "$COMPILE_MARKER" && ! -e "$DISPATCH_MARKER" ]]
'''
    result = _source_coordinator(
        harness,
        script,
        env={
            "SID": sid,
            "STATUS_FILE": str(status_path),
            "REQ_FILE": str(prd_path),
            "COMPILE_MARKER": str(compile_marker),
            "DISPATCH_MARKER": str(dispatch_marker),
        },
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert compile_marker.exists()
    assert not dispatch_marker.exists()


def test_registered_live_planner_process_is_strong_ownership_evidence(
    tmp_path: Path,
) -> None:
    harness = _minimal_harness(tmp_path)
    (harness / "lib").mkdir()
    registry_module = _HARNESS / "lib" / "run_process_registry.py"
    shutil.copy2(registry_module, harness / "lib" / registry_module.name)
    sid = "sprint-registry-owned-planner"
    task_id = f"pm-{sid}-N0-acde1234"
    worker = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(300)"],
        start_new_session=True,
    )
    try:
        registered = subprocess.run(
            [
                sys.executable,
                str(registry_module),
                "register",
                "--run-id",
                "harness",
                "--role",
                "operator-task-child",
                "--pid",
                str(worker.pid),
                "--meta",
                json.dumps({"task_id": task_id}),
            ],
            env={**os.environ, "HARNESS_DIR": str(harness)},
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert registered.returncode == 0, registered.stderr

        result = _source_coordinator(
            harness,
            f'if pm_operator_role_pool_task_live "{sid}" planner; then echo live; else echo absent; fi',
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "live"
    finally:
        try:
            os.killpg(worker.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        worker.wait(timeout=5)


def test_expired_operator_pool_claim_allows_legacy_recovery(tmp_path: Path) -> None:
    harness = _minimal_harness(tmp_path)
    status_path = harness / "sprints" / "sprint-expired.status.json"
    status_path.write_text(
        json.dumps(
            {
                "planner_dispatch_claim": {
                    "owner": "operator_pool",
                    "state": "pending",
                    "claimed_at": _iso_after(-300),
                    "expires_at": _iso_after(-1),
                }
            }
        ),
        encoding="utf-8",
    )

    result = _source_coordinator(
        harness,
        f'if pm_operator_role_pool_claim_active "{status_path}" planner; then echo active; else echo expired; fi',
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "expired"


def test_failed_submission_releases_planner_claim_without_waiting_for_ttl(tmp_path: Path) -> None:
    harness = _minimal_harness(tmp_path)
    (harness / "lib").mkdir(exist_ok=True)
    shutil.copy2(_HARNESS / "lib" / "planner_operator_gate.py", harness / "lib")
    sid = "sprint-no-capacity"
    task_id = f"pm-{sid}-N0-acde0001"
    (harness / "sprints" / f"{sid}.status.json").write_text(
        json.dumps(
            {
                "id": sid,
                "status": "drafting",
                "planner_dispatch_claim": {
                    "owner": "operator_pool",
                    "state": "failed",
                    "task_id": task_id,
                    "expires_at": _iso_after(180),
                },
            }
        ),
        encoding="utf-8",
    )
    (harness / "run" / "pm-inbox" / f"{task_id}.json").write_text(
        json.dumps(
            {
                "task_id": task_id,
                "requested_role": "planner",
                "status": "failed_no_dispatchable_operator",
                "failure_reason": "no_dispatchable_operator_for_role: planner",
            }
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(harness / "lib" / "planner_operator_gate.py"),
            "state",
            sid,
            "--harness-dir",
            str(harness),
            "--json",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["state"] == "failed"
    assert payload["reason"] == "planner_submission_failed_before_lease"


def test_coordinator_retries_failed_drafting_without_fingerprint_change() -> None:
    source = _COORDINATOR.read_text(encoding="utf-8")

    assert "startup recovery: replaying failed Planner dispatch" in source
    assert "retrying without a status-fingerprint change" in source
    assert 'drafting_retry_blocked "$sid" "planner_operator_retry"' in source


def test_coordinator_certifies_completed_drafting_without_fingerprint_change() -> None:
    source = _COORDINATOR.read_text(encoding="utf-8")

    assert '[[ "$drafting_planner_state" == "completed" ]]' in source
    assert 'planner_artifacts_present "$sid"' in source
    assert "certifying without a status-fingerprint change" in source


def test_active_gate_waits_for_planner_result_without_certifying_or_rolling_back(
    tmp_path: Path,
) -> None:
    harness = _minimal_harness(tmp_path)
    (harness / "lib").mkdir(exist_ok=True)
    shutil.copy2(_HARNESS / "lib" / "planner_operator_gate.py", harness / "lib")
    sid = "sprint-planner-candidate-still-running"
    task_id = f"pm-{sid}-N0-acde9876"
    sprints = harness / "sprints"
    status_path = sprints / f"{sid}.status.json"
    status_path.write_text(
        json.dumps(
            {
                "id": sid,
                "status": "active",
                "phase": "planning_complete",
                "handoff_to": "builder_main",
                "planner_dispatch_claim": {
                    "owner": "operator_pool",
                    "state": "submitted",
                    "task_id": task_id,
                    "expires_at": _iso_after(120),
                },
            }
        ),
        encoding="utf-8",
    )
    (harness / "run" / "pm-inbox" / f"{task_id}.json").write_text(
        json.dumps(
            {
                "task_id": task_id,
                "sprint_id": sid,
                "requested_role": "planner",
                "status": "submitted",
            }
        ),
        encoding="utf-8",
    )
    marker = tmp_path / "forbidden-action"
    script = r'''
log() { :; }
workflow_guard_route_role() { printf '%s\n' planner; }
workflow_guard_violations() { printf '%s\n' '[]'; }
compile_generic_plan_graph() { printf '%s\n' compile > "$MARKER"; return 0; }
runtime_status_transition() { printf '%s\n' rollback > "$MARKER"; return 0; }
dispatch_to_planner() { printf '%s\n' dispatch > "$MARKER"; return 0; }
if gate_check "$SID" active; then exit 91; fi
[[ ! -e "$MARKER" ]]
'''
    result = _source_coordinator(
        harness,
        script,
        env={"SID": sid, "MARKER": str(marker)},
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert not marker.exists()


def test_planner_gate_selects_new_retry_after_claimed_task_failed(tmp_path: Path) -> None:
    harness = _minimal_harness(tmp_path)
    (harness / "lib").mkdir(exist_ok=True)
    shutil.copy2(_HARNESS / "lib" / "planner_operator_gate.py", harness / "lib")
    sid = "sprint-planner-retry-selection"
    old_task = f"pm-{sid}-N0-00000001"
    new_task = f"pm-{sid}-N0-00000002"
    status_path = harness / "sprints" / f"{sid}.status.json"
    status_path.write_text(
        json.dumps(
            {
                "id": sid,
                "status": "drafting",
                "planner_dispatch_claim": {
                    "owner": "operator_pool",
                    "state": "submitted",
                    "task_id": old_task,
                    "expires_at": _iso_after(120),
                },
            }
        ),
        encoding="utf-8",
    )
    old_record = harness / "run" / "pm-inbox" / f"{old_task}.json"
    old_record.write_text(
        json.dumps({"task_id": old_task, "requested_role": "planner", "status": "failed_missing_pm_result"}),
        encoding="utf-8",
    )
    old_result_dir = harness / "run" / "operator-results" / "op" / old_task
    old_result_dir.mkdir(parents=True)
    (old_result_dir / "result.json").write_text(
        json.dumps({"task_id": old_task, "status": "draining", "exit_code": -15}),
        encoding="utf-8",
    )
    new_record = harness / "run" / "pm-inbox" / f"{new_task}.json"
    new_record.write_text(
        json.dumps({"task_id": new_task, "requested_role": "planner", "status": "submitted"}),
        encoding="utf-8",
    )
    old_time = dt.datetime.now().timestamp() - 10
    os.utime(old_record, (old_time, old_time))

    result = subprocess.run(
        [
            sys.executable,
            str(harness / "lib" / "planner_operator_gate.py"),
            "state",
            sid,
            "--harness-dir",
            str(harness),
            "--json",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["state"] == "pending"
    assert payload["task_id"] == new_task


def test_failed_planner_retry_uses_solar_pm_dispatch(tmp_path: Path) -> None:
    harness = _minimal_harness(tmp_path)
    (harness / "tools").mkdir()
    call_log = tmp_path / "pm-dispatch-call.json"
    (harness / "tools" / "pm_dispatch.py").write_text(
        "import json, os, sys\n"
        "json.dump(sys.argv[1:], open(os.environ['CALL_LOG'], 'w', encoding='utf-8'))\n"
        "print('OK: PM task submitted')\n"
        "print('task_id = pm-retry-N0-cafefeed')\n",
        encoding="utf-8",
    )
    sid = "sprint-planner-retry-dispatch"
    script = r'''
log() { :; }
emit_event() { :; }
dispatch_planner_operator_retry "$SID"
'''
    result = _source_coordinator(
        harness,
        script,
        env={"SID": sid, "CALL_LOG": str(call_log)},
    )

    assert result.returncode == 0, result.stdout + result.stderr
    args = json.loads(call_log.read_text(encoding="utf-8"))
    assert args[0] == "submit"
    assert args[args.index("--role") + 1] == "planner"
    assert args[args.index("--sprint") + 1] == sid
    objective = args[args.index("--objective") + 1]
    assert "Do not run the plan compiler" in objective
    assert "do not dispatch Builder or Evaluator" in objective
