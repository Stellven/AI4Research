#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import notebooklm_operator as nlo  # noqa: E402


def test_build_notebooklm_request_derives_name_and_output_dir(tmp_path):
    envelope = {
        "task_id": "T1",
        "sprint_id": "sprint-x",
        "node_id": "N2",
        "logical_operator": "NotebookLMEnricher",
        "objective": "Create mindmap",
        "source_files": ["/tmp/a.md"],
        "metadata": {"date": "2026-05-27", "notebook_group": "AI Influence"},
    }
    payload = nlo.build_notebooklm_request(envelope, task_dir=tmp_path)
    assert payload["notebook_name"] == "AI Influence 2026-05-27"
    assert payload["output_dir"] == str((tmp_path / "notebooklm-output").resolve())
    assert payload["metadata"]["logical_operator"] == "NotebookLMEnricher"
    assert payload["metadata"]["task_id"] == "T1"


def test_build_notebooklm_request_prefers_inline_request(tmp_path):
    envelope = {
        "task_id": "T2",
        "notebooklm_request": {
            "source_files": ["/tmp/a.md"],
            "notebook_name": "Explicit Notebook",
            "metadata": {"date": "2026-05-27"},
        },
    }
    payload = nlo.build_notebooklm_request(envelope, task_dir=tmp_path)
    assert payload["notebook_name"] == "Explicit Notebook"
    assert payload["source_files"] == ["/tmp/a.md"]


def test_notebooklm_wrapper_cmd_falls_back_to_bundled(monkeypatch):
    monkeypatch.delenv("TECH_HOTSPOT_BROWSER_NOTEBOOKLM_CMD", raising=False)
    monkeypatch.delenv("BROWSER_AGENT_NOTEBOOKLM_CMD", raising=False)
    monkeypatch.setattr(nlo, "DEFAULT_WRAPPER", Path("/tmp/browser_agent_notebooklm_wrapper.py"))
    monkeypatch.setattr(nlo, "DEFAULT_BROWSER_USE_PYTHON", Path("/tmp/browser-use-python"))
    monkeypatch.setattr(Path, "exists", lambda self: str(self) in {"/tmp/browser_agent_notebooklm_wrapper.py", "/tmp/browser-use-python"})
    cmd = nlo.notebooklm_wrapper_cmd()
    assert cmd == ["/tmp/browser-use-python", "/tmp/browser_agent_notebooklm_wrapper.py"]


def test_run_notebooklm_request_writes_result(monkeypatch, tmp_path, capsys):
    response = {
        "ok": True,
        "notebook_name": "AI Influence 2026-05-27",
        "notebook_title": "AI Influence 2026-05-27",
        "source_count": 2,
        "mindmap": {"status": "ready"},
        "infographics": [{"title": "图一"}],
    }

    class Result:
        returncode = 0
        stdout = json.dumps(response, ensure_ascii=False)
        stderr = ""

    monkeypatch.setattr(nlo, "notebooklm_wrapper_cmd", lambda: ["fake-wrapper"])
    monkeypatch.setattr(nlo.subprocess, "run", lambda *args, **kwargs: Result())
    payload = {
        "source_files": ["/tmp/a.md"],
        "notebook_name": "AI Influence 2026-05-27",
    }
    result = nlo.run_notebooklm_request(payload, task_dir=tmp_path)
    assert result["source_count"] == 2
    assert (tmp_path / "notebooklm-request.json").exists()
    assert (tmp_path / "notebooklm-result.json").exists()
    out = capsys.readouterr().out
    assert "NotebookLM Operator Result" in out
    assert "source_count: 2" in out


