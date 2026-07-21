#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import pane_runtime_contract as contract  # noqa: E402


def test_judge_result_artifact_present_success(tmp_path):
    artifact = tmp_path / ".understand-anything" / "knowledge-graph.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text("{}", encoding="utf-8")
    manifest = {
        "runtime_preferences": {"success_artifact": ".understand-anything/knowledge-graph.json"},
        "verification": {"pass_conditions": [{"kind": "artifact_present", "path": ".understand-anything/knowledge-graph.json"}]},
    }
    result = contract.judge_result("actual_backend_used=ThunderOMLX", manifest, tmp_path)
    assert result.status == "SUCCESS"


def test_judge_result_pattern_match_blocked(tmp_path):
    result = contract.judge_result("WAITING_HUMAN blocked for input", {"verification": {"pass_conditions": []}}, tmp_path)
    assert result.status == "BLOCKED"


def test_write_evidence_creates_file(tmp_path):
    target = contract.write_evidence("cap.example", contract.JudgeResult(status="SUCCESS", reasons=["ok"]), tmp_path)
    assert target.exists()


def test_send_command_stdout_fallback_when_no_tmux(monkeypatch):
    monkeypatch.setattr(contract.shutil, "which", lambda _name: None)
    result = contract.send_command("pane-1", "printf ok", timeout_s=5)
    assert result.ok is True
    assert result.dispatch_mode == "stdout_fallback"
    assert result.output == "ok"
