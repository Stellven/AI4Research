from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest


REPO = Path(__file__).resolve().parents[3]
HARNESS = REPO / "harness"
STATUS_SERVER = HARNESS / "lib" / "symphony" / "status-server.py"
AUTH_HELPER = HARNESS / "auth-helpers.sh"


def _load_status_server() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "phase22_authentication_session_security_status_server",
        STATUS_SERVER,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {STATUS_SERVER}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _bash_executable() -> str | None:
    executable = shutil.which("bash")
    if executable:
        return executable
    git_bash = Path(r"C:\Program Files\Git\bin\bash.exe")
    return str(git_bash) if git_bash.exists() else None


def test_authentication_session_security_provider_authenticated_live_status() -> None:
    if os.environ.get("SOLAR_LIVE_AUTH_STATUS_TEST") != "1":
        pytest.skip("Set SOLAR_LIVE_AUTH_STATUS_TEST=1 to inspect the current CLI-owned auth state.")
    bash = _bash_executable()
    if not bash:
        pytest.skip("A bash runtime is required to execute harness/auth-helpers.sh status.")

    completed = subprocess.run(
        [bash, str(AUTH_HELPER), "status"],
        cwd=REPO,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=15,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["ok"] is True
    assert payload["codex"] == "ok"
    assert payload["detail"]["codex_auth_json"] is True
    assert "token" not in payload
    assert "api_key" not in payload


class _FakeProcess:
    def __init__(self, returncode: int | None) -> None:
        self.returncode = returncode

    def poll(self) -> int | None:
        return self.returncode


def _close_login_handles(module: ModuleType) -> None:
    for entry in module._AUTH_LOGINS.values():
        handle = entry.get("fh")
        if handle and not handle.closed:
            handle.close()
    module._AUTH_LOGINS.clear()


def test_authentication_session_security_login_start_spawns_device_auth_helper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_status_server()
    harness_dir = tmp_path / "harness"
    helper = harness_dir / "auth-helpers.sh"
    helper.parent.mkdir(parents=True)
    helper.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    monkeypatch.setattr(module, "HARNESS_DIR", harness_dir)
    module._AUTH_LOGINS.clear()
    captured: dict[str, Any] = {}

    def fake_popen(args: list[str], **kwargs: Any) -> _FakeProcess:
        captured["args"] = args
        captured["kwargs"] = kwargs
        return _FakeProcess(None)

    monkeypatch.setattr(module.subprocess, "Popen", fake_popen)
    try:
        result = module._auth_login_start("codex")
        assert result == {"ok": True, "provider": "codex", "state": "started"}
        assert captured["args"] == ["bash", str(helper), "login", "codex"]
        assert captured["kwargs"]["stdin"] is subprocess.DEVNULL
        assert captured["kwargs"]["start_new_session"] is True
        assert module._AUTH_LOGINS["codex"]["log"].name == "auth-login-codex.log"
    finally:
        _close_login_handles(module)


def test_authentication_session_security_login_status_reports_completed_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_status_server()
    log_path = tmp_path / "auth-login-codex.log"
    log_path.write_text(
        "Open https://auth.openai.com/device and enter ABCD-EFGH\n",
        encoding="utf-8",
    )
    module._AUTH_LOGINS.clear()
    module._AUTH_LOGINS["codex"] = {
        "proc": _FakeProcess(0),
        "log": log_path,
        "fh": None,
        "started": 1.0,
    }
    monkeypatch.setattr(
        module,
        "_auth_status_payload",
        lambda: {"ok": True, "codex": "ok", "source": "controlled-test"},
    )
    try:
        result = module._auth_login_status("codex")
        assert result["ok"] is True
        assert result["provider"] == "codex"
        assert result["state"] == "done"
        assert result["exit_code"] == 0
        assert result["url"] == "https://auth.openai.com/device"
        assert result["code"] == "ABCD-EFGH"
        assert result["auth"]["codex"] == "ok"
        assert "api_key" not in json.dumps(result).lower()
    finally:
        _close_login_handles(module)