def test_main_applies_success_cooldown(monkeypatch, tmp_path):
    envelope = {
        "task_id": "T3",
        "operator_id": "mini-browser-notebooklm",
        "source_files": ["/tmp/a.md"],
    }
    envelope_path = tmp_path / "envelope.json"
    envelope_path.write_text(json.dumps(envelope), encoding="utf-8")
    monkeypatch.setenv("SOLAR_OPERATOR_ENVELOPE_JSON", str(envelope_path))
    monkeypatch.setenv("TASK_DIR", str(tmp_path / "task"))
    monkeypatch.setenv("SOLAR_NOTEBOOKLM_SUCCESS_COOLDOWN_SECONDS", "123")
    monkeypatch.setattr(
        nlo,
        "run_notebooklm_request",
        lambda request_payload, task_dir=None: {"ok": True, "source_count": 1},
    )
    monkeypatch.setattr(
        nlo.ofc,
        "ensure_operator_available",
        lambda operator_id: None,
    )
    calls: list[tuple[str, int]] = []
    monkeypatch.setattr(
        nlo.ofc,
        "apply_success_cooldown",
        lambda operator_id, *, success_cooldown_seconds: calls.append((operator_id, success_cooldown_seconds)) or {},
    )
    assert nlo.main() == 0
    assert calls == [("mini-browser-notebooklm", 123)]


def test_main_applies_rate_limit_cooldown_on_failure(monkeypatch, tmp_path, capsys):
    envelope = {
        "task_id": "T4",
        "operator_id": "mini-browser-notebooklm",
        "source_files": ["/tmp/a.md"],
    }
    envelope_path = tmp_path / "envelope.json"
    envelope_path.write_text(json.dumps(envelope), encoding="utf-8")
    monkeypatch.setenv("SOLAR_OPERATOR_ENVELOPE_JSON", str(envelope_path))
    monkeypatch.setenv("TASK_DIR", str(tmp_path / "task"))
    monkeypatch.setenv("SOLAR_NOTEBOOKLM_RATE_LIMIT_COOLDOWN_SECONDS", "321")

    def _boom(request_payload, task_dir=None):
        raise nlo.NotebookLMOperatorError("wrapper failed", combined_output="429 rate limit")

    monkeypatch.setattr(nlo, "run_notebooklm_request", _boom)
    monkeypatch.setattr(
        nlo.ofc,
        "ensure_operator_available",
        lambda operator_id: None,
    )
    calls: list[tuple[str, int, int, bool, bool]] = []
    monkeypatch.setattr(
        nlo.ofc,
        "apply_failure_flow_control",
        lambda task_dir, *, operator_id, failure_text, rate_limit_cooldown_seconds, auth_cooldown_seconds, defer_on_cooldown, defer_on_auth: calls.append(
            (operator_id, rate_limit_cooldown_seconds, auth_cooldown_seconds, defer_on_cooldown, defer_on_auth)
        ) or {"runtime_state": "cooldown"},
    )
    assert nlo.main() == 1
    assert calls == [("mini-browser-notebooklm", 321, 21600, True, True)]
    assert "notebooklm_operator failed" in capsys.readouterr().err


def test_main_applies_auth_expired_on_failure(monkeypatch, tmp_path):
    envelope = {
        "task_id": "T5",
        "operator_id": "mini-browser-notebooklm",
        "source_files": ["/tmp/a.md"],
    }
    envelope_path = tmp_path / "envelope.json"
    envelope_path.write_text(json.dumps(envelope), encoding="utf-8")
    monkeypatch.setenv("SOLAR_OPERATOR_ENVELOPE_JSON", str(envelope_path))
    monkeypatch.setenv("TASK_DIR", str(tmp_path / "task"))
    monkeypatch.setenv("SOLAR_NOTEBOOKLM_AUTH_COOLDOWN_SECONDS", "777")

    def _boom(request_payload, task_dir=None):
        raise nlo.NotebookLMOperatorError("wrapper failed", combined_output="sign in required")

    monkeypatch.setattr(nlo, "run_notebooklm_request", _boom)
    monkeypatch.setattr(
        nlo.ofc,
        "ensure_operator_available",
        lambda operator_id: None,
    )
    calls: list[tuple[str, int, int, bool, bool]] = []
    monkeypatch.setattr(
        nlo.ofc,
        "apply_failure_flow_control",
        lambda task_dir, *, operator_id, failure_text, rate_limit_cooldown_seconds, auth_cooldown_seconds, defer_on_cooldown, defer_on_auth: calls.append(
            (operator_id, rate_limit_cooldown_seconds, auth_cooldown_seconds, defer_on_cooldown, defer_on_auth)
        ) or {"runtime_state": "auth_expired"},
    )
    assert nlo.main() == 1
    assert calls == [("mini-browser-notebooklm", 3600, 777, True, True)]
