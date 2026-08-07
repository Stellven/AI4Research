"""Lane 0.5 — P1.6 non-hermetic teardown proof (AC-R7.4).

Opt-in: set ``SOLAR_P16_REAL_PROCESS=1`` to run. Spawns REAL local dummy
processes (plain ``sleep`` daemons plus a respawning fake watchdog written in
bash) — no tmux, no models, no network — and proves:

  * teardown kills every registered run-scoped process, watchdog-first;
  * the run-terminal marker suppresses watchdog respawn attempts (the fake
    watchdog respawns its child in a loop until the registry refuses/marks
    terminal, generalizing F-043);
  * teardown is idempotent against a real process table.

Every ladder rung's cleanup gate reuses this proof (runtime-validation-ladder
P2+ cleanup gates call ``run_process_registry teardown`` / ``status``).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

import run_process_registry as rpr


pytestmark = pytest.mark.skipif(
    os.environ.get("SOLAR_P16_REAL_PROCESS", "").strip() != "1",
    reason="P1.6 real-process tier is opt-in: set SOLAR_P16_REAL_PROCESS=1",
)

RID = "sprint-20260706-p16"


@pytest.fixture()
def harness_dir(tmp_path, monkeypatch):
    hd = tmp_path / "harness"
    hd.mkdir()
    monkeypatch.setenv("HARNESS_DIR", str(hd))
    return hd


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _spawn_sleeper() -> subprocess.Popen:
    return subprocess.Popen(
        ["sleep", "300"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )


def _spawn_fake_watchdog(tmp_path: Path, harness_dir: Path) -> subprocess.Popen:
    """A respawning supervisor: keeps a sleep child registered, restarting it
    whenever it dies — until the run is marked terminal (marker file or a
    refused register), at which point it exits. This is the watchdog-respawn
    behavior AC-R7.4 requires teardown to defeat."""
    module = Path(rpr.__file__).resolve()
    script = tmp_path / "fake-watchdog.sh"
    script.write_text(
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            set -u
            RID="{RID}"
            REG="{module}"
            export HARNESS_DIR="{harness_dir}"
            while true; do
              if "{sys.executable}" "$REG" is-terminal --run-id "$RID" >/dev/null 2>&1; then
                exit 0
              fi
              sleep 300 &
              child=$!
              if ! "{sys.executable}" "$REG" register --run-id "$RID" --role driver --pid "$child" >/dev/null 2>&1; then
                kill "$child" 2>/dev/null
                exit 0
              fi
              wait "$child" 2>/dev/null
              sleep 0.1
            done
            """
        )
    )
    script.chmod(0o755)
    bash = shutil.which("bash") or "/bin/bash"
    return subprocess.Popen(
        [bash, str(script)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )


def test_real_teardown_kills_all_and_suppresses_respawn(tmp_path, harness_dir):
    coordinator = _spawn_sleeper()
    status_server = _spawn_sleeper()
    rpr.register(RID, "coordinator", coordinator.pid, harness_dir=harness_dir)
    rpr.register(RID, "status-server", status_server.pid, harness_dir=harness_dir)

    watchdog = _spawn_fake_watchdog(tmp_path, harness_dir)
    rpr.register(RID, "watchdog", watchdog.pid, harness_dir=harness_dir)

    # let the fake watchdog spawn + register its first child
    deadline = time.time() + 10
    while time.time() < deadline:
        drivers = [
            r
            for r in rpr.read_records(RID, harness_dir=harness_dir)
            if r["event"] == "register" and r["role"] == "driver"
        ]
        if drivers:
            break
        time.sleep(0.1)
    assert drivers, "fake watchdog never registered its child"

    result = rpr.teardown(RID, grace_s=5.0, kill_grace_s=2.0, harness_dir=harness_dir)

    assert result["ok"] is True, f"teardown left survivors: {result}"
    assert rpr.is_terminal(RID, harness_dir=harness_dir)

    # reap our direct children (killed by teardown, zombies until reaped)
    for proc in (coordinator, status_server, watchdog):
        proc.wait(timeout=10)

    # zero surviving run-scoped processes (AC-R7.4)
    registered = [
        r for r in rpr.read_records(RID, harness_dir=harness_dir) if r["event"] == "register"
    ]
    record_count = len(registered)
    for rec in registered:
        assert not _alive(rec["pid"]), f"pid {rec['pid']} ({rec['role']}) survived teardown"

    # respawn suppression: no new registrations appear after teardown
    time.sleep(1.0)
    registered_after = [
        r for r in rpr.read_records(RID, harness_dir=harness_dir) if r["event"] == "register"
    ]
    assert len(registered_after) == record_count, "watchdog respawned past the terminal marker"
    assert rpr.live_entries(RID, harness_dir=harness_dir) == []


def test_real_teardown_idempotent(harness_dir):
    sleeper = _spawn_sleeper()
    rpr.register(RID, "coordinator", sleeper.pid, harness_dir=harness_dir)

    first = rpr.teardown(RID, harness_dir=harness_dir)
    assert first["ok"] is True
    sleeper.wait(timeout=10)

    second = rpr.teardown(RID, harness_dir=harness_dir)
    assert second["ok"] is True
    assert second["killed"] == [] and second["sigkilled"] == []

    events = [r for r in rpr.read_records(RID, harness_dir=harness_dir) if r["event"] == "teardown"]
    assert len(events) == 2


def test_real_registry_status_reports_live_then_dead(harness_dir):
    sleeper = _spawn_sleeper()
    rpr.register(RID, "driver", sleeper.pid, harness_dir=harness_dir)
    assert [e["pid"] for e in rpr.live_entries(RID, harness_dir=harness_dir)] == [sleeper.pid]

    result = rpr.teardown(RID, harness_dir=harness_dir)
    assert result["ok"] is True
    sleeper.wait(timeout=10)
    assert rpr.live_entries(RID, harness_dir=harness_dir) == []

    payload = json.loads(
        subprocess.run(
            [sys.executable, str(Path(rpr.__file__).resolve()), "status", "--run-id", RID],
            capture_output=True,
            text=True,
            env={**os.environ, "HARNESS_DIR": str(harness_dir)},
            timeout=30,
        ).stdout
    )
    assert payload["terminal"] is True
    assert payload["live"] == []
