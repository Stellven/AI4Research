from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "live-codex-e2e-isolated.sh"


def _classify(status: str) -> tuple[str, int]:
    command = r'''
source "$1"
set +e
classification="$(classify_sprint_status "$2")"
exit_code=$?
python3 - "$classification" "$exit_code" <<'PY'
import json, sys
print(json.dumps({"classification": sys.argv[1], "exit_code": int(sys.argv[2])}))
PY
'''
    completed = subprocess.run(
        ["bash", "-c", command, "terminal-status-test", str(SCRIPT), status],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)
    return payload["classification"], payload["exit_code"]


def test_live_e2e_terminal_status_classes_are_distinct():
    assert _classify("passed") == ("success", 0)
    assert _classify("needs_human_review") == ("human_review", 3)
    assert _classify("failed_launch") == ("failure", 1)
    assert _classify("active") == ("active", 4)


def test_sourcing_live_e2e_script_has_no_setup_side_effects(tmp_path):
    completed = subprocess.run(
        [
            "bash",
            "-c",
            'cd "$1"; before="$(find . -mindepth 1 -print)"; '
            'source "$2"; after="$(find . -mindepth 1 -print)"; '
            '[[ "$before" == "$after" ]]',
            "source-side-effect-test",
            str(tmp_path),
            str(SCRIPT),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_owned_process_teardown_records_term_without_unnecessary_kill():
    command = r'''
source "$1"
sleep 30 &
pid=$!
terminate_owned_pid "$pid" 10
python3 - "$pid" "$TERMINATE_TERM_PID" "$TERMINATE_KILL_PID" "$TERMINATE_SURVIVOR_PID" <<'PY'
import json, sys
print(json.dumps({"pid": sys.argv[1], "term": sys.argv[2], "kill": sys.argv[3], "survivor": sys.argv[4]}))
PY
'''
    completed = subprocess.run(
        ["bash", "-c", command, "teardown-term-test", str(SCRIPT)],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)
    assert payload == {
        "pid": payload["pid"],
        "term": payload["pid"],
        "kill": "",
        "survivor": "",
    }


def test_owned_process_teardown_escalates_and_measures_no_survivor():
    command = r'''
source "$1"
bash -c 'trap "" TERM; while :; do sleep 1; done' &
pid=$!
sleep 0.1
terminate_owned_pid "$pid" 2
python3 - "$pid" "$TERMINATE_TERM_PID" "$TERMINATE_KILL_PID" "$TERMINATE_SURVIVOR_PID" <<'PY'
import json, sys
print(json.dumps({"pid": sys.argv[1], "term": sys.argv[2], "kill": sys.argv[3], "survivor": sys.argv[4]}))
PY
'''
    completed = subprocess.run(
        ["bash", "-c", command, "teardown-kill-test", str(SCRIPT)],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)
    assert payload == {
        "pid": payload["pid"],
        "term": payload["pid"],
        "kill": payload["pid"],
        "survivor": "",
    }


def test_teardown_observations_close_parent_span_and_report_measured_targets(tmp_path):
    trace = tmp_path / "trace.jsonl"
    registry = tmp_path / "registry.json"
    registry.write_text(
        json.dumps(
            {
                "term_signalled": [111, 444],
                "kill_signalled": [222, 555],
                "survivors": [333, 666],
            }
        ),
        encoding="utf-8",
    )
    command = r'''
source "$1"
export SOLAR_DEVELOPER_OBSERVABILITY=1
export SOLAR_OBSERVABILITY_TRACE="$2"
export UAT_RUN_ID="teardown-observation-test"
observe_uat_teardown_started "$3"
observe_uat_teardown_completed "$3" 111 222 333 "$4" $'session-a\nsession-a' session-b SIGTERM
'''
    completed = subprocess.run(
        [
            "bash",
            "-c",
            command,
            "teardown-observation-test",
            str(SCRIPT),
            str(trace),
            str(ROOT / "harness" / "lib"),
            str(registry),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    rows = [json.loads(line) for line in trace.read_text(encoding="utf-8").splitlines()]
    assert [row["event"] for row in rows] == [
        "uat.teardown.started",
        "uat.teardown.term_sent",
        "uat.teardown.kill_sent",
        "uat.teardown.tmux_sessions_terminated",
        "uat.teardown.completed",
    ]
    started, term, kill, _tmux, completed_row = rows
    assert started["operation_id"] == completed_row["operation_id"]
    assert started["span_id"] == completed_row["span_id"]
    assert started["parent_span_id"] is None
    assert completed_row["parent_span_id"] is None
    assert completed_row["terminal"] is True
    assert term["parent_span_id"] == started["span_id"]
    assert kill["parent_span_id"] == started["span_id"]
    assert term["data"]["target_pids"] == [111, 444]
    assert kill["data"]["target_pids"] == [222, 555]
    assert completed_row["data"]["survivor_pids"] == [333, 666]
    span_ids = {row["span_id"] for row in rows if row.get("span_id")}
    parent_ids = {
        row["parent_span_id"] for row in rows if row.get("parent_span_id")
    }
    assert parent_ids <= span_ids


def test_poller_stops_immediately_and_records_human_review_terminal(tmp_path):
    harness = tmp_path / "harness"
    evidence = tmp_path / "evidence"
    (harness / "sprints").mkdir(parents=True)
    evidence.mkdir()
    sid = "sprint-human-review"
    (harness / "sprints" / f"{sid}.status.json").write_text(
        json.dumps({"sprint_id": sid, "status": "needs_human_review"}),
        encoding="utf-8",
    )
    command = r'''
source "$1"
iso_harness="$2"
evidence_dir="$3"
timeout_seconds=30
poll_seconds=5
capture_http_snapshot() { :; }
set +e
poll_until_terminal "$4" "http://unused.invalid"
exit $?
'''
    completed = subprocess.run(
        [
            "bash",
            "-c",
            command,
            "terminal-poller-test",
            str(SCRIPT),
            str(harness),
            str(evidence),
            sid,
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 3, completed.stderr
    marker = json.loads(
        (evidence / "TERMINAL_PRODUCT_STATE.json").read_text(encoding="utf-8")
    )
    assert marker == {
        "sprint_id": sid,
        "status": "needs_human_review",
        "classification": "human_review",
        "exit_code": 3,
        "poll_index": 1,
        "observed_at": marker["observed_at"],
    }
    assert not (evidence / "TIMEOUT_NOT_PRODUCT_PROOF.json").exists()
