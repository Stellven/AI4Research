"""G4-lite teardown-ownership fix — operator worker processes are registered.

Evidence: G4-lite run 2 (p5-g4-lite-live-rung-20260710T133158Z) — the repair
builder's worker process (PID 572280) survived `solar-harness kill` and kept
writing after the sprint's truthful terminal (the post-fixture drift). Run 3
confirmed the class from the other side (a process the registry never knew
about outliving teardown). Mechanism: operatord spawns each task worker with
start_new_session=True (its own session — deliberate, so the worker survives
an operatord restart mid-task) but never REGISTERS it, and the registry
teardown (`run_process_registry.teardown --run-id harness`) only reaps
registered pids.

Fix under test: operatord registers every spawned worker in the harness run
registry (role "operator-task", process-birth identity for exec-safe kills,
task metadata) so the ONE existing teardown owns it. Registration is
best-effort: a terminal run refuses registration by design (the
respawn-past-teardown guard) and any registry failure must never break task
execution. State corruption from stragglers is already fenced (546e134a);
this closes the process-hygiene half.
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

_HARNESS = Path(__file__).resolve().parents[2]
_LIB = _HARNESS / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

import run_process_registry as rpr  # noqa: E402


def _load_operatord(harness_dir: Path):
    spec = importlib.util.spec_from_file_location(
        "g4lite_teardown_operatord", _HARNESS / "tools" / "operatord.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    old = os.environ.get("HARNESS_DIR")
    os.environ["HARNESS_DIR"] = str(harness_dir)
    try:
        spec.loader.exec_module(mod)
    finally:
        if old is None:
            os.environ.pop("HARNESS_DIR", None)
        else:
            os.environ["HARNESS_DIR"] = old
    mod.HARNESS_DIR = harness_dir
    return mod


def _load_codex_operator(harness_dir: Path):
    spec = importlib.util.spec_from_file_location(
        "g4lite_teardown_codex_operator", _HARNESS / "tools" / "codex_operator.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    old = os.environ.get("HARNESS_DIR")
    os.environ["HARNESS_DIR"] = str(harness_dir)
    try:
        spec.loader.exec_module(mod)
    finally:
        if old is None:
            os.environ.pop("HARNESS_DIR", None)
        else:
            os.environ["HARNESS_DIR"] = old
    return mod


ENVELOPE = {
    "task_id": "pm-sprint-g4td-N1-abc123",
    "sprint_id": "sprint-g4td",
    "node_id": "N1",
    "operator_id": "test-command-builder",
    "task_type": "graph_node",
    "objective": "teardown ownership fixture",
}


def _registry_entries(harness_dir: Path) -> list[dict]:
    path = harness_dir / "run" / "process-registry" / "harness.jsonl"
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


class TestWorkerRegistration:
    def test_spawned_worker_is_registered_and_teardown_reaps_it(self, tmp_path):
        od = _load_operatord(tmp_path)
        worker = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(300)"],
            start_new_session=True,
        )
        try:
            od._register_worker_process(worker.pid, ENVELOPE)

            entries = [
                e for e in _registry_entries(tmp_path)
                if e.get("event") == "register" and e.get("role") == "operator-task"
            ]
            assert entries, _registry_entries(tmp_path)
            assert entries[-1]["pid"] == worker.pid
            assert entries[-1].get("meta", {}).get("task_id") == ENVELOPE["task_id"]
            assert entries[-1].get("cmdline"), "diagnostic command snapshot is required"
            assert entries[-1].get("birth_id"), "stable process-birth identity is required"

            result = rpr.teardown("harness", grace_s=0.5, kill_grace_s=0.5, harness_dir=tmp_path)
            deadline = time.time() + 5
            while worker.poll() is None and time.time() < deadline:
                time.sleep(0.1)
            assert worker.poll() is not None, (
                f"teardown must reap the registered worker (teardown={result})"
            )
        finally:
            if worker.poll() is None:
                os.killpg(os.getpgid(worker.pid), signal.SIGKILL)

    def test_detached_codex_process_group_is_registered_and_fully_reaped(
        self, tmp_path, monkeypatch
    ):
        """RC9 live red: killing the outer operator left Codex's own session.

        The registered Codex group contains a leader plus a child, mirroring
        the Node wrapper/native Codex pair seen in the installed run. Teardown
        must own and reap the complete dedicated group, not only its leader.
        """
        child_pid_path = tmp_path / "codex-child.pid"
        leader = subprocess.Popen(
            [
                sys.executable,
                "-c",
                (
                    "import pathlib, subprocess, sys, time; "
                    "child=subprocess.Popen([sys.executable, '-c', "
                    "'import time; time.sleep(300)']); "
                    f"pathlib.Path({str(child_pid_path)!r}).write_text(str(child.pid)); "
                    "time.sleep(300)"
                ),
            ],
            start_new_session=True,
        )
        child_pid = 0
        try:
            deadline = time.time() + 5
            while time.time() < deadline and not child_pid_path.exists():
                time.sleep(0.05)
            assert child_pid_path.exists(), "fixture group leader never spawned its child"
            child_pid = int(child_pid_path.read_text(encoding="utf-8"))
            assert rpr._running(leader.pid) and rpr._running(child_pid)

            monkeypatch.setenv("HARNESS_DIR", str(tmp_path))
            codex_operator = _load_codex_operator(tmp_path)
            assert codex_operator._register_codex_process_group(leader.pid) is True

            registrations = [
                e for e in _registry_entries(tmp_path)
                if e.get("event") == "register"
                and e.get("role") == "operator-task-child"
            ]
            assert registrations, _registry_entries(tmp_path)
            assert registrations[-1].get("signal_scope") == "process_group"
            assert registrations[-1].get("pgid") == leader.pid

            result = rpr.teardown(
                "harness", grace_s=0.5, kill_grace_s=0.5, harness_dir=tmp_path
            )
            leader.wait(timeout=5)
            deadline = time.time() + 5
            while rpr._running(child_pid) and time.time() < deadline:
                time.sleep(0.05)
            assert result["ok"] is True, result
            assert not rpr._running(child_pid), (
                f"registered Codex process-group child survived teardown: {result}"
            )
        finally:
            try:
                os.killpg(leader.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            if leader.poll() is None:
                leader.wait(timeout=5)

    def test_process_group_identity_mismatch_is_never_signalled(self, tmp_path):
        leader = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(300)"],
            start_new_session=True,
        )
        try:
            rpr.register(
                "harness",
                "operator-task-child",
                leader.pid,
                harness_dir=tmp_path,
                signal_scope="process_group",
            )
            registry_path = tmp_path / "run" / "process-registry" / "harness.jsonl"
            records = [json.loads(line) for line in registry_path.read_text().splitlines()]
            records[0]["session_id"] = leader.pid + 1
            registry_path.write_text(
                "\n".join(json.dumps(record) for record in records) + "\n",
                encoding="utf-8",
            )

            result = rpr.teardown(
                "harness", grace_s=0.1, kill_grace_s=0.1, harness_dir=tmp_path
            )
            assert leader.poll() is None, result
            assert {
                "pid": leader.pid,
                "why": "process_group_identity_mismatch",
            } in result["skipped"]
        finally:
            try:
                os.killpg(leader.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            leader.wait(timeout=5)

    def test_terminal_run_refuses_registration_without_breaking(self, tmp_path):
        od = _load_operatord(tmp_path)
        rpr.mark_terminal("harness", reason="test", harness_dir=tmp_path)
        worker = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            start_new_session=True,
        )
        try:
            od._register_worker_process(worker.pid, ENVELOPE)  # must not raise
            entries = [
                e for e in _registry_entries(tmp_path)
                if e.get("event") == "register" and e.get("role") == "operator-task"
            ]
            assert not entries, entries
        finally:
            os.killpg(os.getpgid(worker.pid), signal.SIGKILL)

    def test_worker_exec_keeps_same_identity_and_is_reaped(self, tmp_path):
        """Exact RC9 live failure: bash registered, then exec'd Python/Codex.

        Command text legitimately changes across exec while the PID and process
        birth remain the same.  Teardown must not misclassify that transition
        as PID reuse and leave the worker running.
        """
        od = _load_operatord(tmp_path)
        release = tmp_path / "exec-now"
        worker = subprocess.Popen(
            [
                "bash",
                "-c",
                f"while [ ! -e {release!s} ]; do sleep 0.02; done; exec sleep 300",
            ],
            start_new_session=True,
        )
        try:
            od._register_worker_process(worker.pid, ENVELOPE)
            registered = [
                e for e in _registry_entries(tmp_path)
                if e.get("event") == "register" and e.get("pid") == worker.pid
            ][-1]
            before_cmdline = registered.get("cmdline")
            assert before_cmdline and "bash" in before_cmdline

            release.touch()
            deadline = time.time() + 5
            while time.time() < deadline:
                current = rpr._read_cmdline(worker.pid)
                if current and current != before_cmdline and "sleep 300" in current:
                    break
                time.sleep(0.05)
            else:
                pytest.fail("worker never completed the controlled exec transition")

            result = rpr.teardown(
                "harness", grace_s=0.5, kill_grace_s=0.5, harness_dir=tmp_path
            )
            worker.wait(timeout=5)
            assert worker.returncode is not None
            assert not any(
                item.get("pid") == worker.pid and item.get("why") == "pid_reused"
                for item in result["skipped"]
            ), result
        finally:
            if worker.poll() is None:
                os.killpg(os.getpgid(worker.pid), signal.SIGKILL)


class TestDaemonOnceRegistersWorker:
    """Real operatord --once with a command backend: after the run, the
    registry must contain the worker's registration (append-only, so the
    assertion is timing-free)."""

    OPERATOR_ID = "test-command-builder"

    def _setup(self, tmp_path: Path) -> dict:
        (tmp_path / "config").mkdir(parents=True)
        (tmp_path / "personas").mkdir(parents=True)
        (tmp_path / "tools").mkdir(parents=True)
        (tmp_path / "config" / "physical-operators.json").write_text(json.dumps({
            "version": 1,
            "operators": {
                self.OPERATOR_ID: {
                    "display_name": "Test Command Builder",
                    "role": "builder",
                    "persona": "builder",
                    "backend": "command",
                    "model": "local-command",
                    "enabled": True,
                }
            },
        }, indent=2))
        real_persona = _HARNESS / "personas" / "builder.md"
        dest = tmp_path / "personas" / "builder.md"
        if real_persona.exists():
            shutil.copy(real_persona, dest)
        else:
            dest.write_text("# Builder\nYou are a builder.")
        env = {**os.environ, "HARNESS_DIR": str(tmp_path)}
        env["COMMAND_AGENT"] = f"{sys.executable} -c \"print('worker ran')\""
        return env

    def test_daemon_once_registers_the_worker_pid(self, tmp_path):
        env = self._setup(tmp_path)
        envelope_path = tmp_path / "envelope.json"
        envelope_path.write_text(json.dumps(ENVELOPE))
        submit = subprocess.run(
            [sys.executable, str(_LIB / "operator_runtime.py"), "submit",
             "--envelope", str(envelope_path)],
            env=env, capture_output=True, text=True, timeout=15,
        )
        assert submit.returncode == 0, submit.stderr
        daemon = subprocess.run(
            [sys.executable, str(_HARNESS / "tools" / "operatord.py"), "daemon",
             "--operator", self.OPERATOR_ID, "--once", "--poll-interval", "0.2"],
            env=env, capture_output=True, text=True, timeout=60,
        )
        assert daemon.returncode == 0, f"stdout={daemon.stdout}\nstderr={daemon.stderr}"
        entries = [
            e for e in _registry_entries(tmp_path)
            if e.get("event") == "register" and e.get("role") == "operator-task"
        ]
        assert entries, (
            "operatord must register its spawned worker in the harness run "
            f"registry; registry={_registry_entries(tmp_path)}"
        )
        assert entries[-1].get("meta", {}).get("task_id") == ENVELOPE["task_id"]
        daemon_entries = [
            e for e in _registry_entries(tmp_path)
            if e.get("event") == "register" and e.get("role") == "operatord"
        ]
        assert daemon_entries, (
            "operator_runtime's real auto-kicked operatord must be owned by "
            f"the harness registry; registry={_registry_entries(tmp_path)}"
        )
        assert daemon_entries[-1].get("meta", {}).get("operator_id") == self.OPERATOR_ID
