"""G3 run-2 fix-round: status-server lifecycle must be scoped to ITS harness.

G3 live rung 2 (run-archive/p5-g3-live-rung-20260709T190808Z,
RUN_SETUP_FAILED_NO_INTAKE): the sandbox status server answered /healthz at
19:09:53Z and refused connections by 19:10:14Z — killed silently, empty
stderr. Root cause is in `solar-harness.sh status-server stop`: it probes
ports 8765-8775 for ANY /healthz responder and lsof-kills EVERY listener on
those ports, machine-wide, plus it kills a fixed global tmux session name.
With parallel harness sessions on one machine (the standing situation), any
session's stop/restart kills every other session's status server — the
contamination/cleanup failure class landing inside the P5 campaign.

These tests run the REAL solar-harness.sh with HARNESS_DIR pointed at a tmp
harness (line 17 makes it env-respecting) and pin the scoping contract:

- a foreign /healthz listener in the swept port range SURVIVES this
  harness's stop;
- this harness's own server (pidfile-recorded, or args matching
  $HARNESS_DIR/lib/symphony/status-server.py) is still killed;
- start does not adopt a foreign listener as "already running".
"""
from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

_HARNESS = (Path(__file__).resolve().parents[3] / 'harness')
_SCRIPT = _HARNESS / "solar-harness.sh"

_SWEEP_PORTS = range(8766, 8776)  # stay off 8765 (a real dev server may own it)


def _free_sweep_port() -> int:
    for port in _SWEEP_PORTS:
        with socket.socket() as sock:
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    pytest.skip("no free port in the 8766-8775 sweep range")


_HEALTHZ_SERVER = textwrap.dedent(
    """
    import sys
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
        def log_message(self, *a):
            pass

    HTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
    """
)


def _wait_healthz(port: int, timeout: float = 5.0) -> bool:
    import urllib.request

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=1):
                return True
        except Exception:
            time.sleep(0.1)
    return False


def _tmp_harness(tmp_path: Path) -> Path:
    harness = tmp_path / "harness"
    (harness / "run").mkdir(parents=True)
    (harness / "lib" / "symphony").mkdir(parents=True)
    # solar-harness.sh hard-sources these helpers from $HARNESS_DIR
    for helper in ("run-state.sh", "harness-config.sh"):
        src = _HARNESS / "lib" / helper
        if src.exists():
            (harness / "lib" / helper).write_bytes(src.read_bytes())
    return harness


def _run_ss(harness: Path, action: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["HARNESS_DIR"] = str(harness)
    return subprocess.run(
        ["bash", str(_SCRIPT), "status-server", action],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


@pytest.fixture
def foreign_server():
    """A /healthz listener that does NOT belong to the tmp harness — it
    stands in for another session's status server on the shared port range."""
    port = _free_sweep_port()
    proc = subprocess.Popen(
        [sys.executable, "-c", _HEALTHZ_SERVER, str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    assert _wait_healthz(port), "foreign fixture server never came up"
    yield proc, port
    if proc.poll() is None:
        proc.send_signal(signal.SIGKILL)
    proc.wait(timeout=10)


def test_stop_spares_foreign_healthz_listener(tmp_path, foreign_server):
    """The G3 run-2 killer: stop's port sweep must not kill a listener whose
    process does not belong to THIS harness."""
    proc, port = foreign_server
    harness = _tmp_harness(tmp_path)

    result = _run_ss(harness, "stop")

    assert result.returncode == 0, result.stderr
    time.sleep(0.5)
    assert proc.poll() is None, (
        f"status-server stop killed a foreign listener on port {port} "
        f"(machine-global sweep): {result.stdout} {result.stderr}"
    )
    assert _wait_healthz(port, timeout=2), "foreign server no longer serving"


def test_stop_kills_own_pidfile_server(tmp_path):
    """Scoping must not weaken legitimate cleanup: a pid recorded in THIS
    harness's pidfile whose process belongs to this harness is stopped."""
    harness = _tmp_harness(tmp_path)
    own = harness / "lib" / "symphony" / "status-server.py"
    own.write_text("import time\ntime.sleep(300)\n", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, str(own)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        (harness / "run" / "status-server.pid").write_text(f"{proc.pid}\n", encoding="utf-8")

        result = _run_ss(harness, "stop")

        assert result.returncode == 0, result.stderr
        deadline = time.time() + 5
        while time.time() < deadline and proc.poll() is None:
            time.sleep(0.1)
        assert proc.poll() is not None, "own pidfile server was not stopped"
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=10)


def test_stop_kills_own_path_matched_server_without_pidfile(tmp_path):
    """The ps-args matcher (scoped by $HARNESS_DIR script path) still reaps a
    this-harness server that lost its pidfile."""
    harness = _tmp_harness(tmp_path)
    own = harness / "lib" / "symphony" / "status-server.py"
    own.write_text("import time\ntime.sleep(300)\n", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, str(own)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        result = _run_ss(harness, "stop")

        assert result.returncode == 0, result.stderr
        deadline = time.time() + 5
        while time.time() < deadline and proc.poll() is None:
            time.sleep(0.1)
        assert proc.poll() is not None, "own path-matched server was not stopped"
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=10)


def test_start_does_not_adopt_foreign_listener(tmp_path, foreign_server):
    """Pre-fix, start's ports-only "healed from live runtime" branch adopted
    ANY /healthz responder in the range as this harness's server (writing its
    port into the port file and skipping startup). A foreign listener must
    not satisfy "already running"."""
    proc, port = foreign_server
    harness = _tmp_harness(tmp_path)
    # A real (if trivial) server script so a genuine start has something to
    # exec; it exits immediately, which is fine — the assertion is only about
    # the adoption decision, not about a successful boot.
    (harness / "lib" / "symphony" / "status-server.py").write_text(
        "raise SystemExit(0)\n", encoding="utf-8"
    )

    result = _run_ss(harness, "start")

    # The intentionally trivial owned server exits immediately, so start must
    # report readiness failure. The contract under test is that the foreign
    # healthy listener was not adopted as this harness's server.
    assert result.returncode != 0, result.stdout
    port_file = harness / "run" / "status-server.port"
    recorded = port_file.read_text(encoding="utf-8").strip() if port_file.exists() else ""
    assert recorded != str(port), (
        f"start adopted the foreign listener on port {port} as its own: "
        f"{result.stdout}"
    )
    assert proc.poll() is None, "start killed the foreign listener"
    # cleanup: reap whatever start may have spawned for this tmp harness
    _run_ss(harness, "stop")
