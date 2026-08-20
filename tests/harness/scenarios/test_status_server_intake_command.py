from __future__ import annotations

import base64
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


_HARNESS = Path(__file__).resolve().parents[3] / "harness"
_STATUS_SERVER = _HARNESS / "lib" / "symphony" / "status-server.py"


def _load_status_server():
    spec = importlib.util.spec_from_file_location(
        "status_server_intake_command", _STATUS_SERVER
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_intake_prefers_harness_local_cli_over_ambient_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    status_server = _load_status_server()
    harness = tmp_path / "harness"
    harness.mkdir()
    script = harness / "solar-harness.sh"
    script.write_text("#!/bin/bash\n", encoding="utf-8")

    status_server.HARNESS_DIR = harness
    monkeypatch.setattr(status_server, "_running_on_windows", lambda: False)
    monkeypatch.setattr(
        status_server.shutil,
        "which",
        lambda name: "/ambient/windows/solar.exe" if name == "solar" else None,
    )

    command = status_server._intake_command("test prompt")

    assert command == [str(script), "intake", "--request", "test prompt"]


def test_windows_intake_runs_harness_script_inside_wsl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    status_server = _load_status_server()
    harness = tmp_path / "harness"
    harness.mkdir()
    script = harness / "solar-harness.sh"
    script.write_text("#!/bin/bash\n", encoding="utf-8")

    status_server.HARNESS_DIR = harness
    monkeypatch.setattr(status_server, "_running_on_windows", lambda: True)
    monkeypatch.setattr(
        status_server.shutil,
        "which",
        lambda name: r"C:\Windows\System32\wsl.exe" if name == "wsl.exe" else None,
    )

    command = status_server._intake_command("test prompt")

    assert command[0] == r"C:\Windows\System32\wsl.exe"
    assert command[1:3] == ["--exec", "env"]
    assert "/bin/bash" in command
    assert command[-3:] == ["intake", "--request", "test prompt"]


def test_windows_path_is_translated_for_wsl() -> None:
    status_server = _load_status_server()

    assert (
        status_server._windows_path_for_wsl(r"C:\p22all\harness\solar-harness.sh")
        == "/mnt/c/p22all/harness/solar-harness.sh"
    )


def test_intake_launch_failure_is_structured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    status_server = _load_status_server()
    harness = tmp_path / "harness"
    harness.mkdir()
    status_server.HARNESS_DIR = harness
    status_server.SPRINTS_DIR = harness / "sprints"
    monkeypatch.setattr(
        status_server, "_intake_command", lambda _task: [sys.executable]
    )

    def fail_to_launch(*_args, **_kwargs):
        raise OSError(193, "not a valid application")

    monkeypatch.setattr(status_server.subprocess, "run", fail_to_launch)

    result = status_server._intake_payload({"task": "test prompt"})

    assert result["ok"] is False
    assert result["error"] == "intake_cli_launch_failed"
    assert result["request_id"].startswith("intake-")
    assert "OSError" in result["detail"]


def test_intake_upload_persists_file_and_forwards_structured_attachment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    status_server = _load_status_server()
    harness = tmp_path / "harness"
    harness.mkdir()
    status_server.HARNESS_DIR = harness
    status_server.SPRINTS_DIR = harness / "sprints"
    monkeypatch.setattr(
        status_server,
        "_intake_command",
        lambda task: [sys.executable, task],
    )
    captured: dict = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["env"] = dict(kwargs["env"])
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="Sprint created: sprint-upload\n",
            stderr="",
        )

    monkeypatch.setattr(status_server.subprocess, "run", fake_run)
    content = b"uploaded evidence\n"
    result = status_server._intake_payload(
        {
            "task": "Summarize the evidence.",
            "request_id": "upload-test",
            "attachments": [
                {
                    "name": "../evidence.txt",
                    "mime_type": "text/plain",
                    "content_base64": base64.b64encode(content).decode("ascii"),
                }
            ],
        }
    )

    assert result["ok"] is True
    assert result["sprint_id"] == "sprint-upload"
    assert len(result["attachments"]) == 1
    attachment = result["attachments"][0]
    path = Path(attachment["path"])
    assert path.parent == harness / "run" / "intake-uploads" / "upload-test"
    assert path.name == "evidence.txt"
    assert path.read_bytes() == content
    assert str(path) in captured["command"][1]
    forwarded = json.loads(captured["env"]["SOLAR_INTAKE_ATTACHMENTS_JSON"])
    assert forwarded[0]["sha256"] == attachment["sha256"]


def test_intake_upload_rejects_oversized_attachment_before_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    status_server = _load_status_server()
    harness = tmp_path / "harness"
    harness.mkdir()
    status_server.HARNESS_DIR = harness
    monkeypatch.setattr(
        status_server.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("intake launched")),
    )
    content = b"x" * (status_server._MAX_INTAKE_ATTACHMENT_BYTES + 1)

    result = status_server._intake_payload(
        {
            "task": "Read it.",
            "request_id": "too-large",
            "attachments": [
                {
                    "name": "large.bin",
                    "content_base64": base64.b64encode(content).decode("ascii"),
                }
            ],
        }
    )

    assert result["ok"] is False
    assert result["error"] == "attachment_too_large"
