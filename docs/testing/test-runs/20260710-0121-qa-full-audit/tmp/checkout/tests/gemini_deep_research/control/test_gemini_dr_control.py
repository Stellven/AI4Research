import json
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "harness" / "tools"))

import gemini_deep_research_operator as gdro

def test_control_retry_limit_exceeded(monkeypatch, tmp_path):
    class FailResult:
        returncode = 1
        stdout = ""
        stderr = "API Failure"

    monkeypatch.setattr(gdro, "_wrapper_cmd", lambda: ["fake-wrapper"])
    monkeypatch.setattr(gdro.subprocess, "run", lambda *args, **kwargs: FailResult())
    monkeypatch.setattr(gdro.time, "sleep", lambda sec: None)
    
    request_dir = tmp_path / "gemini-deep-research-request"
    request_dir.mkdir(parents=True, exist_ok=True)
    
    with pytest.raises(RuntimeError) as exc_info:
        gdro.run_request({
            "prompt": "Control Prompt",
            "request_dir": str(request_dir),
            "max_retries": 2
        }, task_dir=tmp_path)
    
    assert "failed after 2 attempts" in str(exc_info.value)
