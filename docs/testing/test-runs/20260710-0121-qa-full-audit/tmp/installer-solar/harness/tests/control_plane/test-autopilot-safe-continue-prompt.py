#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[2] / "tools" / "solar-autopilot-monitor.py"
spec = importlib.util.spec_from_file_location("solar_autopilot_monitor", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules["solar_autopilot_monitor"] = mod
spec.loader.exec_module(mod)


def main() -> int:
    safe = """
────────────────────────
❯ 继续 N5
────────────────────────
"""
    unsafe = """
────────────────────────
❯ rm -rf /tmp/example
────────────────────────
"""
    if not mod.pane_safe_continue_prompt(safe):
        raise SystemExit("safe continue prompt was not detected")
    if mod.pane_safe_continue_prompt(unsafe):
        raise SystemExit("unsafe prompt was treated as safe continue")
    print('{"ok": true, "feature": "autopilot_safe_continue_prompt"}')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
