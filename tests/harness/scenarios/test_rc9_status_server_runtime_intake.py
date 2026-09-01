"""RC9 dashboard intake must use the runtime selected in current config.

The status server can outlive a dashboard settings change.  A server started
under Claude therefore carries Claude/Anthropic defaults in ``os.environ``
even after the user selects Codex.  Intake subprocesses must be pinned from
the current persisted config, not from that stale process environment.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


_HARNESS = (Path(__file__).resolve().parents[3] / 'harness')
_STATUS_SERVER = _HARNESS / "lib" / "symphony" / "status-server.py"


def _load_status_server():
    spec = importlib.util.spec_from_file_location(
        "rc9_status_server_runtime_intake", _STATUS_SERVER
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("configured_runtime", "stale_runtime", "stale_provider", "expected_provider"),
    [
        ("codex", "claude", "anthropic", "openai"),
        ("claude", "codex", "openai", "anthropic"),
    ],
)
def test_intake_reloads_runtime_provider_defaults_after_settings_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    configured_runtime: str,
    stale_runtime: str,
    stale_provider: str,
    expected_provider: str,
):
    status_server = _load_status_server()
    harness_dir = tmp_path / "harness"
    config_path = harness_dir / "config" / "solar-user-config.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        json.dumps({"runtime": configured_runtime}), encoding="utf-8"
    )

    status_server.HARNESS_DIR = harness_dir
    status_server.SPRINTS_DIR = harness_dir / "sprints"
    status_server._USER_CONFIG_PATH = config_path
    monkeypatch.setattr(status_server, "_intake_command", lambda _task: [sys.executable])
    monkeypatch.setenv("SOLAR_PANE_RUNTIME", stale_runtime)
    monkeypatch.setenv("SOLAR_PM_DEFAULT_PROVIDERS", stale_provider)
    monkeypatch.setenv("SOLAR_MULTI_TASK_DEFAULT_PROVIDERS", stale_provider)

    captured: dict = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["env"] = dict(kwargs["env"])
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="Sprint created: sprint-runtime-config\n",
            stderr="",
        )

    monkeypatch.setattr(status_server.subprocess, "run", fake_run)

    result = status_server._intake_payload({"task": "build a small CLI"})

    assert result["ok"] is True
    assert captured["env"]["SOLAR_PANE_RUNTIME"] == configured_runtime
    assert captured["env"]["SOLAR_PM_DEFAULT_PROVIDERS"] == expected_provider
    assert (
        captured["env"]["SOLAR_MULTI_TASK_DEFAULT_PROVIDERS"]
        == expected_provider
    )


def test_intake_reports_cli_failure_instead_of_missing_sprint_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    status_server = _load_status_server()
    harness_dir = tmp_path / "harness"
    harness_dir.mkdir()
    status_server.HARNESS_DIR = harness_dir
    status_server.SPRINTS_DIR = harness_dir / "sprints"
    monkeypatch.setattr(status_server, "_intake_command", lambda _task: [sys.executable])
    monkeypatch.setattr(status_server, "_intake_subprocess_env", lambda: {})
    monkeypatch.setattr(
        status_server,
        "_classify_intake_request",
        lambda _task, _env, explicit_workflow_id="": {"applied": False},
    )
    monkeypatch.setattr(
        status_server.subprocess,
        "run",
        lambda command, **_kwargs: subprocess.CompletedProcess(
            command,
            1,
            stdout="",
            stderr="ModuleNotFoundError: No module named 'referencing'\n",
        ),
    )

    result = status_server._intake_payload({"task": "build a small CLI"})

    assert result["ok"] is False
    assert result["sprint_id"] == ""
    assert result["error"] == "intake_cli_failed"
    assert result["returncode"] == 1
