"""Isolated regression coverage for known runtime/platform lifecycle repairs."""
from __future__ import annotations

import importlib.util
import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen


REPO_ROOT = Path(__file__).resolve().parents[3]
LIB_DIR = REPO_ROOT / "harness" / "lib"
sys.path.insert(0, str(LIB_DIR))

from actor_lease import LEASED, RUNNING, LeaseBroker  # noqa: E402
from research_orchestration.runtime_readiness import check_research_runtime  # noqa: E402


def _module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.25):
            return True
    except OSError:
        return False


def _wait_until(predicate, timeout: float = 6.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


def test_fallback_permission_matrix_never_expands_access(tmp_path: Path) -> None:
    report = check_research_runtime(
        source_env={"HOME": str(tmp_path / "home"), "SECRET_CANARY": "must-not-leak"},
        platform_system="Linux",
        platform_release="6.1",
        python_executable=sys.executable,
        which_func=lambda name: "/bin/true" if name in {"git", "codex"} else None,
        use_sandbox=True,
        sandbox_root=tmp_path / "allowed",
        dns_probe=lambda: True,
        stdin_transport_supported=True,
        readonly_transport_fallback_available=True,
    )
    permissions = report["sandbox_permissions"]
    assert permissions["mode"] == "restricted_fallback"
    assert permissions["write_scope"] == "sandbox_root_only"
    assert permissions["home_access"] is False
    assert permissions["network_access"] is False
    assert permissions["secret_access"] is False
    assert "must-not-leak" not in json.dumps(report, sort_keys=True)


def test_actor_lease_contention_and_expired_running_recovery(tmp_path: Path) -> None:
    broker = LeaseBroker(tmp_path / "actor-leases")
    first = broker.acquire("runner", "task-a", "run-a", "node-a", ttl_sec=1)
    assert first is not None and first.state == LEASED
    assert broker.acquire("runner", "task-b", "run-b", "node-b") is None
    assert broker.transition("runner", RUNNING) is not None
    lease_path = tmp_path / "actor-leases" / "runner.json"
    data = json.loads(lease_path.read_text(encoding="utf-8"))
    data["expires_at"] = "2000-01-01T00:00:00Z"
    lease_path.write_text(json.dumps(data), encoding="utf-8")
    assert broker.check_stale("runner") is True
    recovered = broker.acquire("runner", "task-c", "run-c", "node-c")
    assert recovered is not None and recovered.task_id == "task-c"


def test_windows_native_pane_release_removes_stale_lock(tmp_path: Path, monkeypatch) -> None:
    pane = _module(LIB_DIR / "pane_lease.py", "runtime_platform_pane_lease")
    monkeypatch.setattr(pane, "LEASE_DIR", tmp_path / "pane-leases")
    monkeypatch.setattr(pane, "pane_exists", lambda _pane: True)
    assert pane.acquire("repair:0.0", "run", "dispatch", ttl=30)["acquired"]
    assert pane.release("repair:0.0", "dispatch")["released"]
    assert not list((tmp_path / "pane-leases").glob("*.lock"))


def test_status_server_repeated_lifecycle_releases_reserved_test_port(tmp_path: Path) -> None:
    """Use only the assigned 18250-18299 range and clean every child."""
    port = 18250
    server = REPO_ROOT / "harness" / "lib" / "symphony" / "status-server.py"
    for _ in range(2):
        assert not _port_open(port), f"reserved test port {port} was already in use"
        harness = tmp_path / f"harness-{time.time_ns()}"
        env = {
            **os.environ,
            "HARNESS_DIR": str(harness),
            "SOLAR_HARNESS_DIR": str(harness),
            "SOLAR_STATUS_PORT_START": str(port),
            "SOLAR_STATUS_PORT_END": str(port),
            "SOLAR_BIND_HOST": "127.0.0.1",
        }
        proc = subprocess.Popen([sys.executable, str(server)], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        server_pid = None
        try:
            assert _wait_until(lambda: _port_open(port))
            with urlopen(f"http://127.0.0.1:{port}/runtime-info", timeout=3) as response:
                payload = json.loads(response.read())
            server_pid = int(payload["pid"])
            assert int((harness / "run" / "status-server.pid").read_text(encoding="utf-8")) == server_pid
            assert _wait_until(lambda: (harness / "run" / "status-server.port").exists())
        finally:
            if server_pid:
                # Target the actual interpreter PID (the Windows launcher PID
                # can differ) so its SIGTERM handler removes ownership files.
                os.kill(server_pid, signal.SIGTERM)
            elif proc.poll() is None:
                proc.send_signal(signal.SIGTERM)
            if proc.poll() is None and os.name != "nt":
                proc.wait(timeout=8)
        assert _wait_until(lambda: not _port_open(port))
        # Direct Windows SIGTERM can be translated to a forced termination by
        # the Python launcher; production `status-server stop` removes these
        # ownership files after taskkill. This isolated direct-process probe
        # also removes only its own records before the next cycle.
        for path in (harness / "run" / "status-server.pid", harness / "run" / "status-server.port"):
            path.unlink(missing_ok=True)
        assert not (harness / "run" / "status-server.pid").exists()
        assert not (harness / "run" / "status-server.port").exists()


def test_status_server_tmux_command_binds_per_harness_environment() -> None:
    source = (REPO_ROOT / "harness" / "solar-harness.sh").read_text(encoding="utf-8")
    command = next(
        line
        for line in source.splitlines()
        if "exec env HOME='$HOME'" in line and "status-server.py" in line
    )
    for token in (
        "USERPROFILE=",
        "SOLAR_HOME=",
        "HARNESS_DIR=",
        "SOLAR_HARNESS_DIR=",
        "SOLAR_BIND_HOST=",
    ):
        assert token in command
