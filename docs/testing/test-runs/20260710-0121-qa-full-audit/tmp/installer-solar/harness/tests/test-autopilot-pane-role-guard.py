#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "solar-autopilot-monitor.py"
spec = importlib.util.spec_from_file_location("solar_autopilot_monitor", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules["solar_autopilot_monitor"] = mod
spec.loader.exec_module(mod)


def main() -> int:
    titles = {
        "solar-harness:0.0": "PM 产品经理 | 模型:Opus",
        "solar-harness:0.1": "Planner 规划者 | 模型:Opus",
        "solar-harness:0.2": "Builder 主建设者 | 模型:Opus",
        "solar-harness:0.3": "Evaluator 审判官 | 模型:Opus",
        "solar-harness-lab:0.0": "Builder 1 | 模型:GLM",
        "solar-harness-lab:0.1": "Planner 规划者 | 模型:GLM",
    }
    mod.tmux_title = lambda target: titles.get(target, "")

    assert mod.pane_title_matches_role("solar-harness:0.2", "builder")
    assert mod.pane_title_matches_role("solar-harness-lab:0.0", "builder")
    assert not mod.pane_title_matches_role("solar-harness:0.0", "builder")
    assert not mod.pane_title_matches_role("solar-harness-lab:0.1", "builder")
    assert mod.pane_title_matches_role("solar-harness:0.3", "evaluator")
    assert not mod.pane_title_matches_role("solar-harness:0.3", "builder")

    class FakeCompleted:
        returncode = 0
        stdout = "\n".join(f"{target}\t{title}" for target, title in titles.items())

    mod.subprocess.run = lambda *args, **kwargs: FakeCompleted()
    workers = mod.discover_worker_panes()
    assert workers == ["solar-harness:0.2", "solar-harness-lab:0.0"], workers

    sent: list[list[str]] = []
    mod.subprocess.run = lambda cmd, **kwargs: sent.append(cmd) or FakeCompleted()
    mod.no_dispatch_enabled = lambda: False
    mod.pane_gate = lambda target, sid: (True, "ok", {})
    mod.pane_is_busy = lambda target: False
    mod.target_recently_dispatched = lambda state, target, cooldown: False
    mod.should_act = lambda state, finding, cooldown: True
    mod.append_event = lambda *args, **kwargs: None
    mod.mark_action = lambda *args, **kwargs: None

    actions = mod.apply_findings(
        [
            {
                "sid": "sprint-test",
                "type": "pane_safe_continue_prompt",
                "target": "solar-harness:0.0",
                "role": "builder",
            }
        ],
        dispatch=True,
        state={"actions": {}, "target_actions": {}},
        cooldown=0,
    )
    assert actions[0].get("skipped") == "role_mismatch", actions
    assert not sent, sent

    print("PASS autopilot filters pane actions by role title")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
