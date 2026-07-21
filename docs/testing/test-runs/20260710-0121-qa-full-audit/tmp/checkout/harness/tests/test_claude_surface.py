"""Tests for claude_surface — surface classifier and reserve routing policy."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import claude_surface as cs  # noqa: E402


# ── Fixtures ─────────────────────────────────────────────────────────────────

def _make_interactive(model: str = "opus") -> dict:
    return {
        "operator_id": f"mini-claude-{model}-planner",
        "backend": "claude-cli",
        "model": model,
        "launch_cmd_kind": "interactive_repl",
        "billing_surface": "subscription_interactive",
        "billing_pool": "anthropic_subscription_interactive",
        "surface": {
            "type": "claude_code_interactive",
            "tool": "claude",
            "launch_cmd": f"claude --dangerously-skip-permissions --model {model}",
        },
    }


def _make_print(model: str = "opus") -> dict:
    return {
        "operator_id": f"mini-claude-{model}-planner-print",
        "backend": "claude-cli",
        "model": model,
        "launch_cmd_kind": "print_once",
        "billing_surface": "anthropic_agent_sdk_credit",
        "billing_pool": "anthropic_agent_sdk_credit",
        "surface": {
            "type": "claude_print",
            "tool": "claude",
            "launch_cmd": f"claude --print --model {model}",
        },
        "quota": {
            "quota_type": "monthly-agent-credit",
            "reserve_for": ["ARCH_DECISION", "ROOT_CAUSE_DEBUG", "FINAL_REVIEW"],
            "on_exhausted": "disable_and_fallback",
        },
    }


def _make_print_no_reserve(model: str = "sonnet") -> dict:
    """claude_print operator with no reserve_for list."""
    op = _make_print(model)
    del op["quota"]["reserve_for"]
    return op


def _make_ambiguous() -> dict:
    """Operator with no surface hints at all."""
    return {
        "operator_id": "mini-unknown",
        "backend": "claude-cli",
        "model": "sonnet",
    }


# ── classify_surface ──────────────────────────────────────────────────────────

class TestClassifySurface:
    def test_explicit_surface_type_print(self):
        assert cs.classify_surface(_make_print()) == cs.CLAUDE_PRINT

    def test_explicit_surface_type_interactive(self):
        assert cs.classify_surface(_make_interactive()) == cs.CLAUDE_INTERACTIVE

    def test_launch_cmd_kind_print_once(self):
        op = {"launch_cmd_kind": "print_once", "backend": "claude-cli"}
        assert cs.classify_surface(op) == cs.CLAUDE_PRINT

    def test_launch_cmd_kind_interactive_repl(self):
        op = {"launch_cmd_kind": "interactive_repl", "backend": "claude-cli"}
        assert cs.classify_surface(op) == cs.CLAUDE_INTERACTIVE

    def test_billing_surface_agent_sdk_credit(self):
        op = {"billing_surface": "anthropic_agent_sdk_credit", "backend": "claude-cli"}
        assert cs.classify_surface(op) == cs.CLAUDE_PRINT

    def test_billing_surface_subscription_interactive(self):
        op = {"billing_surface": "subscription_interactive", "backend": "claude-cli"}
        assert cs.classify_surface(op) == cs.CLAUDE_INTERACTIVE

    def test_launch_cmd_with_double_dash_print(self):
        op = {"surface": {"launch_cmd": "claude --print --model sonnet"}}
        assert cs.classify_surface(op) == cs.CLAUDE_PRINT

    def test_launch_cmd_with_dash_p(self):
        op = {"surface": {"launch_cmd": "claude -p --model sonnet"}}
        assert cs.classify_surface(op) == cs.CLAUDE_PRINT

    def test_launch_cmd_interactive_no_print_flag(self):
        op = {"surface": {"launch_cmd": "claude --dangerously-skip-permissions --model opus"}}
        # No print flag → falls through to SURFACE_UNKNOWN (no other hints)
        assert cs.classify_surface(op) == cs.SURFACE_UNKNOWN

    def test_unknown_operator(self):
        assert cs.classify_surface(_make_ambiguous()) == cs.SURFACE_UNKNOWN

    def test_surface_type_takes_precedence_over_billing(self):
        """surface.type wins even if billing_surface says something different."""
        op = {
            "surface": {"type": cs.CLAUDE_INTERACTIVE},
            "billing_surface": "anthropic_agent_sdk_credit",
        }
        assert cs.classify_surface(op) == cs.CLAUDE_INTERACTIVE


# ── Boolean helpers ───────────────────────────────────────────────────────────

class TestBooleanHelpers:
    def test_is_claude_print_true(self):
        assert cs.is_claude_print(_make_print()) is True

    def test_is_claude_print_false_for_interactive(self):
        assert cs.is_claude_print(_make_interactive()) is False

    def test_is_claude_interactive_true(self):
        assert cs.is_claude_interactive(_make_interactive()) is True

    def test_is_claude_interactive_false_for_print(self):
        assert cs.is_claude_interactive(_make_print()) is False

    def test_is_claude_print_false_for_unknown(self):
        assert cs.is_claude_print(_make_ambiguous()) is False

    def test_is_claude_interactive_false_for_unknown(self):
        assert cs.is_claude_interactive(_make_ambiguous()) is False


# ── claude_print_reserve_allows ───────────────────────────────────────────────

class TestReservePolicy:
    def test_non_print_always_allowed(self):
        op = _make_interactive()
        assert cs.claude_print_reserve_allows(op, "FANOUT") is True
        assert cs.claude_print_reserve_allows(op, "bulk-extraction") is True
        assert cs.claude_print_reserve_allows(op, "FINAL_REVIEW") is True

    def test_print_with_reserve_for_allows_reserved_task(self):
        op = _make_print()
        assert cs.claude_print_reserve_allows(op, "FINAL_REVIEW") is True
        assert cs.claude_print_reserve_allows(op, "ROOT_CAUSE_DEBUG") is True
        assert cs.claude_print_reserve_allows(op, "ARCH_DECISION") is True

    def test_print_with_reserve_for_blocks_non_reserved(self):
        op = _make_print()
        assert cs.claude_print_reserve_allows(op, "implementation") is False
        assert cs.claude_print_reserve_allows(op, "debugging") is False
        assert cs.claude_print_reserve_allows(op, "FANOUT") is False

    def test_print_with_reserve_for_blocks_bulk(self):
        op = _make_print()
        assert cs.claude_print_reserve_allows(op, "BULK_EDIT") is False
        assert cs.claude_print_reserve_allows(op, "TEST_RUN") is False
        assert cs.claude_print_reserve_allows(op, "LOW_VALUE_SCAN") is False

    def test_print_no_reserve_blocks_fanout(self):
        op = _make_print_no_reserve()
        assert cs.claude_print_reserve_allows(op, "FANOUT") is False
        assert cs.claude_print_reserve_allows(op, "fanout") is False

    def test_print_no_reserve_blocks_bulk_edit(self):
        op = _make_print_no_reserve()
        assert cs.claude_print_reserve_allows(op, "BULK_EDIT") is False
        assert cs.claude_print_reserve_allows(op, "bulk-edit") is False

    def test_print_no_reserve_blocks_test_run(self):
        op = _make_print_no_reserve()
        assert cs.claude_print_reserve_allows(op, "TEST_RUN") is False

    def test_print_no_reserve_blocks_low_value_scan(self):
        op = _make_print_no_reserve()
        assert cs.claude_print_reserve_allows(op, "LOW_VALUE_SCAN") is False
        assert cs.claude_print_reserve_allows(op, "low-value-scan") is False

    def test_print_no_reserve_allows_high_value_task(self):
        op = _make_print_no_reserve()
        # Not a bulk/fanout task — allowed under the heuristic
        assert cs.claude_print_reserve_allows(op, "FINAL_REVIEW") is True
        assert cs.claude_print_reserve_allows(op, "ROOT_CAUSE_DEBUG") is True

    def test_empty_task_type_always_allowed(self):
        op = _make_print()
        assert cs.claude_print_reserve_allows(op, "") is True
        assert cs.claude_print_reserve_allows(op, None) is True  # type: ignore[arg-type]

    def test_reserve_check_case_insensitive(self):
        op = _make_print()
        assert cs.claude_print_reserve_allows(op, "final_review") is True
        assert cs.claude_print_reserve_allows(op, "Final_Review") is True

    def test_unknown_operator_always_allowed(self):
        op = _make_ambiguous()
        assert cs.claude_print_reserve_allows(op, "FANOUT") is True
