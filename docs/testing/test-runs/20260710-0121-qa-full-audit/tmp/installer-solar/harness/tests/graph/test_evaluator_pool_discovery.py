from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "lib"))

import graph_node_dispatcher as gnd  # noqa: E402


def test_discover_evaluators_includes_lab_evaluator_lane(monkeypatch) -> None:
    pane_rows = "\n".join(
        [
            "solar-harness:0.3\tEvaluator 审判官 | 模型:Opus",
            "solar-harness-lab:0.1\tEvaluator 2 审判官 | 模型:GLM",
            "solar-harness-lab:0.2\tPlanner 规划者 | 模型:GLM",
            "solar-harness-lab:0.0\tBuilder 1 | 模型:GLM",
            "solar-harness-lab:0.3\tBuilder 4 | 模型:Sonnet",
        ]
    ).encode()

    monkeypatch.setattr(gnd, "_pane_exists", lambda pane: True)
    monkeypatch.setattr(gnd, "_pane_runtime_unavailable_reason", lambda pane, title: "")
    monkeypatch.setattr(gnd, "_pane_unavailable_reason", lambda pane: "")
    monkeypatch.setattr(gnd, "_pane_has_active_lease", lambda pane: False)
    monkeypatch.setattr(gnd, "_pane_tui_busy", lambda pane: False)
    monkeypatch.setattr(gnd, "_models_for_pane", lambda pane, title="": ["opus"] if pane == "solar-harness:0.3" else ["claude-sonnet"])
    monkeypatch.setattr(
        gnd,
        "_pane_title",
        lambda pane: {
            "solar-harness:0.3": "Evaluator 审判官 | 模型:Opus",
            "solar-harness-lab:0.1": "Evaluator 2 审判官 | 模型:GLM",
            "solar-harness-lab:0.2": "Planner 规划者 | 模型:GLM",
            "solar-harness-lab:0.0": "Builder 1 | 模型:GLM",
            "solar-harness-lab:0.3": "Builder 4 | 模型:Sonnet",
        }.get(pane, ""),
    )
    monkeypatch.setattr(
        gnd.subprocess,
        "check_output",
        lambda *args, **kwargs: pane_rows,
    )

    evaluators = gnd._discover_evaluators(dry_run=False)
    panes = [item["pane"] for item in evaluators]

    assert "solar-harness:0.3" in panes
    assert "solar-harness-lab:0.1" in panes
    assert "solar-harness-lab:0.0" in panes
    assert "solar-harness-lab:0.3" in panes
    assert "solar-harness-lab:0.2" not in panes
