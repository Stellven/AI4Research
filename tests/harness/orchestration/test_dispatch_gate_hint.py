"""Tests for dispatch_gate_hint.inject_gate_hint()."""

from __future__ import annotations

import json

from lib.orchestration.dispatch_gate_hint import inject_gate_hint


class TestInjectGateHint:
    def test_injects_hint_into_valid_context(self):
        ctx = json.dumps({"dispatch_id": "abc123"})
        result = inject_gate_hint(ctx, "sprint-001")
        data = json.loads(result)
        assert "gate_hints" in data
        assert len(data["gate_hints"]) == 1
        assert data["gate_hints"][0]["sprint_id"] == "sprint-001"
        assert data["gate_hints"][0]["source"] == "dispatch_gate_hint"
        assert data["gate_hints"][0]["status"] == "gate_ready"

    def test_fail_open_on_invalid_json(self):
        bad_ctx = "not-json{at-all"
        result = inject_gate_hint(bad_ctx, "sprint-002")
        assert result == bad_ctx  # returned unchanged

    def test_fail_open_on_empty_string(self):
        result = inject_gate_hint("", "sprint-003")
        assert result == ""

    def test_no_duplicate_injection(self):
        ctx = json.dumps({"dispatch_id": "xyz"})
        first = inject_gate_hint(ctx, "sprint-004")
        second = inject_gate_hint(first, "sprint-004")
        data = json.loads(second)
        assert len(data["gate_hints"]) == 1  # not duplicated

    def test_preserves_existing_gate_hints(self):
        ctx = json.dumps({
            "gate_hints": [{"source": "other", "sprint_id": "other-sid"}],
        })
        result = inject_gate_hint(ctx, "sprint-005")
        data = json.loads(result)
        assert len(data["gate_hints"]) == 2
        assert data["gate_hints"][0]["source"] == "other"

    def test_multiple_different_sprints(self):
        ctx = json.dumps({})
        first = inject_gate_hint(ctx, "sprint-A")
        second = inject_gate_hint(first, "sprint-B")
        data = json.loads(second)
        assert len(data["gate_hints"]) == 2

    def test_views_registered_count(self):
        ctx = json.dumps({})
        result = inject_gate_hint(ctx, "sprint-006")
        data = json.loads(result)
        assert data["gate_hints"][0]["views_registered"] == 5
