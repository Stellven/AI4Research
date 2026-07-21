#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import gemini_deep_research_operator as gdro  # noqa: E402


def test_build_request_reads_prompt_file(tmp_path):
    prompt_file = tmp_path / "prompt.txt"
    prompt_file.write_text("hello deep research", encoding="utf-8")
    payload = gdro.build_request({"prompt_file": str(prompt_file)}, task_dir=tmp_path)
    assert payload["prompt"] == "hello deep research"
    assert payload["project_name"] == "杂项"
    assert payload["expected_output"] == "markdown"
    assert payload["max_retries"] == 3


def test_run_request_writes_result(monkeypatch, tmp_path, capsys):
    class Result:
        returncode = 0
        stdout = "final research report"
        stderr = ""

    request_dir = tmp_path / "gemini-deep-research-request"
    request_dir.mkdir(parents=True, exist_ok=True)
    
    # Create mock artifacts that the wrapper is supposed to generate
    (request_dir / "assistant-response.txt").write_text("deep research report text", encoding="utf-8")
    (request_dir / "page.json").write_text(json.dumps({
        "title": "Gemini Deep Research",
        "url": "https://gemini.google.com/app/123",
        "conversation_id": "123",
        "citations": [{"title": "Paper 1", "url": "https://example.com"}]
    }), encoding="utf-8")

    monkeypatch.setattr(gdro, "_wrapper_cmd", lambda: ["fake-wrapper"])
    monkeypatch.setattr(gdro.subprocess, "run", lambda *args, **kwargs: Result())
    
    result = gdro.run_request({
        "prompt": "hello",
        "project_name": "杂项",
        "request_dir": str(request_dir)
    }, task_dir=tmp_path)
    
    assert result["ok"] is True
    assert result["text"] == "deep research report text"
    assert len(result["citations"]) == 1
    assert (tmp_path / "gemini-deep-research-request.json").exists()
    assert (tmp_path / "gemini-deep-research-result.json").exists()
    assert (tmp_path / "report.md").exists()
    
    out = capsys.readouterr().out
    assert "Gemini Deep Research Result" in out
    assert "Paper 1" in out


def test_run_request_retries_on_failure(monkeypatch, tmp_path):
    class FailResult:
        returncode = 1
        stdout = ""
        stderr = "Network Timeout Error"
        
    class SuccessResult:
        returncode = 0
        stdout = "report"
        stderr = ""

    request_dir = tmp_path / "gemini-deep-research-request"
    request_dir.mkdir(parents=True, exist_ok=True)
    
    calls = []
    
    def mock_run(*args, **kwargs):
        calls.append(len(calls) + 1)
        if len(calls) == 1:
            return FailResult()
        # On second attempt, write files and succeed
        (request_dir / "assistant-response.txt").write_text("recovered text", encoding="utf-8")
        return SuccessResult()

    monkeypatch.setattr(gdro, "_wrapper_cmd", lambda: ["fake-wrapper"])
    monkeypatch.setattr(gdro.subprocess, "run", mock_run)
    monkeypatch.setattr(gdro.time, "sleep", lambda sec: None)
    
    result = gdro.run_request({
        "prompt": "hello",
        "request_dir": str(request_dir),
        "max_retries": 2
    }, task_dir=tmp_path)
    
    assert len(calls) == 2
    assert result["ok"] is True
    assert result["text"] == "recovered text"


def test_main_applies_success_cooldown(monkeypatch, tmp_path):
    envelope = {
        "task_id": "T1",
        "operator_id": "mini-gemini-deep-research",
        "prompt": "hello"
    }
    envelope_path = tmp_path / "envelope.json"
    envelope_path.write_text(json.dumps(envelope), encoding="utf-8")
    
    monkeypatch.setenv("SOLAR_OPERATOR_ENVELOPE_JSON", str(envelope_path))
    monkeypatch.setenv("TASK_DIR", str(tmp_path / "task"))
    monkeypatch.setenv("SOLAR_GEMINI_SUCCESS_COOLDOWN_SECONDS", "300")
    
    monkeypatch.setattr(gdro.ofc, "ensure_operator_available", lambda operator_id: None)
    monkeypatch.setattr(gdro, "run_request", lambda request, task_dir: {"ok": True})
    
    cooldown_calls = []
    monkeypatch.setattr(
        gdro.ofc,
        "apply_success_cooldown",
        lambda operator_id, *, success_cooldown_seconds: cooldown_calls.append((operator_id, success_cooldown_seconds)) or {},
    )
    
    assert gdro.main() == 0
    assert cooldown_calls == [("mini-gemini-deep-research", 300)]


def test_main_applies_failure_flow_control(monkeypatch, tmp_path):
    envelope = {
        "task_id": "T2",
        "operator_id": "mini-gemini-deep-research",
        "prompt": "hello"
    }
    envelope_path = tmp_path / "envelope.json"
    envelope_path.write_text(json.dumps(envelope), encoding="utf-8")
    
    monkeypatch.setenv("SOLAR_OPERATOR_ENVELOPE_JSON", str(envelope_path))
    monkeypatch.setenv("TASK_DIR", str(tmp_path / "task"))
    
    monkeypatch.setattr(gdro.ofc, "ensure_operator_available", lambda operator_id: None)
    
    def _boom(request, task_dir):
        raise RuntimeError("Something went wrong")
        
    monkeypatch.setattr(gdro, "run_request", _boom)
    
    failure_calls = []
    monkeypatch.setattr(
        gdro.ofc,
        "apply_failure_flow_control",
        lambda task_dir, *, operator_id, failure_text, rate_limit_cooldown_seconds, auth_cooldown_seconds, defer_on_cooldown, defer_on_auth: failure_calls.append(
            (operator_id, failure_text)
        ) or {"runtime_state": "cooldown"},
    )
    
    assert gdro.main() == 1
    assert len(failure_calls) == 1
    assert failure_calls[0][0] == "mini-gemini-deep-research"
    assert "Something went wrong" in failure_calls[0][1]
