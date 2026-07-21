"""Runtime checks for the vendored MIA Memory-Serve service."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
from typing import Any, Dict

from . import mia_adapter


HARNESS_DIR = os.path.expanduser("~/.solar/harness")
MIA_DIR = os.path.join(HARNESS_DIR, "vendor", "MIA", "Memory-Serve")
MIA_ENTRYPOINT = os.path.join(MIA_DIR, "memory_serve.py")
LIB_EXPERIENCE_DIR = os.path.dirname(os.path.abspath(__file__))
WRAPPER = os.path.join(LIB_EXPERIENCE_DIR, "memory_serve_wrapper.py")
VENV_PYTHON = os.path.join(HARNESS_DIR, "venvs", "mia-memory-serve", "bin", "python3")
STATE_DIR = os.path.join(HARNESS_DIR, "run")
PID_FILE = os.path.join(STATE_DIR, "mia-memory-serve.pid")
LOG_FILE = os.path.join(STATE_DIR, "mia-memory-serve.log")

# Modules required inside the venv (flask) or inherited via --system-site-packages
REQUIRED_MODULES = ("openai", "transformers", "torch", "numpy", "dotenv")

_DEFAULT_BERT = os.path.join(
    os.path.expanduser("~"),
    ".cache", "huggingface", "hub",
    "models--sentence-transformers--all-MiniLM-L6-v2",
    "snapshots", "c9745ed1d9f207416be6d2e6f8de32d1f16199bf",
)


def _venv_python() -> str:
    return VENV_PYTHON if os.path.exists(VENV_PYTHON) else sys.executable


def _module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _venv_has_flask() -> bool:
    """Check that the venv's python can import flask."""
    try:
        result = subprocess.run(
            [_venv_python(), "-c", "import flask"],
            capture_output=True, timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


def dependency_status() -> Dict[str, Any]:
    missing = [name for name in REQUIRED_MODULES if not _module_available(name)]
    local_missing = []
    if not os.path.exists(MIA_ENTRYPOINT):
        local_missing.append(MIA_ENTRYPOINT)
    if not os.path.exists(WRAPPER):
        local_missing.append(WRAPPER)
    venv_ok = os.path.exists(VENV_PYTHON) and _venv_has_flask()
    bert_path = os.environ.get("MIA_BERT_PATH", _DEFAULT_BERT)
    bert_ok = os.path.isdir(bert_path)
    return {
        "ok": not missing and not local_missing and venv_ok and bert_ok,
        "missing_python_modules": missing,
        "missing_files": local_missing,
        "venv_ok": venv_ok,
        "venv_python": VENV_PYTHON,
        "bert_path": bert_path,
        "bert_ok": bert_ok,
        "entrypoint": MIA_ENTRYPOINT,
        "wrapper": WRAPPER,
    }


def _pid_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def pid_status() -> Dict[str, Any]:
    if not os.path.exists(PID_FILE):
        return {"pid": None, "running": False, "pid_file": PID_FILE}
    try:
        with open(PID_FILE, encoding="utf-8") as f:
            pid = int(f.read().strip())
    except Exception as exc:
        return {"pid": None, "running": False, "pid_file": PID_FILE, "reason": str(exc)}
    return {"pid": pid, "running": _pid_running(pid), "pid_file": PID_FILE}


def status() -> Dict[str, Any]:
    deps = dependency_status()
    pid = pid_status()
    runtime = mia_adapter.health()
    state = "ok" if runtime.get("ok") else "pending"
    if not deps.get("ok"):
        state = "missing_dependency"
    return {
        "ok": bool(runtime.get("ok")),
        "status": state,
        "adapter": runtime,
        "dependencies": deps,
        "process": pid,
        "log_file": LOG_FILE,
    }


def start(host: str = "127.0.0.1", port: int = 5197, *, dry_run: bool = False) -> Dict[str, Any]:
    """Start MIA Memory-Serve via the Solar wrapper (venv python, in-memory patches).

    Does not install dependencies or mutate the vendored upstream tree.
    """
    deps = dependency_status()
    if not deps.get("ok"):
        return {"ok": False, "status": "missing_dependency", "dependencies": deps}

    venv_py = _venv_python()
    cmd = [venv_py, WRAPPER, "--host", host, "--port", str(port)]
    env = {**os.environ, "MIA_BERT_PATH": os.environ.get("MIA_BERT_PATH", _DEFAULT_BERT)}

    if dry_run:
        return {"ok": True, "status": "dry_run", "cmd": cmd, "env_bert": env["MIA_BERT_PATH"]}

    current = mia_adapter.health(timeout=0.2)
    if current.get("ok"):
        return {"ok": True, "status": "already_running", "adapter": current}

    os.makedirs(STATE_DIR, exist_ok=True)
    log = open(LOG_FILE, "a", encoding="utf-8")
    proc = subprocess.Popen(
        cmd,
        cwd=MIA_DIR,
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    with open(PID_FILE, "w", encoding="utf-8") as f:
        f.write(str(proc.pid))

    # BERT model loading can take 15–30 s on first run; allow 60 s total
    deadline = time.time() + 60
    last = {}
    while time.time() < deadline:
        last = mia_adapter.health(timeout=0.5)
        if last.get("ok"):
            return {"ok": True, "status": "started", "pid": proc.pid, "adapter": last}
        time.sleep(1.0)
    return {"ok": False, "status": "start_timeout", "pid": proc.pid, "adapter": last, "log_file": LOG_FILE}


def main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "status"
    if cmd == "status":
        print(json.dumps(status(), ensure_ascii=False))
        return 0
    if cmd == "start":
        dry_run = "--dry-run" in argv
        print(json.dumps(start(dry_run=dry_run), ensure_ascii=False))
        return 0
    print(json.dumps({"ok": False, "error": f"unknown command: {cmd}"}))
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
