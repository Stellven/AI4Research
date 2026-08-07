"""Activation proof for dispatch gate hint fail-open behavior."""

from __future__ import annotations

import json

from lib.orchestration.dispatch_gate_hint import inject_gate_hint


def test_inject_gate_hint_is_importable_callable_and_visible() -> None:
    result = inject_gate_hint(json.dumps({"dispatch_id": "d1"}), "sprint-s05")
    data = json.loads(result)
    assert data["gate_hints"][0]["source"] == "dispatch_gate_hint"
    assert data["gate_hints"][0]["sprint_id"] == "sprint-s05"
    assert data["gate_hints"][0]["views_registered"] == 5


def test_inject_gate_hint_fail_open_on_invalid_context() -> None:
    bad_context = "not-json"
    assert inject_gate_hint(bad_context, "sprint-s05") == bad_context

