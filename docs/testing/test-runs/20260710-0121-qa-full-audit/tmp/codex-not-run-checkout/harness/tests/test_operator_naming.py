"""Tests for tools/operator_naming.py.

Covers:
  - canonical_operator_id for Claude/Codex/Antigravity/local operators
  - pane_title for all vendor families
  - apply_pane_title is a safe no-op outside tmux
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest import mock

import pytest

# Allow import from tools/ regardless of working directory
TOOLS_DIR = Path(__file__).parent.parent / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from operator_naming import apply_pane_title, canonical_operator_id, pane_title


# ---------------------------------------------------------------------------
# Fixtures — operator config dicts mirroring physical-operators.json entries
# ---------------------------------------------------------------------------

CLAUDE_BUILDER = {
    "backend": "claude-cli",
    "provider": "anthropic",
    "vendor": "Anthropic",
    "role": "builder",
    "model": "sonnet",
}

CLAUDE_EVALUATOR = {
    "backend": "claude-cli",
    "provider": "anthropic",
    "vendor": "Anthropic",
    "role": "evaluator",
    "model": "opus",
}

CODEX_BUILDER = {
    "backend": "openai-api",
    "provider": "openai",
    "vendor": "OpenAI",
    "role": "builder",
    "model": "gpt-4o",
}

ANTIGRAVITY_FLASH = {
    "backend": "agy-cli",
    "provider": "google",
    "vendor": "Google",
    "role": "builder",
    "model": "gemini-3.5-flash-high",
}

ANTIGRAVITY_PRO = {
    "backend": "agy-cli",
    "provider": "google",
    "vendor": "Google",
    "role": "planner",
    "model": "gemini-3.1-pro",
}

LOCAL_THUNDEROMLX = {
    "backend": "command",
    "provider": "local",
    "vendor": "ThunderOMLX",
    "role": "builder",
    "model": "thunderomlx",
}

LOCAL_GLM = {
    "backend": "command",
    "provider": "glm",
    "vendor": "ZhipuAI",
    "role": "builder",
    "model": "glm-5.1",
}

LOCAL_RIPGREP = {
    "backend": "local",
    "provider": "local",
    "vendor": "Solar",
    "role": "builder",
    "model": "ripgrep",
}


# ---------------------------------------------------------------------------
# canonical_operator_id
# ---------------------------------------------------------------------------


class TestCanonicalOperatorId:
    def test_claude_builder(self):
        result = canonical_operator_id("mini-claude-sonnet-builder", CLAUDE_BUILDER)
        assert result == "claude/builder/claude-sonnet-builder"

    def test_claude_evaluator(self):
        result = canonical_operator_id("mini-claude-opus-evaluator", CLAUDE_EVALUATOR)
        assert result == "claude/evaluator/claude-opus-evaluator"

    def test_antigravity_flash(self):
        result = canonical_operator_id("mini-antigravity-gemini35-flash-high", ANTIGRAVITY_FLASH)
        assert result == "antigravity/builder/antigravity-gemini35-flash-high"

    def test_antigravity_pro_planner(self):
        result = canonical_operator_id("mini-antigravity-gemini31-pro", ANTIGRAVITY_PRO)
        assert result == "antigravity/planner/antigravity-gemini31-pro"

    def test_local_thunderomlx(self):
        result = canonical_operator_id("mini-thunderomlx-qwen36-knowledge", LOCAL_THUNDEROMLX)
        assert result == "local/builder/thunderomlx-qwen36-knowledge"

    def test_local_glm(self):
        result = canonical_operator_id("mini-glm51-knowledge", LOCAL_GLM)
        assert result == "local/builder/glm51-knowledge"

    def test_local_ripgrep(self):
        result = canonical_operator_id("mini-local-scan", LOCAL_RIPGREP)
        assert result == "local/builder/local-scan"

    def test_codex_builder(self):
        result = canonical_operator_id("mini-codex-gpt4o-builder", CODEX_BUILDER)
        assert result == "codex/builder/codex-gpt4o-builder"

    def test_no_mini_prefix_preserved(self):
        result = canonical_operator_id("custom-claude-builder", CLAUDE_BUILDER)
        # No "mini-" prefix to strip
        assert result == "claude/builder/custom-claude-builder"

    def test_empty_config_defaults(self):
        result = canonical_operator_id("mini-unknown-op", {})
        # vendor falls back to "local", role falls back to "builder"
        assert result == "local/builder/unknown-op"


# ---------------------------------------------------------------------------
# pane_title
# ---------------------------------------------------------------------------


class TestPaneTitle:
    def test_claude_builder(self):
        title = pane_title("mini-claude-sonnet-builder", "builder", config=CLAUDE_BUILDER)
        assert "[Claude]" in title
        assert "Builder" in title
        assert "sonnet" in title

    def test_claude_evaluator(self):
        title = pane_title("mini-claude-opus-evaluator", "evaluator", config=CLAUDE_EVALUATOR)
        assert "[Claude]" in title
        assert "Evaluator" in title
        assert "opus" in title

    def test_codex_builder(self):
        title = pane_title("mini-codex-gpt4o-builder", "builder", config=CODEX_BUILDER)
        assert "[Codex]" in title
        assert "Builder" in title
        assert "gpt-4o" in title

    def test_antigravity_flash(self):
        title = pane_title("mini-antigravity-gemini35-flash-high", "builder", config=ANTIGRAVITY_FLASH)
        assert "[Antigravity]" in title
        assert "Builder" in title
        assert "gemini-3.5-flash-high" in title

    def test_antigravity_pro_planner(self):
        title = pane_title("mini-antigravity-gemini31-pro", "planner", config=ANTIGRAVITY_PRO)
        assert "[Antigravity]" in title
        assert "Planner" in title

    def test_local_thunderomlx(self):
        title = pane_title("mini-thunderomlx-qwen36-knowledge", "builder", config=LOCAL_THUNDEROMLX)
        assert "[Local]" in title
        assert "Builder" in title
        assert "thunderomlx" in title

    def test_local_glm(self):
        title = pane_title("mini-glm51-knowledge", "builder", config=LOCAL_GLM)
        assert "[Local]" in title

    def test_local_ripgrep(self):
        title = pane_title("mini-local-scan", "builder", config=LOCAL_RIPGREP)
        assert "[Local]" in title

    def test_explicit_vendor_override(self):
        title = pane_title("op", "builder", vendor="antigravity")
        assert "[Antigravity]" in title

    def test_explicit_model_override(self):
        title = pane_title("op", "builder", model="custom-model-v1", config={})
        assert "custom-model-v1" in title

    def test_no_model_omits_separator(self):
        title = pane_title("op", "builder", config={})
        # No model → no " | " separator
        assert " | " not in title


# ---------------------------------------------------------------------------
# apply_pane_title — outside-tmux safety
# ---------------------------------------------------------------------------


class TestApplyPaneTitle:
    def test_noop_outside_tmux(self):
        """apply_pane_title must not call subprocess when TMUX is unset."""
        env_without_tmux = {k: v for k, v in os.environ.items() if k != "TMUX"}
        with mock.patch.dict(os.environ, env_without_tmux, clear=True):
            with mock.patch("subprocess.run") as mock_run:
                apply_pane_title("Test Title")
                mock_run.assert_not_called()

    def test_noop_when_tmux_empty(self):
        with mock.patch.dict(os.environ, {"TMUX": ""}, clear=False):
            env = dict(os.environ)
            env["TMUX"] = ""
            with mock.patch.dict(os.environ, {"TMUX": ""}, clear=False):
                # Temporarily remove TMUX to simulate empty
                with mock.patch("subprocess.run") as mock_run:
                    # TMUX="" is falsy so apply_pane_title should no-op
                    with mock.patch.dict(os.environ, {}, clear=False):
                        # Remove TMUX key entirely for this sub-test
                        saved = os.environ.pop("TMUX", None)
                        try:
                            apply_pane_title("Test Title")
                            mock_run.assert_not_called()
                        finally:
                            if saved is not None:
                                os.environ["TMUX"] = saved

    def test_calls_tmux_when_inside(self):
        """apply_pane_title must call tmux select-pane when TMUX is set."""
        with mock.patch.dict(os.environ, {"TMUX": "/tmp/tmux-1000/default,12345,0"}, clear=False):
            with mock.patch("subprocess.run") as mock_run:
                apply_pane_title("My Title")
                mock_run.assert_called_once()
                call_args = mock_run.call_args[0][0]
                assert "tmux" in call_args
                assert "select-pane" in call_args
                assert "-T" in call_args
                assert "My Title" in call_args

    def test_explicit_pane_id(self):
        """When pane_id is provided it should appear in the tmux call."""
        with mock.patch.dict(os.environ, {"TMUX": "/tmp/tmux-1000/default,12345,0"}, clear=False):
            with mock.patch("subprocess.run") as mock_run:
                apply_pane_title("Title", pane_id="%3")
                call_args = mock_run.call_args[0][0]
                assert "-t" in call_args
                assert "%3" in call_args

    def test_tmux_not_found_is_noop(self):
        """FileNotFoundError from missing tmux binary must not propagate."""
        with mock.patch.dict(os.environ, {"TMUX": "/tmp/tmux-1000/default,12345,0"}, clear=False):
            with mock.patch("subprocess.run", side_effect=FileNotFoundError):
                # Must not raise
                apply_pane_title("Title")

    def test_tmux_error_is_noop(self):
        """Any subprocess exception must be swallowed."""
        with mock.patch.dict(os.environ, {"TMUX": "/tmp/tmux-1000/default,12345,0"}, clear=False):
            with mock.patch("subprocess.run", side_effect=RuntimeError("tmux died")):
                apply_pane_title("Title")  # Must not raise
