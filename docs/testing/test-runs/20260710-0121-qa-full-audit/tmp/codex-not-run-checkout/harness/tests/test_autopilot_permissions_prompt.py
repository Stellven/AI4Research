#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "tools" / "solar-autopilot-monitor.py"


def _load_monitor():
    spec = importlib.util.spec_from_file_location("solar_autopilot_monitor", MODULE)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_accept_edits_footer_alone_is_not_permissions_blocker() -> None:
    monitor = _load_monitor()
    tail = """
───────────────────────────────────────
❯\u00a0
───────────────────────────────────────
  ⏵⏵ accept edits on (shift+tab to cycle)
"""
    assert monitor.pane_permissions_prompt_blocked(tail) is False


def test_bypass_permissions_footer_alone_is_not_permissions_blocker() -> None:
    monitor = _load_monitor()
    tail = """
───────────────────────────────────────
❯\u00a0
───────────────────────────────────────
  ⏵⏵ bypass permissions on (shift+tab to cycle)
"""
    assert monitor.pane_permissions_prompt_blocked(tail) is False


def test_real_edit_confirmation_is_permissions_blocker() -> None:
    monitor = _load_monitor()
    tail = """
Do you want to make this edit to graph_node_dispatcher.py?
 ❯ 1. Yes
   2. No

Esc to cancel · Tab to amend
"""
    assert monitor.pane_permissions_prompt_blocked(tail) is True
