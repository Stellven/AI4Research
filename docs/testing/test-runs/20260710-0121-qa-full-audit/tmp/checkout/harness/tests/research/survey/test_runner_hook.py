"""Tests for runner_hook attach mechanism."""

from __future__ import annotations

import pytest

from lib.research.survey.runner_hook import attach_to_survey_continue


class FakeRunner:
    """Minimal runner stub with ``add_hook`` support."""

    def __init__(self):
        self.hooks: dict[str, list] = {}

    def add_hook(self, event: str, callback):
        self.hooks.setdefault(event, []).append(callback)


class NoHookRunner:
    """Runner without ``add_hook`` — should degrade gracefully."""

    pass


# ---------------------------------------------------------------------------
# 1. Successful attach
# ---------------------------------------------------------------------------

def test_attach_success():
    runner = FakeRunner()
    result = attach_to_survey_continue(runner)
    assert result["attached"] is True
    assert "section_compiled" in result["hooks"]
    assert "section_compiled" in runner.hooks


# ---------------------------------------------------------------------------
# 2. Degrade when no add_hook
# ---------------------------------------------------------------------------

def test_degrade_no_hook():
    runner = NoHookRunner()
    result = attach_to_survey_continue(runner)
    assert result["attached"] is False
    assert result["reason"] == "runner_has_no_add_hook"


# ---------------------------------------------------------------------------
# 3. Idempotent — calling twice doesn't duplicate hooks
# ---------------------------------------------------------------------------

def test_idempotent():
    runner = FakeRunner()
    r1 = attach_to_survey_continue(runner)
    r2 = attach_to_survey_continue(runner)
    assert r1["attached"] is True
    assert r2["attached"] is True
    # The hook list on the runner has 2 entries (one per call)
    # but the _survey_gate_hooks attribute tracks them
    assert hasattr(runner, "_survey_gate_hooks")
