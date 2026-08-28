from __future__ import annotations

import importlib.util
import json
from pathlib import Path


MODULE = Path(__file__).resolve().parents[2] / "harness" / "lib" / "graph_dispatch_outcome.py"


def _load():
    spec = importlib.util.spec_from_file_location("graph_dispatch_outcome_test", MODULE)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_builder_result_pending_is_waiting_not_failure() -> None:
    mod = _load()
    raw = json.dumps({
        "ok": False,
        "dispatched": [],
        "skipped": [{
            "node": "S1",
            "reason": "builder_operator_result_pending",
            "complete": False,
        }],
        "terminalized": [],
    })

    assert mod.classify_evaluator_dispatch_output(raw) == {
        "reason": "builder_operator_result_pending",
        "node": "S1",
        "nodes": ["S1"],
        "waiting_count": 1,
    }


def test_real_dispatch_errors_are_not_reclassified() -> None:
    mod = _load()
    for payload in (
        {"ok": False, "skipped": [{"node": "S1", "reason": "no_available_evaluator"}]},
        {"ok": False, "skipped": [{"node": "S1", "reason": "builder_operator_result_failed", "complete": True}]},
        {"ok": False, "dispatched": [], "skipped": []},
        {"ok": False, "dispatched": [{"node": "S1"}], "skipped": [{"node": "S2", "reason": "builder_operator_result_pending", "complete": False}]},
    ):
        assert mod.classify_evaluator_dispatch_output(json.dumps(payload)) is None


def test_invalid_output_is_not_reclassified() -> None:
    mod = _load()
    assert mod.classify_evaluator_dispatch_output("not json") is None
