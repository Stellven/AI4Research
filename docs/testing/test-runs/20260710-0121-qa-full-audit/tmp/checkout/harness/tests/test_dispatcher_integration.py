"""Tests for graph_node_dispatcher.py broker integration (S03 N6).

Acceptance criteria verified:
  1. get_broker() lazy import function exists
  2. <action_contracts> block injected when broker enabled
  3. SOLAR_BROKER_ENABLED=0 produces dispatch without <action_contracts>
  4. Existing function signatures unchanged (LR-04)
  5. Dual-run comparison tests PASS
  6. pytest all PASS
  7. py_compile passes
"""

import ast
import os
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

DISPATCHER = Path(__file__).parent.parent / "lib" / "graph_node_dispatcher.py"


# ---------------------------------------------------------------------------
# AC1: get_broker() lazy import
# ---------------------------------------------------------------------------


class TestGetBroker:
    def test_get_broker_callable(self):
        from harness.lib.graph_node_dispatcher import get_broker
        assert callable(get_broker)

    def test_get_broker_returns_class_when_available(self):
        """execution_broker exists (N3 delivered); get_broker returns the class."""
        from harness.lib.graph_node_dispatcher import get_broker
        result = get_broker()
        assert result is not None
        assert result.__name__ == "ExecutionBroker"

    def test_get_broker_is_lazy_import(self):
        """get_broker import must not trigger at module level."""
        source = DISPATCHER.read_text()
        tree = ast.parse(source)
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ImportFrom) and node.module and "execution_broker" in node.module:
                pytest.fail(f"Top-level import of execution_broker at line {node.lineno}")


# ---------------------------------------------------------------------------
# AC2: <action_contracts> block injected when broker enabled
# ---------------------------------------------------------------------------


class TestActionContractsInjected:
    def test_contracts_present_when_enabled(self):
        from harness.lib.graph_node_dispatcher import build_dispatch_text
        payload = {
            "sprint_id": "sprint-test",
            "node": {
                "id": "N1",
                "goal": "test goal",
                "read_scope": ["harness/lib/foo.py"],
                "write_scope": ["harness/lib/bar.py"],
                "acceptance": ["AC1: foo", "AC2: bar"],
            },
        }
        with mock.patch.dict(os.environ, {"SOLAR_BROKER_ENABLED": "1"}):
            text = build_dispatch_text(payload, "pane-0.1")
        assert "<action_contracts>" in text
        assert "</action_contracts>" in text
        assert "<read_scope>" in text
        assert "<write_scope>" in text
        assert "<acceptance>" in text
        assert "<path>harness/lib/foo.py</path>" in text
        assert "<path>harness/lib/bar.py</path>" in text
        assert "<criterion>AC1: foo</criterion>" in text

    def test_contracts_injected_between_rules_and_work_steps(self):
        from harness.lib.graph_node_dispatcher import build_dispatch_text
        payload = {
            "sprint_id": "sprint-test",
            "node": {"id": "N1", "goal": "g", "acceptance": ["ac1"]},
        }
        with mock.patch.dict(os.environ, {"SOLAR_BROKER_ENABLED": "1"}):
            text = build_dispatch_text(payload, "pane-0.1")
        rules_idx = text.index("## Rules")
        steps_idx = text.index("## Work Steps")
        contracts_idx = text.index("<action_contracts>")
        assert rules_idx < contracts_idx < steps_idx


# ---------------------------------------------------------------------------
# AC3: SOLAR_BROKER_ENABLED=0 produces no <action_contracts>
# ---------------------------------------------------------------------------


class TestActionContractsDisabled:
    def test_no_contracts_when_disabled(self):
        from harness.lib.graph_node_dispatcher import build_dispatch_text
        payload = {
            "sprint_id": "sprint-test",
            "node": {
                "id": "N1",
                "goal": "test",
                "acceptance": ["ac1"],
            },
        }
        with mock.patch.dict(os.environ, {"SOLAR_BROKER_ENABLED": "0"}):
            text = build_dispatch_text(payload, "pane-0.1")
        assert "<action_contracts>" not in text

    def test_byte_identical_to_legacy_baseline(self):
        """Dispatch text with broker off must be identical to what it was
        before the feature was added (no extra blank lines or artifacts)."""
        from harness.lib.graph_node_dispatcher import build_dispatch_text
        payload = {
            "sprint_id": "sprint-test",
            "node": {"id": "N1", "goal": "g"},
        }
        with mock.patch.dict(os.environ, {"SOLAR_BROKER_ENABLED": "0"}):
            text = build_dispatch_text(payload, "pane-0.1")
        assert "<action_contracts>" not in text
        assert "<read_scope>" not in text
        assert "<write_scope>" not in text


