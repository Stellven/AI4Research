"""Isolated end-to-end tests for the Solar Experience Memory layer.

Every scenario exercises the real modules, SQLite database, and filesystem in a
fresh subprocess rooted under ``tmp_path``.  Test collection must never import
from or write to the user's installed ``~/.solar/harness`` runtime.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


HARNESS_DIR = (Path(__file__).resolve().parents[3] / 'harness')
LIB_DIR = HARNESS_DIR / "lib"


def _run_isolated(
    runtime_root: Path,
    script: str,
    *,
    extra_env: dict[str, str] | None = None,
) -> dict:
    runtime_root.mkdir(parents=True, exist_ok=True)
    isolated_home = runtime_root.parent / "home"
    isolated_home.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.update(
        {
            "HOME": str(isolated_home),
            "HARNESS_DIR": str(runtime_root),
            "SOLAR_HARNESS_DIR": str(runtime_root),
            "PYTHONPATH": str(LIB_DIR),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    if extra_env:
        env.update(extra_env)

    proc = subprocess.run(
        [sys.executable, "-c", script],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    assert lines, "isolated Experience Memory scenario produced no output"
    return json.loads(lines[-1])


def test_terminal_phase_wake_abort(tmp_path):
    runtime_root = tmp_path / "runtime"
    sprints_dir = runtime_root / "sprints"
    sprints_dir.mkdir(parents=True)
    sid = "sprint-synthetic-e2e-test-001"
    (sprints_dir / f"{sid}.status.json").write_text(
        json.dumps(
            {
                "sid": sid,
                "status": "passed",
                "phase": "finalized",
                "round": 1,
                "updated_at": "2026-05-10T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )

    result = _run_isolated(
        runtime_root,
        f"""
import json
from coordinator_hooks import pre_dispatch
decision = pre_dispatch({sid!r}, "test_dispatch")
print(json.dumps(decision.to_dict()))
""",
    )

    assert result["action"] == "abort"
    assert result["pattern"] == "terminal_phase_wake"
    assert result["confidence"] > 0.5
    assert (runtime_root / "experience" / "decisions.jsonl").is_file()


def test_experience_hook_disabled(tmp_path):
    result = _run_isolated(
        tmp_path / "runtime",
        """
import json
from coordinator_hooks import pre_dispatch
print(json.dumps(pre_dispatch("any-sprint", "test").to_dict()))
""",
        extra_env={"EXPERIENCE_HOOK": "0"},
    )

    assert result["action"] == "allow"
    assert result["reason"] == "hook_disabled"


def test_decisions_audit_written(tmp_path):
    runtime_root = tmp_path / "runtime"
    result = _run_isolated(
        runtime_root,
        """
import json
from coordinator_hooks import pre_dispatch
decision = pre_dispatch("sprint-synthetic-audit-test", "test_audit")
print(json.dumps(decision.to_dict()))
""",
    )

    decisions_path = runtime_root / "experience" / "decisions.jsonl"
    entries = [
        json.loads(line)
        for line in decisions_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert result["action"] == "allow"
    assert entries[-1]["sid"] == "sprint-synthetic-audit-test"
    assert entries[-1]["action_requested"] == "test_audit"


def test_stats_reflects_real_persisted_entry(tmp_path):
    result = _run_isolated(
        tmp_path / "runtime",
        """
import json
from experience.compressor import compress_trajectories
from experience.query import get_stats
trajectory = {
    "schema_version": "1.0.0",
    "sid": "sprint-synthetic-success",
    "status": "passed",
    "phase": "finalized",
    "trigger_sig": "synthetic-trigger",
    "state_sig": "synthetic-state",
    "tags": ["test:isolated"],
    "events_summary": {
        "total_events": 1,
        "c_u_events": 0,
        "dispatch_events": 0,
        "eval_rounds": 1,
        "duration_minutes": 1.0,
    },
    "anti_patterns": [],
    "outcome": "success",
    "repair_actions": [],
    "extracted_at": "2026-05-10T00:00:00Z",
}
entries = compress_trajectories([trajectory])
print(json.dumps({"entries": entries, "stats": get_stats()}))
""",
    )

    assert result["entries"][0]["pattern_class"] == "success_workflow"
    assert result["stats"]["total_entries"] == 1
    assert result["stats"]["by_pattern"] == {"success_workflow": 1}


def test_query_for_sprint_returns_memories_contract(tmp_path):
    runtime_root = tmp_path / "runtime"
    sprints_dir = runtime_root / "sprints"
    sprints_dir.mkdir(parents=True)
    sid = "sprint-synthetic-query"
    (sprints_dir / f"{sid}.status.json").write_text(
        json.dumps({"sid": sid, "status": "active", "phase": "building", "round": 1}),
        encoding="utf-8",
    )

    result = _run_isolated(
        runtime_root,
        f"""
import json
from experience.query import query_for_sprint
print(json.dumps(query_for_sprint({sid!r}, limit=5, include_mia=False)))
""",
    )

    assert result["ok"] is True
    assert result["sid"] == sid
    assert isinstance(result["memories"], list)


def test_extract_sprint_is_repeatable_for_synthetic_terminal_sprint(tmp_path):
    runtime_root = tmp_path / "runtime"
    sprints_dir = runtime_root / "sprints"
    sprints_dir.mkdir(parents=True)
    sid = "sprint-synthetic-extract"
    (sprints_dir / f"{sid}.status.json").write_text(
        json.dumps(
            {
                "sid": sid,
                "status": "passed",
                "phase": "finalized",
                "round": 1,
                "updated_at": "2026-05-10T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )

    result = _run_isolated(
        runtime_root,
        f"""
import json
from experience.extractor import extract_sprint
first = extract_sprint({sid!r})
second = extract_sprint({sid!r})
print(json.dumps({{"first": first, "second": second}}))
""",
    )

    assert result["first"]["sid"] == sid
    assert result["second"]["sid"] == sid
    assert result["first"]["trigger_sig"] == result["second"]["trigger_sig"]
    assert (runtime_root / "experience" / "trajectory" / f"{sid}.json").is_file()


def test_schema_validation_rejects_bad_entry(tmp_path):
    result = _run_isolated(
        tmp_path / "runtime",
        """
import json
from experience.schema import validate_entry
try:
    validate_entry({
        "schema_version": "1.0.0",
        "entry_id": "test",
        "trigger_sig": "abc",
        "pattern_class": "not_a_valid_pattern",
        "outcome": "failure",
        "created_at": "2026-01-01T00:00:00Z",
    })
except ValueError as exc:
    print(json.dumps({"rejected": True, "error": str(exc)}))
else:
    print(json.dumps({"rejected": False}))
""",
    )

    assert result["rejected"] is True
    assert "invalid pattern_class" in result["error"]
