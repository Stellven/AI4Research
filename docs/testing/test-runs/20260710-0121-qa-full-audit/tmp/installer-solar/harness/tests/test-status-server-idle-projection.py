#!/usr/bin/env python3
"""Regression tests for status-server idle/no-active projection."""

import importlib.util
from pathlib import Path


MODULE = Path(__file__).resolve().parents[1] / "lib" / "symphony" / "status-server.py"
spec = importlib.util.spec_from_file_location("status_server", MODULE)
status_server = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(status_server)


def test_runtime_from_tail_prefers_current_idle_prompt_over_old_bash_history():
    tail = """
⏺ Bash(echo old command)
  ⎿ done

────────────────────────────────────────────────────────────────
❯
────────────────────────────────────────────────────────────────
  ⏵⏵ bypass permissions on (shift+tab to cycle)
"""
    assert status_server._runtime_from_tail(tail) == "idle"


def test_runtime_from_tail_detects_prompt_residue():
    tail = """
────────────────────────────────────────────────────────────────
❯ commit this
  continued editable input
────────────────────────────────────────────────────────────────
  ⏵⏵ bypass permissions on (shift+tab to cycle)
"""
    assert status_server._runtime_from_tail(tail) == "prompt_residue"


def test_runtime_from_tail_ignores_historical_prompt_before_divider():
    tail = """
❯ commit this
────────────────────────────────────────────────────────────────
  ⏵⏵ bypass permissions on (shift+tab to cycle)
"""
    assert status_server._runtime_from_tail(tail) == "idle"