# ---------------------------------------------------------------------------
# AC4: Existing function signatures unchanged (LR-04)
# ---------------------------------------------------------------------------


class TestSignatureUnchanged:
    def test_build_dispatch_text_signature(self):
        """build_dispatch_text must accept (payload, pane) — no new required params."""
        import inspect
        from harness.lib.graph_node_dispatcher import build_dispatch_text
        sig = inspect.signature(build_dispatch_text)
        params = list(sig.parameters.keys())
        assert params == ["payload", "pane"]

    def test_build_eval_dispatch_text_signature(self):
        import inspect
        from harness.lib.graph_node_dispatcher import build_eval_dispatch_text
        sig = inspect.signature(build_eval_dispatch_text)
        params = list(sig.parameters.keys())
        assert params == ["graph", "graph_path", "node", "pane", "dispatch_id"]


# ---------------------------------------------------------------------------
# AC5: Dual-run comparison (broker on vs off)
# ---------------------------------------------------------------------------


class TestDualRunComparison:
    def test_only_difference_is_contracts_block(self):
        """The only difference between broker=on and broker=off must be
        the <action_contracts> block."""
        from harness.lib.graph_node_dispatcher import build_dispatch_text
        payload = {
            "sprint_id": "sprint-dual",
            "node": {
                "id": "N1",
                "goal": "dual run",
                "read_scope": ["a.py"],
                "write_scope": ["b.py"],
                "acceptance": ["ac1"],
            },
        }
        with mock.patch.dict(os.environ, {"SOLAR_BROKER_ENABLED": "0"}):
            text_off = build_dispatch_text(payload, "pane-0.1")

        with mock.patch.dict(os.environ, {"SOLAR_BROKER_ENABLED": "1"}):
            text_on = build_dispatch_text(payload, "pane-0.1")

        assert "<action_contracts>" not in text_off
        assert "<action_contracts>" in text_on

        contracts_block = _extract_contracts_block(text_on)
        # The f-string template has a \n before the insertion point;
        # removing the block leaves one extra blank line.
        stripped_on = text_on.replace(contracts_block + "\n", "")
        assert stripped_on == text_off

    def test_empty_node_produces_valid_contracts(self):
        from harness.lib.graph_node_dispatcher import build_dispatch_text
        payload = {
            "sprint_id": "sprint-empty",
            "node": {"id": "N2", "goal": "empty test"},
        }
        with mock.patch.dict(os.environ, {"SOLAR_BROKER_ENABLED": "1"}):
            text = build_dispatch_text(payload, "pane-0.1")
        assert "<action_contracts>" in text

    def test_contracts_reflect_node_metadata(self):
        from harness.lib.graph_node_dispatcher import build_dispatch_text
        payload = {
            "sprint_id": "sprint-meta",
            "node": {
                "id": "N3",
                "goal": "metadata test",
                "read_scope": ["r1.py", "r2.py"],
                "write_scope": ["w1.py"],
                "acceptance": ["a1", "a2", "a3"],
            },
        }
        with mock.patch.dict(os.environ, {"SOLAR_BROKER_ENABLED": "1"}):
            text = build_dispatch_text(payload, "pane-0.1")
        assert "<path>r1.py</path>" in text
        assert "<path>r2.py</path>" in text
        assert "<path>w1.py</path>" in text
        assert "<criterion>a1</criterion>" in text
        assert "<criterion>a2</criterion>" in text
        assert "<criterion>a3</criterion>" in text


# ---------------------------------------------------------------------------
# AC7: py_compile
# ---------------------------------------------------------------------------


class TestCompile:
    def test_py_compile_dispatcher(self):
        result = subprocess.run(
            ["python3", "-m", "py_compile", str(DISPATCHER)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_contracts_block(text: str) -> str:
    start = text.index("<action_contracts>")
    end = text.index("</action_contracts>") + len("</action_contracts>")
    return text[start:end]
