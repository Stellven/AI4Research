"""Cross-platform contract tests for the small ``fcntl.flock`` shim."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


HARNESS_ROOT = Path(__file__).resolve().parents[1]
LIB_DIR = HARNESS_ROOT / "lib"
sys.path.insert(0, str(LIB_DIR))

import file_lock_compat as fcntl  # noqa: E402
import operator_flow_control as flow_control  # noqa: E402


def _child_lock(lock_path: Path) -> subprocess.CompletedProcess[str]:
    code = """
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import file_lock_compat as fcntl
with Path(sys.argv[2]).open('a+b') as handle:
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print('blocked')
    else:
        print('acquired')
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
"""
    return subprocess.run(
        [sys.executable, "-c", code, str(LIB_DIR), str(lock_path)],
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
        timeout=10,
    )


def test_file_object_lock_and_unlock(tmp_path: Path):
    with (tmp_path / "object.lock").open("a+b") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        fcntl.flock(handle, fcntl.LOCK_UN)


def test_integer_fd_lock_and_unlock(tmp_path: Path):
    with (tmp_path / "descriptor.lock").open("a+b") as handle:
        fd = handle.fileno()
        fcntl.flock(fd, fcntl.LOCK_EX)
        fcntl.flock(fd, fcntl.LOCK_UN)


def test_nonblocking_contention_between_processes(tmp_path: Path):
    lock_path = tmp_path / "contention.lock"
    with lock_path.open("a+b") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        child = _child_lock(lock_path)
        fcntl.flock(handle, fcntl.LOCK_UN)

    assert child.returncode == 0, child.stderr
    assert child.stdout.strip() == "blocked"


def test_unlock_allows_another_process_to_reacquire(tmp_path: Path):
    lock_path = tmp_path / "reacquire.lock"
    with lock_path.open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    child = _child_lock(lock_path)
    assert child.returncode == 0, child.stderr
    assert child.stdout.strip() == "acquired"


def test_operator_flow_control_fileno_call(tmp_path: Path, monkeypatch):
    registry_path = tmp_path / "physical-operators.json"
    monkeypatch.setattr(flow_control, "PHYSICAL_OPERATORS_PATH", registry_path)
    payload = {"version": 1, "operators": {}}

    flow_control._write_operator_registry(payload)

    assert json.loads(registry_path.read_text(encoding="utf-8")) == payload
