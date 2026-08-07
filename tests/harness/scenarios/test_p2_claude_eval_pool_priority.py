#!/usr/bin/env python3
"""P2 Claude smoke deterministic replay (fail bundle
p2-sprint-20260708-023541-wf-code-cli-smoke-anthropic-failed-20260708T024638Z).

First live Claude/Anthropic smoke at 5dfde697: preflights green, S1 builder
dispatched through the operator pool (anthropic route records, exit 0) — then
S1 wedged in `reviewing` for the whole §4 budget. The dispatch ledger shows
why: the S1 eval was intent-injected into the live cockpit TUI pane
(`solar-claude-e2e-...:0.3`), not the operator pool. `_discover_evaluators`
sorts by `_pane_evaluator_priority`, which gives the cockpit pane `:0.3`
priority 0 and the `operator-pool:evaluator.0` virtual worker priority 9, and
`_evaluation_capacity_snapshot` selects `available[:required]` — pure list
order. Claude TUI panes accept direct dispatch and match the evaluator role,
so the pane always outranks the pool on the claude runtime; the injected eval
sat unexecuted, and the in-flight dispatch sidecar suppressed every later
tick (`dispatched: []` for 8+ minutes — the rc8 inflight-suppression wedge
class). Codex panes cannot take direct dispatch, which is why every codex
smoke correctly used the pool and this never surfaced before.

A pane eval is also EVIDENCE-FREE: no operatord lease, no result.json, no
submitted/completed route records. On the contracted path the operator pool
is the evidence-generating evaluator seam, so contracted graphs must prefer
dispatchable pool evaluators over TUI panes (panes remain fallback when the
pool has no dispatchable evaluator). Uncontracted/legacy cockpit graphs keep
pane-first ordering unchanged.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_HARNESS = (Path(__file__).resolve().parents[3] / 'harness')
_HARNESS_LIB = str(_HARNESS / "lib")
if _HARNESS_LIB not in sys.path:
    sys.path.insert(0, _HARNESS_LIB)

import graph_node_dispatcher as gnd  # noqa: E402


def _pane_evaluator(pane: str = "solar-claude-e2e-x:0.3", busy: bool = False) -> dict:
    return {
        "pane": pane,
        "models": ["opus", "sonnet"],
        "skills": ["review", "testing", "bash"],
        "busy": busy,
        "title": "Evaluator 审判官",
        "evaluator_host_role": "evaluator",
        "unavailable_reason": "",
    }


def _pool_evaluator(busy: bool = False) -> dict:
    return {
        "pane": "operator-pool:evaluator.0",
        "models": ["operator-pool", "opus"],
        "skills": ["review", "testing", "bash"],
        "busy": busy,
        "title": "operator pool evaluator",
        "evaluator_host_role": "operator_pool",
        "unavailable_reason": "",
    }


def _contracted_graph() -> dict:
    return {"sprint_id": "p2-claude-eval", "workflow_contract_id": "code.cli_smoke_anthropic"}


@pytest.fixture(autouse=True)
def _flags(monkeypatch):
    monkeypatch.setenv("SOLAR_GATE_LEDGER", "1")
    monkeypatch.setenv("SOLAR_GRAPH_EVAL_OPERATOR_POOL", "1")


def _selected_pane(graph: dict, evaluators: list[dict]) -> str:
    ordered = gnd._order_evaluators_for_graph(graph, evaluators)
    capacity = gnd._evaluation_capacity_snapshot({"required_evaluators": 1}, ordered)
    panes = capacity.get("selected_panes") or []
    return str(panes[0]) if panes else ""


def test_contracted_graph_prefers_pool_evaluator_over_live_pane():
    # the live failure shape: cockpit pane first in discovery order, pool last
    evaluators = [_pane_evaluator(), _pool_evaluator()]
    assert _selected_pane(_contracted_graph(), evaluators) == "operator-pool:evaluator.0", (
        "contracted eval dispatch selected the TUI pane over the operator "
        "pool — the evidence-free pane path that wedged the live claude "
        "smoke (S1 reviewing, zero evaluator route records)"
    )


def test_uncontracted_graph_keeps_pane_first_ordering():
    evaluators = [_pane_evaluator(), _pool_evaluator()]
    graph = {"sprint_id": "legacy-cockpit"}
    assert _selected_pane(graph, evaluators) == "solar-claude-e2e-x:0.3"


def test_flag_off_keeps_pane_first_even_when_contracted(monkeypatch):
    monkeypatch.setenv("SOLAR_GATE_LEDGER", "0")
    evaluators = [_pane_evaluator(), _pool_evaluator()]
    assert _selected_pane(_contracted_graph(), evaluators) == "solar-claude-e2e-x:0.3"


def test_busy_pool_falls_back_to_pane():
    evaluators = [_pane_evaluator(), _pool_evaluator(busy=True)]
    assert _selected_pane(_contracted_graph(), evaluators) == "solar-claude-e2e-x:0.3"


def test_pool_only_list_unchanged():
    evaluators = [_pool_evaluator()]
    assert _selected_pane(_contracted_graph(), evaluators) == "operator-pool:evaluator.0"


def test_eval_pool_flag_off_keeps_pane_first(monkeypatch):
    monkeypatch.setenv("SOLAR_GRAPH_EVAL_OPERATOR_POOL", "0")
    monkeypatch.setenv("SOLAR_GRAPH_BUILDER_OPERATOR_POOL", "0")
    evaluators = [_pane_evaluator(), _pool_evaluator()]
    assert _selected_pane(_contracted_graph(), evaluators) == "solar-claude-e2e-x:0.3"
