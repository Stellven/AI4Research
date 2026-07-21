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


PERMISSIONS_TAIL = """
✢ Warping… (3m 54s · thought for 3s)
  ⎿  Tip: Use /btw to ask a quick side
     question without interrupting
     Claude's current work

────────────────────────────────────────
❯ Press up to edit queued messages
────────────────────────────────────────
  ⏵⏵ bypass permissions on          ·
"""

READY_FOOTER_TAIL = """
⏺ Read(/tmp/example.md)
  ⎿  Read 12 lines

────────────────────────────────────────
❯ Try "edit /tmp/example.md"
────────────────────────────────────────
  ⏵⏵ bypass permissions on (shift+tab to cycle)
"""

STALE_QUEUED_SCROLLBACK_TAIL = """
────────────────────────────────────────
❯ Press up to edit queued messages
────────────────────────────────────────
  ⏵⏵ bypass permissions on

✶ Sprouting… (0s)

────────────────────────────────────────
❯
────────────────────────────────────────
  ⏵⏵ bypass permissions on (shift+tab to cycle)
"""


def main() -> int:
    if not mod.pane_permissions_prompt_blocked(PERMISSIONS_TAIL):
        raise SystemExit("permissions prompt was not detected")
    if mod.pane_permissions_prompt_blocked(READY_FOOTER_TAIL):
        raise SystemExit("ready footer was incorrectly detected as permissions prompt")
    if mod.pane_permissions_prompt_blocked(STALE_QUEUED_SCROLLBACK_TAIL):
        raise SystemExit("stale queued scrollback was incorrectly detected as permissions prompt")

    mod.tmux_capture = lambda target: PERMISSIONS_TAIL
    mod.assigned_graph_node_for_pane = lambda target: {
        "sid": "sprint-demo",
        "node_id": "N2",
        "status": "dispatched",
        "dispatch_file": "/tmp/sprint-demo.N2-dispatch.md",
    } if target == "solar-harness-lab:0.0" else None
    mod.discover_worker_panes = lambda: ["solar-harness-lab:0.0"]

    findings = mod.inspect_panes({"pane": {}, "actions": {}, "target_actions": {}}, stall_seconds=30)
    blocked = [f for f in findings if f.get("type") == "pane_permissions_prompt_blocked"]
    if len(blocked) != 1:
        raise SystemExit(f"expected 1 permissions finding, got {blocked!r}")
    finding = blocked[0]
    if finding.get("sid") != "sprint-demo" or finding.get("target") != "solar-harness-lab:0.0":
        raise SystemExit(f"unexpected permissions finding payload: {finding!r}")

    sent: list[list[str]] = []

    class FakeCompleted:
        returncode = 0

    mod.subprocess.run = lambda cmd, **kwargs: sent.append(cmd) or FakeCompleted()
    mod.no_dispatch_enabled = lambda: False
    mod.pane_gate = lambda target, sid: (True, "ok", {})
    mod.pane_is_busy = lambda target: False
    mod.target_recently_dispatched = lambda state, target, cooldown: False
    mod.should_act = lambda state, finding, cooldown: True
    mod.append_event = lambda *args, **kwargs: None
    mod.mark_action = lambda *args, **kwargs: None

    actions = mod.apply_findings(
        [finding],
        dispatch=True,
        state={"actions": {}, "target_actions": {}},
        cooldown=0,
    )
    if not actions or actions[0].get("dispatched") is not True:
        raise SystemExit(f"permissions unblock action failed: {actions!r}")
    if not any(cmd[:5] == ["tmux", "send-keys", "-t", "solar-harness-lab:0.0", "BTab"] for cmd in sent):
        raise SystemExit(f"expected tmux BTab for permissions dismiss, got {sent!r}")
    if not any(cmd[:5] == ["tmux", "send-keys", "-t", "solar-harness-lab:0.0", "Enter"] for cmd in sent):
        raise SystemExit(f"expected tmux Enter for permissions dismiss, got {sent!r}")

    print('{"ok": true, "feature": "autopilot_permissions_prompt_block"}')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
