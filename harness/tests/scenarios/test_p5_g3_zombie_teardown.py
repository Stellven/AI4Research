"""G3 zombie-factory fix: watchdogs die with their run; teardown always marks.

Investigation of G3 runs 2/3 (RUN_SETUP_FAILED at the status-server seam)
found 18 coordinator/coordinator-watchdog daemons from COMPLETED e2e
sandboxes (July 7-9) still alive — some for 30+ hours — periodically
rebuilding tmux sessions and re-running harness startup, whose pre-scoping
status-server code swept and killed every live run's server. Two gaps made
the factory:

1. The F-043 terminal marker only suppressed COORDINATOR respawn; the
   watchdog daemon itself looped forever and kept rebuilding sessions.
2. kill_harness only ran the registry teardown (which writes the marker and
   reaps daemons) INSIDE the tmux-session-exists branch — e2e cleanups kill
   sessions directly, so completed sandboxes never got a marker and their
   watchdogs ran fail-open forever.

These tests run the REAL scripts with HARNESS_DIR pointed at a tmp harness.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

_HARNESS = Path(__file__).resolve().parents[2]


def _tmp_harness(tmp_path: Path) -> Path:
    harness = tmp_path / "harness"
    (harness / "run" / "process-registry").mkdir(parents=True)
    (harness / "lib").mkdir(parents=True)
    (harness / "sprints").mkdir(parents=True)
    for helper in ("run-state.sh", "harness-config.sh", "portable.sh"):
        src = _HARNESS / "lib" / helper
        if src.exists():
            (harness / "lib" / helper).write_bytes(src.read_bytes())
    reg = _HARNESS / "lib" / "run_process_registry.py"
    (harness / "lib" / "run_process_registry.py").write_bytes(reg.read_bytes())
    return harness


def _env(harness: Path) -> dict:
    env = dict(os.environ)
    env["HARNESS_DIR"] = str(harness)
    return env


def test_watchdog_daemon_exits_when_run_is_terminal(tmp_path):
    """A terminal marker means the run is over: the watchdog itself must
    exit, not merely suppress coordinator respawn."""
    harness = _tmp_harness(tmp_path)
    (harness / "run" / "process-registry" / "harness.terminal").write_text(
        "terminal\n", encoding="utf-8"
    )

    proc = subprocess.Popen(
        ["bash", str(_HARNESS / "coordinator-watchdog.sh"), "run-daemon"],
        env=_env(harness),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=10)
        pytest.fail("watchdog run-daemon kept looping despite the terminal marker")
    assert proc.returncode == 0


def test_kill_writes_terminal_marker_even_without_tmux_session(tmp_path):
    """Tearing down an already-sessionless harness must still mark the run
    terminal — otherwise a watchdog that outlived the session runs forever."""
    harness = _tmp_harness(tmp_path)

    result = subprocess.run(
        ["bash", str(_HARNESS / "solar-harness.sh"), "kill"],
        env=_env(harness),
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, result.stderr
    marker = harness / "run" / "process-registry" / "harness.terminal"
    assert marker.exists(), (
        f"kill did not write the run-terminal marker: {result.stdout} {result.stderr}"
    )


def test_clear_terminal_reopens_the_run(tmp_path):
    """Review-prep finding (G3 fix-round amplification): kill now ALWAYS
    writes the terminal marker, register() refuses terminal-marked runs
    (silently — start uses `|| true`), and the watchdog exits on the marker.
    Without a clear at start, one kill+start cycle leaves the harness
    unsupervised with unregistered daemons. The registry needs a
    clear-terminal verb and start must invoke it."""
    harness = _tmp_harness(tmp_path)
    reg = harness / "lib" / "run_process_registry.py"
    env = _env(harness)

    subprocess.run(
        [sys.executable, str(reg), "mark-terminal", "--run-id", "harness"],
        env=env, check=True, capture_output=True, timeout=60,
    )
    marker = harness / "run" / "process-registry" / "harness.terminal"
    assert marker.exists()

    result = subprocess.run(
        [sys.executable, str(reg), "clear-terminal", "--run-id", "harness"],
        env=env, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert not marker.exists(), "clear-terminal did not remove the marker"

    register = subprocess.run(
        [sys.executable, str(reg), "register", "--run-id", "harness",
         "--role", "coordinator", "--pid", str(os.getpid())],
        env=env, capture_output=True, text=True, timeout=60,
    )
    assert register.returncode == 0, (
        f"register still refused after clear-terminal: {register.stderr}"
    )


def test_start_paths_clear_stale_terminal_marker():
    """Both daemon-spawning start paths must clear a stale marker before
    spawning: solar-harness.sh start_coordinator_sync and
    coordinator-watchdog.sh start."""
    sh = (_HARNESS / "solar-harness.sh").read_text(encoding="utf-8")
    start = sh.index("start_coordinator_sync()")
    spawn = sh.index("coordinator.sh", start)
    assert "clear-terminal" in sh[start:spawn], (
        "start_coordinator_sync does not clear a stale terminal marker"
    )

    wd = (_HARNESS / "coordinator-watchdog.sh").read_text(encoding="utf-8")
    case_start = wd.index("  start)")
    daemon_spawn = wd.index("run-daemon", case_start)
    assert "clear-terminal" in wd[case_start:daemon_spawn], (
        "watchdog start does not clear a stale terminal marker"
    )


def test_kill_reaps_registered_daemon_even_without_tmux_session(tmp_path):
    """The registry teardown (reap registered daemons watchdog-first) must
    run on every kill, not only when the tmux session still exists."""
    harness = _tmp_harness(tmp_path)
    daemon = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(300)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        subprocess.run(
            [
                sys.executable, str(harness / "lib" / "run_process_registry.py"),
                "register", "--run-id", "harness", "--role", "watchdog",
                "--pid", str(daemon.pid),
            ],
            env=_env(harness),
            check=True,
            capture_output=True,
            timeout=60,
        )

        result = subprocess.run(
            ["bash", str(_HARNESS / "solar-harness.sh"), "kill"],
            env=_env(harness),
            capture_output=True,
            text=True,
            timeout=120,
        )

        assert result.returncode == 0, result.stderr
        deadline = time.time() + 10
        while time.time() < deadline and daemon.poll() is None:
            time.sleep(0.2)
        assert daemon.poll() is not None, "registered daemon survived kill"
    finally:
        if daemon.poll() is None:
            daemon.kill()
            daemon.wait(timeout=10)
