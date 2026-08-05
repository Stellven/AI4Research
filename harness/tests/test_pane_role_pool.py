from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from pane_hygiene_registry import PaneHygieneRegistry, PaneState
from pane_role_pool import discover_role_pool, ensure_clean_for_dispatch


def test_discover_role_pool_planner_prefers_planner_then_architect_then_builder(monkeypatch) -> None:
    monkeypatch.setattr(
        "pane_role_pool.list_tmux_panes",
        lambda: [
            {"pane": "solar-harness-lab:0.0", "title": "Builder 1 | 模型:GLM-5.1"},
            {"pane": "solar-harness:0.3", "title": "Evaluator 审判官 | 模型:Opus"},
            {"pane": "solar-harness:0.1", "title": "Planner 规划者 | 模型:Opus"},
            {"pane": "solar-harness-lab:0.4", "title": "Architect 架构师 | 模型:Sonnet"},
        ],
    )
    panes = [item["pane"] for item in discover_role_pool("planner")]
    assert panes[:3] == ["solar-harness:0.1", "solar-harness-lab:0.4", "solar-harness-lab:0.0"]


def test_strict_role_pool_never_spills_planner_or_evaluator_into_builder(monkeypatch) -> None:
    monkeypatch.setattr(
        "pane_role_pool.list_tmux_panes",
        lambda: [
            {"pane": "solar-harness:0.1", "title": "Planner 规划者 | 模型:Codex"},
            {"pane": "solar-harness:0.2", "title": "Builder 建设者 | 模型:Codex"},
            {"pane": "solar-harness:0.3", "title": "Evaluator 审判官 | 模型:Codex"},
            {"pane": "solar-harness-lab:0.0", "title": "Builder | 模型:Codex"},
        ],
    )

    planner_panes = [
        item["pane"]
        for item in discover_role_pool("planner", strict_role_boundary=True)
    ]
    evaluator_panes = [
        item["pane"]
        for item in discover_role_pool("evaluator", strict_role_boundary=True)
    ]

    assert planner_panes == ["solar-harness:0.1"]
    assert evaluator_panes == ["solar-harness:0.3"]


def test_discover_role_pool_scopes_custom_harness_session(monkeypatch) -> None:
    monkeypatch.setenv("SOLAR_HARNESS_SESSION", "solar-codex-cockpit-clean")
    monkeypatch.setattr(
        "pane_role_pool.list_tmux_panes",
        lambda: [
            {"pane": "solar-codex-cockpit-clean:0.2", "title": "Builder | 模型:Codex"},
            {"pane": "solar-codex-cockpit-clean-lab:0.0", "title": "Builder | 模型:Codex"},
            {"pane": "solar-codex-cockpit-old:0.2", "title": "Builder | 模型:Codex"},
            {"pane": "solar-harness-lab:0.0", "title": "Builder | 模型:Opus"},
        ],
    )

    panes = [item["pane"] for item in discover_role_pool("builder")]

    assert panes == [
        "solar-codex-cockpit-clean-lab:0.0",
        "solar-codex-cockpit-clean:0.2",
    ]


def test_ensure_clean_for_dispatch_registers_and_clears_ready_footer(tmp_path) -> None:
    registry_path = tmp_path / "pane-hygiene.json"
    reg = PaneHygieneRegistry(str(registry_path))
    reg.register_pane("solar-harness-lab:0.0", "builder", initial_state=PaneState.clean)

    footer = """
────────────────────────────────────────
❯ Try "edit /tmp/example.md"
────────────────────────────────────────
  ⏵⏵ bypass permissions on (shift+tab to cycle)
"""

    monkeypatch_capture = lambda pane: footer

    import pane_role_pool as mod
    import pane_clear_manager as pcm

    original_detector = mod.RecoverDetector
    original_send = pcm._tmux_send_keys
    try:
        mod.RecoverDetector = lambda: original_detector(capture_fn=monkeypatch_capture)
        pcm._tmux_send_keys = lambda pane, keys, tmux_binary="tmux": None
        result = ensure_clean_for_dispatch(
            "solar-harness-lab:0.0",
            "builder",
            registry_path=registry_path,
        )
    finally:
        mod.RecoverDetector = original_detector
        pcm._tmux_send_keys = original_send

    assert result["ok"] is True
    assert result["final_state"] == "clean"
