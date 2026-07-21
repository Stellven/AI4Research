#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import gemini_enhanced_search_task_operator as gop  # noqa: E402


def test_build_request_reads_prompt_from_file(tmp_path):
    prompt_file = tmp_path / "prompt.txt"
    prompt_file.write_text("hello world", encoding="utf-8")
    payload = gop.build_request({"prompt_file": str(prompt_file)}, task_dir=tmp_path)
    assert payload["prompt"] == "hello world"
    assert payload["output_dir"] == str(tmp_path.resolve())


def test_run_request_writes_result(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(
        gop.ges,
        "run_pipeline",
        lambda *args, **kwargs: {
            "ok": True,
            "gem_name": "李教授提示词大师",
            "rewritten_prompt": "rewrite",
            "analysis_markdown": "## Analysis",
            "citations": [{"title": "A", "url": "https://a.test"}],
        },
    )
    result = gop.run_request({"prompt": "hello"}, task_dir=tmp_path)
    assert result["ok"] is True
    assert (tmp_path / "gemini-enhanced-search-request.json").exists()
    assert (tmp_path / "gemini-enhanced-search-result.json").exists()
    assert "Gemini Enhanced Search Result" in capsys.readouterr().out


def test_main_applies_success_cooldown(monkeypatch, tmp_path):
    envelope = {
        "task_id": "T1",
        "operator_id": "mini-gemini-enhanced-search",
        "prompt": "hello",
    }
    envelope_path = tmp_path / "envelope.json"
    envelope_path.write_text(json.dumps(envelope), encoding="utf-8")
    monkeypatch.setenv("SOLAR_OPERATOR_ENVELOPE_JSON", str(envelope_path))
    monkeypatch.setenv("TASK_DIR", str(tmp_path / "task"))
    monkeypatch.setenv("SOLAR_GEMINI_SUCCESS_COOLDOWN_SECONDS", "111")
    monkeypatch.setattr(gop.ofc, "ensure_operator_available", lambda operator_id: None)
    monkeypatch.setattr(gop, "run_request", lambda request, task_dir: {"ok": True})
    calls: list[tuple[str, int]] = []
    monkeypatch.setattr(
        gop.ofc,
        "apply_success_cooldown",
        lambda operator_id, *, success_cooldown_seconds: calls.append((operator_id, success_cooldown_seconds)) or {},
    )
    assert gop.main() == 0
    assert calls == [("mini-gemini-enhanced-search", 111)]


def test_main_applies_failure_flow_control(monkeypatch, tmp_path):
    envelope = {
        "task_id": "T2",
        "operator_id": "mini-gemini-enhanced-search",
        "prompt": "hello",
    }
    envelope_path = tmp_path / "envelope.json"
    envelope_path.write_text(json.dumps(envelope), encoding="utf-8")
    monkeypatch.setenv("SOLAR_OPERATOR_ENVELOPE_JSON", str(envelope_path))
    monkeypatch.setenv("TASK_DIR", str(tmp_path / "task"))
    monkeypatch.setattr(gop.ofc, "ensure_operator_available", lambda operator_id: None)

    def _boom(request, task_dir):
        raise RuntimeError("RESOURCE_EXHAUSTED: retry later")

    monkeypatch.setattr(gop, "run_request", _boom)
    calls: list[tuple[str, int, int, bool, bool]] = []
    monkeypatch.setattr(
        gop.ofc,
        "apply_failure_flow_control",
        lambda task_dir, *, operator_id, failure_text, rate_limit_cooldown_seconds, auth_cooldown_seconds, defer_on_cooldown, defer_on_auth: calls.append(
            (operator_id, rate_limit_cooldown_seconds, auth_cooldown_seconds, defer_on_cooldown, defer_on_auth)
        ) or {"runtime_state": "cooldown"},
    )
    assert gop.main() == 1
    assert calls == [("mini-gemini-enhanced-search", 3600, 21600, True, True)]
