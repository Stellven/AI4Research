#!/usr/bin/env python3
"""Integration smoke for the Webwright adapter verification chain."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ADAPTER = ROOT / "lib" / "webwright_adapter.py"


def _run_json(args: list[str], *, env: dict[str, str] | None = None) -> dict:
    proc = subprocess.run(args, capture_output=True, text=True, env=env, check=True)
    return json.loads(proc.stdout)


def test_webwright_smoke_run_verify_replay(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["BROWSER_AGENT_HEADLESS"] = "true"
    env["WEBWRIGHT_ADAPTER_RUN_MODE"] = "fallback"

    run_dir = tmp_path / "webwright-smoke"
    run_result = _run_json(
        [
            sys.executable,
            str(ADAPTER),
            "run",
            "--task",
            "Test Task",
            "--start-url",
            "https://example.com",
            "--out",
            str(run_dir),
            "--json",
        ],
        env=env,
    )

    assert run_result["ok"] is True
    artifacts = run_result.get("artifacts") or {
        "final_script": run_result["final_script"],
        "trajectory": run_result["trajectory"],
        "report": run_result["report"],
        "screenshots": run_result["screenshots"],
    }
    assert Path(artifacts["final_script"]).exists()
    assert Path(artifacts["trajectory"]).exists()
    assert Path(artifacts["report"]).exists()
    assert artifacts["screenshots"], "expected screenshot evidence"
    mode = run_result.get("mode") or run_result.get("meta", {}).get("mode")
    assert mode in {None, "playwright_fallback"}

    verify_result = _run_json(
        [
            sys.executable,
            str(ADAPTER),
            "verify",
            "--run-dir",
            str(run_dir),
            "--json",
        ],
        env=env,
    )
    assert verify_result["passed"] is True
    assert verify_result["reasons"] == []

    replay_result = _run_json(
        [
            sys.executable,
            str(ADAPTER),
            "replay",
            "--run-dir",
            str(run_dir),
            "--json",
        ],
        env=env,
    )
    assert replay_result["ok"] is True
    assert replay_result["exit_code"] == 0
