"""G4-lite run 4 — the health gate must prove server OWNERSHIP, not liveness.

Evidence (p5-g4-lite-live-rung-20260710T175744Z,
STATUS_SERVER_OWNERSHIP_MISMATCH): a stale rehearsal status-server held
port 8765. The fresh sandbox's server did NOT die — it silently took the
next port (the server's designed 8765-8775 fallback) — while every
hardcoded-8765 probe (healthz "ok", POST /intake) talked to the ALIEN
server, and the run flowed into the wrong harness. Liveness at a fixed
port proves nothing about WHOSE server answered — the start-side sibling
of the run-2/f4efa503 stop-side ownership class.

Fix under test: /runtime-info reports the server's HARNESS_DIR, so any
client can verify the responder is its own harness. (The operator briefs
additionally derive the port from the harness's own run/status-server.port
file, so the fixed-port assumption is gone end to end.)

The test runs the REAL status-server as a subprocess against a tmp
harness, reads the port it actually bound from run/status-server.port,
and asserts /runtime-info identifies that harness.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

_HARNESS = Path(__file__).resolve().parents[2]


def test_runtime_info_reports_the_owning_harness(tmp_path):
    harness_dir = tmp_path / "sandbox-harness"
    (harness_dir / "run").mkdir(parents=True)
    env = {**os.environ, "HARNESS_DIR": str(harness_dir)}
    proc = subprocess.Popen(
        [sys.executable, "-u", str(_HARNESS / "lib" / "symphony" / "status-server.py")],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        port_file = harness_dir / "run" / "status-server.port"
        deadline = time.time() + 30
        while not port_file.exists():
            assert proc.poll() is None, "status-server exited before binding"
            assert time.time() < deadline, "status-server never wrote its port file"
            time.sleep(0.2)
        port = int(port_file.read_text().strip())

        info = None
        deadline = time.time() + 15
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/runtime-info", timeout=3
                ) as resp:
                    info = json.loads(resp.read().decode("utf-8"))
                break
            except Exception:
                time.sleep(0.3)
        assert info is not None, "runtime-info unreachable on the bound port"
        assert info.get("harness_dir") == str(harness_dir), info
        assert info.get("port") == port, info
    finally:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
