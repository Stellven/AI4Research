#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "lib" / "graph_node_dispatcher.py"
spec = importlib.util.spec_from_file_location("graph_node_dispatcher", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules["graph_node_dispatcher"] = mod
spec.loader.exec_module(mod)


def main() -> int:
    tail = """
S03 sprint 全部 10 个节点收官

✻ Churned for 2m 45s

────────────────────────────────────────────────────────────────
❯ finalize sprint
────────────────────────────────────────────────────────────────
  ⏵⏵ bypass permissions on (shift+tab to cycle)
"""
    mod._pane_tail = lambda pane, lines=80: tail
    mod._pane_current_command = lambda pane: "bash"
    mod._pane_health = lambda pane: {}

    assert mod._pane_current_prompt_has_residue(tail)
    assert mod._pane_prompt_residue_is_stale_scrollback("solar-harness:0.3", tail)
    assert mod._pane_unavailable_reason("solar-harness:0.3") == ""
    assert mod._pane_tui_busy("solar-harness:0.3") is False

    distant_marker_tail = """
Evaluator finished prior node review.

✻ Sautéed for 4m 1s

old lines 01
old lines 02
old lines 03
old lines 04
old lines 05
old lines 06
old lines 07
old lines 08
old lines 09
old lines 10
old lines 11
old lines 12
old lines 13
────────────────────────────────────────────────────────────────
❯ 看下 N2 N3 N4 跑完没
────────────────────────────────────────────────────────────────
  ⏵⏵ bypass permissions on (shift+tab to cycle)
"""
    mod._pane_tail = lambda pane, lines=80: distant_marker_tail
    assert mod._pane_current_prompt_has_residue("\n".join(distant_marker_tail.splitlines()[-12:]))
    assert mod._pane_prompt_residue_is_stale_scrollback("solar-harness:0.3", distant_marker_tail)
    assert mod._pane_unavailable_reason("solar-harness:0.3") == ""
    assert mod._pane_tui_busy("solar-harness:0.3") is False

    worked_marker_tail = distant_marker_tail.replace("✻ Sautéed for 4m 1s", "✻ Worked for 4m 27s")
    mod._pane_tail = lambda pane, lines=80: worked_marker_tail
    assert mod._pane_prompt_residue_is_stale_scrollback("solar-harness:0.3", worked_marker_tail)
    assert mod._pane_unavailable_reason("solar-harness:0.3") == ""
    assert mod._pane_tui_busy("solar-harness:0.3") is False

    cooked_marker_tail = distant_marker_tail.replace("✻ Sautéed for 4m 1s", "✻ Cooked for 4m 1s")
    mod._pane_tail = lambda pane, lines=80: cooked_marker_tail
    assert mod._pane_prompt_residue_is_stale_scrollback("solar-harness:0.3", cooked_marker_tail)
    assert mod._pane_unavailable_reason("solar-harness:0.3") == ""
    assert mod._pane_tui_busy("solar-harness:0.3") is False

    live_prompt = """
────────────────────────────────────────────────────────────────
❯ finalize sprint
────────────────────────────────────────────────────────────────
  ⏵⏵ bypass permissions on (shift+tab to cycle)
"""
    mod._pane_tail = lambda pane, lines=80: live_prompt
    assert not mod._pane_prompt_residue_is_stale_scrollback("solar-harness:0.3", live_prompt)
    assert mod._pane_unavailable_reason("solar-harness:0.3") == "unsubmitted_prompt_residue"
    assert mod._pane_tui_busy("solar-harness:0.3") is True

    confirmation_prompt = """
────────────────────────────────────────────────────────────────
 Bash command

   for file in *.json; do jq -r 'paths | join(".")' "$file"; done

 Unhandled node type: string

 Do you want to proceed?
 ❯ 1. Yes
   2. No

 Esc to cancel · Tab to amend · ctrl+e to explain
"""
    mod._pane_tail = lambda pane, lines=80: confirmation_prompt
    assert mod._pane_tui_busy("solar-harness-lab:0.1") is True

    stale_busy_marker_with_empty_prompt = """
  ⎿  ~/.solar/harness/lib/benchmark/schemas.py

· Pondering… (29s · ↓ 430 tokens · thought for 4s)

● How is Claude doing this session? (optional)
  1: Bad    2: Fine   3: Good   0: Dismiss

────────────────────────────────────────────────────────────────
❯
────────────────────────────────────────────────────────────────
  ⏵⏵ bypass permissions on (shift+tab to cycle) · esc to interrupt
"""
    mod._pane_tail = lambda pane, lines=80: stale_busy_marker_with_empty_prompt
    assert mod._pane_tui_busy("solar-harness:0.3") is False

    print("PASS graph dispatcher ignores stale completed prompt scrollback")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
