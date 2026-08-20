from __future__ import annotations

from pathlib import Path


def test_handle_passed_checks_graph_parent_before_pass_side_effects() -> None:
    coordinator = (Path(__file__).resolve().parents[2] / 'harness') / "coordinator.sh"
    text = coordinator.read_text(encoding="utf-8")

    guard_call = text.index("ensure_graph_parent_ready_for_pass \"$sid\" \"$sf\"")
    pass_log = text.index("Sprint PASSED!")

    assert "legacy_pass_blocked_by_graph_parent" in text
    assert guard_call < pass_log


def test_handle_passed_refreshes_terminal_coverage_before_export_and_finalization() -> None:
    coordinator = (Path(__file__).resolve().parents[2] / "harness") / "coordinator.sh"
    text = coordinator.read_text(encoding="utf-8")

    function_call = text.index('refresh_terminal_requirement_coverage "$sid"', text.index("handle_passed()"))
    knowledge_closure = text.index('ensure_knowledge_closure_or_block "$sid" "$sf"', function_call)
    finalized_marker = text.index('touch "$finalized"', knowledge_closure)

    assert "--require-pass" in text
    assert function_call < knowledge_closure < finalized_marker
