"""RC9 product mode must execute DAG nodes through the operator pool.

A fresh installed-copy run exposed a cross-increment contradiction: product
mode intentionally leaves the four cockpit panes as passive viewers, while an
older coordinator default disables the builder operator pool.  Graph worker
discovery then selected a passive bash pane, consumed the queue item, and left
the user-visible task stuck at ``assigned`` forever.

These tests pin the product invariant without changing legacy cockpit mode:
the pool is the default executor in product mode, an explicit ``0`` remains a
kill switch, and passive panes are never returned as product-mode workers or
evaluators.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


_HARNESS = (Path(__file__).resolve().parents[3] / 'harness')
_COORDINATOR = _HARNESS / "coordinator.sh"
sys.path.insert(0, str(_HARNESS / "lib"))

import graph_node_dispatcher as gnd  # noqa: E402


def _coordinator_builder_pool_value(
    *, product_mode: str | None, configured: str | None
) -> str:
    """Evaluate only the coordinator's side-effect-free initialization prefix."""

    text = _COORDINATOR.read_text(encoding="utf-8")
    prefix = text.split("# sprint-20260503-163542 D3: bridge ledger", 1)[0]
    env = dict(os.environ)
    env["HARNESS_DIR"] = str(_HARNESS)
    if product_mode is None:
        env.pop("SOLAR_PRODUCT_MODE", None)
    else:
        env["SOLAR_PRODUCT_MODE"] = product_mode
    if configured is None:
        env.pop("SOLAR_GRAPH_BUILDER_OPERATOR_POOL", None)
    else:
        env["SOLAR_GRAPH_BUILDER_OPERATOR_POOL"] = configured
    result = subprocess.run(
        [
            "bash",
            "-c",
            prefix + '\nprintf "%s" "$SOLAR_GRAPH_BUILDER_OPERATOR_POOL"\n',
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_product_coordinator_defaults_builder_pool_on():
    assert _coordinator_builder_pool_value(product_mode="1", configured=None) == "1"


def test_product_coordinator_preserves_explicit_pool_kill_switch():
    assert _coordinator_builder_pool_value(product_mode="1", configured="0") == "0"


def test_legacy_coordinator_keeps_builder_pool_off_by_default():
    assert _coordinator_builder_pool_value(product_mode=None, configured=None) == "0"


def test_dispatcher_defaults_pool_on_only_for_product_mode(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("SOLAR_GRAPH_BUILDER_OPERATOR_POOL", raising=False)
    monkeypatch.setenv("SOLAR_PRODUCT_MODE", "1")
    assert gnd._builder_operator_pool_enabled() is True

    monkeypatch.setenv("SOLAR_PRODUCT_MODE", "0")
    assert gnd._builder_operator_pool_enabled() is False


def test_dispatcher_honors_explicit_product_pool_kill_switch(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SOLAR_PRODUCT_MODE", "1")
    monkeypatch.setenv("SOLAR_GRAPH_BUILDER_OPERATOR_POOL", "0")
    assert gnd._builder_operator_pool_enabled() is False


def test_product_pool_slots_use_provider_policy_available_count(
    monkeypatch: pytest.MonkeyPatch,
):
    """Forbidden-provider idle workers must not become virtual DAG slots."""

    monkeypatch.setattr(gnd, "_builder_operator_pool_enabled", lambda: True)

    class Completed:
        returncode = 0
        stdout = json.dumps({"total_available": 2, "total_policy_available": 0})

    monkeypatch.setattr(gnd.subprocess, "run", lambda *args, **kwargs: Completed())

    assert gnd._builder_operator_pool_available_count() == 0


def _stub_direct_pane_discovery(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOLAR_PRODUCT_MODE", "1")
    monkeypatch.setenv("SOLAR_HARNESS_SESSION", "solar-product")
    monkeypatch.setattr(
        gnd.subprocess,
        "check_output",
        lambda *args, **kwargs: b"solar-product:0.2\tBuilder\nsolar-product:0.3\tEvaluator\n",
    )
    monkeypatch.setattr(gnd, "_pane_in_harness_session_scope", lambda pane: True)
    monkeypatch.setattr(gnd, "_pane_exists", lambda pane: True)
    monkeypatch.setattr(gnd, "_pane_title", lambda pane: "Evaluator" if pane.endswith(".3") else "Builder")
    monkeypatch.setattr(gnd, "_pane_title_matches_role", lambda pane, title, role: pane.endswith(".3"))
    monkeypatch.setattr(gnd, "_lab_builder_can_host_evaluator", lambda pane, title: False)
    monkeypatch.setattr(gnd, "_dispatch_role_for_pane", lambda pane, title: "builder")
    monkeypatch.setattr(gnd, "_recover_hung_pane", lambda pane: False)
    monkeypatch.setattr(gnd, "_models_for_pane", lambda pane, title="": ["claude-sonnet"])
    monkeypatch.setattr(gnd, "_pane_tail", lambda pane: "")
    monkeypatch.setattr(gnd, "_pane_health", lambda pane: {})
    monkeypatch.setattr(gnd, "_quota_exhausted_models", lambda *args: [])
    monkeypatch.setattr(gnd, "_pane_cooldown_reason", lambda pane: "")
    monkeypatch.setattr(gnd, "_pane_in_helper_session", lambda pane: False)
    monkeypatch.setattr(gnd, "_pane_current_command", lambda pane: "bash")
    monkeypatch.setattr(gnd, "_pane_runtime_unavailable_reason", lambda pane, title: "")
    monkeypatch.setattr(gnd, "_multi_task_direct_dispatch_unavailable_reason", lambda *args, **kwargs: "")
    monkeypatch.setattr(gnd, "_pane_unavailable_reason", lambda pane: "")
    monkeypatch.setattr(gnd, "_pane_hygiene_unavailable_reason", lambda pane: "")
    monkeypatch.setattr(gnd, "_pane_has_active_lease", lambda pane: False)
    monkeypatch.setattr(gnd, "_pane_tui_busy", lambda pane: False)
    monkeypatch.setattr(gnd, "_actorhost_bridge", lambda **kwargs: {})


def test_product_worker_discovery_returns_only_operator_pool(monkeypatch: pytest.MonkeyPatch):
    _stub_direct_pane_discovery(monkeypatch)
    monkeypatch.setattr(
        gnd,
        "_builder_operator_pool_workers",
        lambda skills, capabilities: [
            {
                "pane": "operator-pool:builder.0",
                "role": "builder",
                "busy": False,
                "title": "operator pool builder",
            }
        ],
    )

    workers = gnd._discover_workers()

    assert [worker["pane"] for worker in workers] == ["operator-pool:builder.0"]


def test_product_evaluator_discovery_returns_only_operator_pool(monkeypatch: pytest.MonkeyPatch):
    _stub_direct_pane_discovery(monkeypatch)
    monkeypatch.setattr(gnd, "_prune_expired_operator_blocks", lambda: None)
    monkeypatch.setattr(
        gnd,
        "_evaluator_operator_pool_workers",
        lambda: [
            {
                "pane": "operator-pool:evaluator.0",
                "busy": False,
                "title": "operator pool evaluator",
            }
        ],
    )

    evaluators = gnd._discover_evaluators()

    assert [item["pane"] for item in evaluators] == ["operator-pool:evaluator.0"]
