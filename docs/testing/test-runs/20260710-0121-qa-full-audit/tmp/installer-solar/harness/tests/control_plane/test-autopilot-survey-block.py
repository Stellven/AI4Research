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


SURVEY_TAIL = """
● How is Claude doing this session?
  (optional)
  1: Bad   2: Fine   3: Good  0:
                              Dismiss
"""

STALE_SURVEY_TAIL = """
● How is Claude doing this session?
  (optional)
  1: Bad   2: Fine   3: Good  0:
                              Dismiss
───────────────────────────────────────
❯
───────────────────────────────────────
"""


def main() -> int:
    if not mod.pane_survey_blocked(SURVEY_TAIL):
        raise SystemExit("survey prompt was not detected")
    if mod.pane_survey_blocked(STALE_SURVEY_TAIL):
        raise SystemExit("stale survey scrollback was incorrectly detected as blocking")

    mod.tmux_capture = lambda target: SURVEY_TAIL
    mod.assigned_graph_node_for_pane = lambda target: {
        "sid": "sprint-demo",
        "node_id": "N5",
        "status": "reviewing",
        "dispatch_file": "/tmp/sprint-demo.N5-eval-dispatch-q1.md",
    }
    mod.pane_lease = lambda target: {"sid": "sprint-demo", "dispatch_id": "eval-1", "active": True}
    mod.discover_worker_panes = lambda: []

    findings = mod.inspect_panes({"pane": {}, "actions": {}, "target_actions": {}}, stall_seconds=30)
    survey_findings = [f for f in findings if f.get("type") == "evaluator_survey_blocked"]
    if len(survey_findings) != 1:
        raise SystemExit(f"expected 1 survey finding, got {survey_findings!r}")
    finding = survey_findings[0]
    if finding.get("sid") != "sprint-demo" or finding.get("target") != "solar-harness:0.3":
        raise SystemExit(f"unexpected survey finding payload: {finding!r}")

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
        raise SystemExit(f"survey unblock action failed: {actions!r}")
    if not any(cmd[:4] == ["tmux", "send-keys", "-t", "solar-harness:0.3"] for cmd in sent):
        raise SystemExit(f"expected tmux send-keys for survey dismiss, got {sent!r}")

    print('{"ok": true, "feature": "autopilot_evaluator_survey_block"}')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
