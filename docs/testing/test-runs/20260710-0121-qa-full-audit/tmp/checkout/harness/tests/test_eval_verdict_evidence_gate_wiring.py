from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
HARNESS_SOURCE = REPO_ROOT / "harness"


def _install_harness(tmp_path: Path) -> tuple[Path, Path]:
    home = tmp_path / "home"
    harness_dir = home / ".solar" / "harness"
    shutil.copytree(
        HARNESS_SOURCE,
        harness_dir,
        symlinks=True,
        ignore=shutil.ignore_patterns(
            ".DS_Store",
            "*.log",
            "*.pid",
            "*.port",
            "*.tmp",
            "*~",
            "cache",
            "logs",
            "run",
            "state",
            "venvs",
            "vendor",
            "quarantine",
        ),
    )
    (harness_dir / "sprints").mkdir(parents=True, exist_ok=True)
    return home, harness_dir


def _write_reviewing_sprint(harness_dir: Path, sid: str) -> Path:
    status_path = harness_dir / "sprints" / f"{sid}.status.json"
    status_path.write_text(
        json.dumps(
            {
                "id": sid,
                "status": "reviewing",
                "round": 2,
                "history": [
                    {"event": "implementation_completed", "by": "builder", "round": 2},
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return status_path


def test_gate_status_transition_imports_and_allows_reviewing_to_passed(
    tmp_path: Path,
    monkeypatch,
) -> None:
    home, harness_dir = _install_harness(tmp_path)
    sid = "sprint-eval-gate-import"
    _write_reviewing_sprint(harness_dir, sid)

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("HARNESS_DIR", str(harness_dir))
    monkeypatch.syspath_prepend(str(harness_dir / "lib"))

    from coordinator_hooks import gate_status_transition

    decision = gate_status_transition(sid, "reviewing", "passed")

    assert decision.action == "allow"
    assert decision.reason == "status_transition_allowed"


def test_eval_verdict_pass_runs_end_to_end_and_transitions_status(
    tmp_path: Path,
) -> None:
    home, harness_dir = _install_harness(tmp_path)
    sid = "sprint-eval-pass-e2e"
    status_path = _write_reviewing_sprint(harness_dir, sid)

    env = os.environ.copy()
    env.update(
        {
            "HOME": str(home),
            "HARNESS_DIR": str(harness_dir),
            "SPRINTS_DIR": str(harness_dir / "sprints"),
            "PYTHONPATH": str(harness_dir / "lib"),
        }
    )

    proc = subprocess.run(
        ["bash", str(harness_dir / "solar-harness.sh"), "eval-verdict", sid, "pass", "all good"],
        cwd=str(tmp_path),
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=20,
    )

    assert proc.returncode == 0, f"stdout={proc.stdout}\nstderr={proc.stderr}"

    status = json.loads(status_path.read_text(encoding="utf-8"))
    assert status["status"] == "passed"
    assert status["phase"] == "eval_passed"
    assert status["handoff_to"] == ""
    assert status["target_role"] == ""
    assert status["history"][-1]["event"] == "eval_completed"
    assert status["history"][-1]["verdict"] == "PASS"
    assert status["history"][-1]["reason"] == "all good"

    events_path = harness_dir / "sessions" / sid / "events.jsonl"
    assert events_path.exists()
    events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()]
    transitions = [event for event in events if event["type"] == "state_transition"]
    assert transitions[-1]["payload"]["from"] == "reviewing"
    assert transitions[-1]["payload"]["to"] == "passed"
