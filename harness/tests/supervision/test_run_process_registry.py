"""Lane 0.5 — run process registry (R7, design §1.9, AC-R7.4 deterministic tier).

P1.5 deterministic tests: no real processes are spawned or killed here — process
liveness and signalling go through the module's injectable seams
(``_pid_exists`` / ``_read_cmdline`` / ``_send_signal`` / ``_sleep``). The
real-daemon teardown proof (including watchdog-respawn suppression) lives in
``test_run_teardown_real_processes.py`` at the opt-in P1.6 tier.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import run_process_registry as rpr


RID = "sprint-20260706-lane05"


@pytest.fixture()
def harness_dir(tmp_path, monkeypatch):
    hd = tmp_path / "harness"
    hd.mkdir()
    monkeypatch.setenv("HARNESS_DIR", str(hd))
    return hd


def _records(hd: Path, rid: str = RID) -> list[dict]:
    return rpr.read_records(rid, harness_dir=hd)


# --- register / read ---------------------------------------------------------


def test_register_and_read_roundtrip(harness_dir):
    rec1 = rpr.register(RID, "coordinator", 4242, harness_dir=harness_dir)
    rec2 = rpr.register(RID, "watchdog", 4243, meta={"src": "test"}, harness_dir=harness_dir)
    assert rec1["event"] == "register" and rec1["pid"] == 4242
    assert rec2["role"] == "watchdog" and rec2["meta"] == {"src": "test"}

    records = _records(harness_dir)
    assert [r["pid"] for r in records if r["event"] == "register"] == [4242, 4243]
    # one registry file per run, run-scoped
    assert rpr.registry_path(RID, harness_dir=harness_dir).exists()


def test_register_rejects_traversal_run_id(harness_dir):
    with pytest.raises(ValueError):
        rpr.register("../evil", "coordinator", 4242, harness_dir=harness_dir)
    with pytest.raises(ValueError):
        rpr.register("a/b", "coordinator", 4242, harness_dir=harness_dir)


def test_register_rejects_bad_pid(harness_dir):
    for pid in (0, -1, 1):
        with pytest.raises(ValueError):
            rpr.register(RID, "driver", pid, harness_dir=harness_dir)


def test_process_group_registration_rejects_the_callers_own_group(harness_dir):
    with pytest.raises(ValueError, match="dedicated session/group leader|own process group"):
        rpr.register(
            RID,
            "driver",
            os.getpid(),
            harness_dir=harness_dir,
            signal_scope="process_group",
        )


def test_register_refused_after_terminal(harness_dir):
    rpr.register(RID, "coordinator", 4242, harness_dir=harness_dir)
    rpr.mark_terminal(RID, reason="done", harness_dir=harness_dir)
    with pytest.raises(rpr.TerminalRunError):
        rpr.register(RID, "driver", 4300, harness_dir=harness_dir)


# --- terminal marker ---------------------------------------------------------


def test_mark_terminal_idempotent_and_shell_checkable(harness_dir):
    assert not rpr.is_terminal(RID, harness_dir=harness_dir)
    rpr.mark_terminal(RID, reason="wrapper_exit", harness_dir=harness_dir)
    rpr.mark_terminal(RID, reason="second_call", harness_dir=harness_dir)
    assert rpr.is_terminal(RID, harness_dir=harness_dir)
    # the marker is a plain file so bash call sites can gate respawn with [[ -f ... ]]
    marker = rpr.terminal_marker_path(RID, harness_dir=harness_dir)
    assert marker.is_file()
    terminals = [r for r in _records(harness_dir) if r["event"] == "terminal"]
    assert terminals and terminals[0]["reason"] == "wrapper_exit"


# --- crash survival ----------------------------------------------------------


def test_registry_survives_crash_torn_last_line(harness_dir):
    rpr.register(RID, "coordinator", 4242, harness_dir=harness_dir)
    rpr.register(RID, "driver", 4243, harness_dir=harness_dir)
    path = rpr.registry_path(RID, harness_dir=harness_dir)
    # simulate a crash mid-append: torn, non-JSON trailing line
    with open(path, "a", encoding="utf-8") as f:
        f.write('{"event": "register", "run_id": "' + RID)

    records = _records(harness_dir)
    assert [r["pid"] for r in records if r["event"] == "register"] == [4242, 4243]
    # registry still writable and teardown still runs after the torn write
    rpr.mark_terminal(RID, harness_dir=harness_dir)
    assert rpr.is_terminal(RID, harness_dir=harness_dir)


# --- teardown (simulated processes) ------------------------------------------


class FakeProcs:
    """Simulated process table keyed by pid.

    behavior: 'dies_on_term' | 'dies_on_kill' | 'immortal'
    """

    def __init__(self, behaviors: dict[int, str]):
        self.behaviors = dict(behaviors)
        self.alive = set(behaviors)
        self.signals: list[tuple[int, int]] = []
        self.terminal_at_first_signal: bool | None = None
        self._is_terminal = lambda: False

    def pid_exists(self, pid: int) -> bool:
        return pid in self.alive

    def send_signal(self, pid: int, sig: int) -> None:
        if self.terminal_at_first_signal is None:
            self.terminal_at_first_signal = self._is_terminal()
        self.signals.append((pid, sig))
        if pid not in self.alive:
            raise ProcessLookupError(pid)
        behavior = self.behaviors[pid]
        import signal as _signal

        if sig == _signal.SIGTERM and behavior == "dies_on_term":
            self.alive.discard(pid)
        elif sig == _signal.SIGKILL and behavior in {"dies_on_term", "dies_on_kill"}:
            self.alive.discard(pid)


@pytest.fixture()
def fake_procs(monkeypatch, harness_dir):
    def _install(behaviors: dict[int, str]) -> FakeProcs:
        procs = FakeProcs(behaviors)
        procs._is_terminal = lambda: rpr.is_terminal(RID, harness_dir=harness_dir)
        monkeypatch.setattr(rpr, "_pid_exists", procs.pid_exists)
        monkeypatch.setattr(rpr, "_send_signal", procs.send_signal)
        monkeypatch.setattr(rpr, "_read_cmdline", lambda pid: "")
        monkeypatch.setattr(rpr, "_sleep", lambda s: None)
        return procs

    return _install


def test_teardown_kills_watchdog_first_and_marks_terminal_before_signalling(
    harness_dir, fake_procs
):
    rpr.register(RID, "status-server", 5001, harness_dir=harness_dir)
    rpr.register(RID, "coordinator", 5002, harness_dir=harness_dir)
    rpr.register(RID, "watchdog", 5003, harness_dir=harness_dir)
    procs = fake_procs({5001: "dies_on_term", 5002: "dies_on_term", 5003: "dies_on_term"})

    result = rpr.teardown(RID, harness_dir=harness_dir)

    assert result["ok"] is True
    assert not procs.alive
    # terminal marker must exist before the first signal (respawn window closed)
    assert procs.terminal_at_first_signal is True
    # watchdog killed first, coordinator second
    signalled_order = [pid for pid, _sig in procs.signals]
    assert signalled_order.index(5003) < signalled_order.index(5002) < signalled_order.index(5001)
    events = [r for r in _records(harness_dir) if r["event"] == "teardown"]
    assert events and events[-1]["ok"] is True


def test_teardown_escalates_to_sigkill_and_reports_survivors(harness_dir, fake_procs):
    import signal

    rpr.register(RID, "watchdog", 6001, harness_dir=harness_dir)
    rpr.register(RID, "driver", 6002, harness_dir=harness_dir)
    rpr.register(RID, "driver", 6003, harness_dir=harness_dir)
    procs = fake_procs({6001: "dies_on_term", 6002: "dies_on_kill", 6003: "immortal"})

    result = rpr.teardown(RID, grace_s=0.2, kill_grace_s=0.1, harness_dir=harness_dir)

    assert 6002 in result["sigkilled"]
    assert result["survivors"] == [6003]
    assert result["ok"] is False
    assert (6002, signal.SIGKILL) in procs.signals


def test_teardown_idempotent(harness_dir, fake_procs):
    rpr.register(RID, "coordinator", 7001, harness_dir=harness_dir)
    procs = fake_procs({7001: "dies_on_term"})

    first = rpr.teardown(RID, harness_dir=harness_dir)
    signals_after_first = list(procs.signals)
    second = rpr.teardown(RID, harness_dir=harness_dir)

    assert first["ok"] is True and second["ok"] is True
    # second teardown finds nothing alive and sends no further signals
    assert procs.signals == signals_after_first
    events = [r for r in _records(harness_dir) if r["event"] == "teardown"]
    assert len(events) == 2


def test_teardown_skips_reused_pid(harness_dir, monkeypatch, fake_procs):
    rpr.register(RID, "driver", 8001, harness_dir=harness_dir)
    # rewrite the record's identity so the current "process" no longer matches
    procs = fake_procs({8001: "dies_on_term"})
    monkeypatch.setattr(rpr, "_read_cmdline", lambda pid: "some-other-binary --flag")
    path = rpr.registry_path(RID, harness_dir=harness_dir)
    records = [json.loads(line) for line in path.read_text().splitlines()]
    records[0]["cmdline"] = "original-daemon --run"
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n")

    result = rpr.teardown(RID, harness_dir=harness_dir)

    assert procs.signals == []  # never signalled: identity mismatch means pid reuse
    assert any(s.get("pid") == 8001 and s.get("why") == "pid_reused" for s in result["skipped"])


def test_teardown_never_signals_self(harness_dir, fake_procs):
    me = os.getpid()
    rpr.register(RID, "driver", me, harness_dir=harness_dir)
    procs = fake_procs({me: "immortal"})

    result = rpr.teardown(RID, harness_dir=harness_dir)

    assert procs.signals == []
    assert any(s.get("pid") == me and s.get("why") == "self" for s in result["skipped"])


def test_live_entries_reflect_process_table(harness_dir, fake_procs):
    rpr.register(RID, "coordinator", 9001, harness_dir=harness_dir)
    rpr.register(RID, "driver", 9002, harness_dir=harness_dir)
    fake_procs({9001: "immortal"})  # 9002 not in the table -> already exited

    live = rpr.live_entries(RID, harness_dir=harness_dir)
    assert [e["pid"] for e in live] == [9001]


# --- CLI plumbing (no processes killed: dead pid + marker round-trip) ---------


def test_cli_register_terminal_roundtrip(harness_dir, tmp_path):
    import subprocess
    import sys

    module = Path(rpr.__file__).resolve()
    env = dict(os.environ)
    env["HARNESS_DIR"] = str(harness_dir)

    def cli(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(module), *args],
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )

    # spawn-and-reap a trivial process so the pid is real but already dead
    reaped = subprocess.Popen(["true"])
    reaped.wait(timeout=10)
    dead_pid = str(reaped.pid)

    assert cli("register", "--run-id", RID, "--role", "driver", "--pid", dead_pid).returncode == 0
    assert cli("is-terminal", "--run-id", RID).returncode == 1
    assert cli("mark-terminal", "--run-id", RID, "--reason", "cli-test").returncode == 0
    assert cli("is-terminal", "--run-id", RID).returncode == 0
    # register after terminal is refused with a distinct exit code
    refused = cli("register", "--run-id", RID, "--role", "driver", "--pid", dead_pid)
    assert refused.returncode == 3
    status = cli("status", "--run-id", RID)
    assert status.returncode == 0
    payload = json.loads(status.stdout)
    assert payload["terminal"] is True
