"""V2 — negative-control + activation-proof, reproducible.

Negative control (the epic's anti-"half-completion" guard): every degraded or
failed path must produce an EXPLICIT failure with a reason, never a silent or
fabricated success.

  - O2 optimizer unavailable / missing reference directive -> fails before O3.
  - DR fails and retries to the configured limit -> attempts_exhausted FAILED.
  - waiting_human / reauth_required -> stops with a human blocker, no success.
  - done-but-incomplete (refs below threshold) -> FAILED, not a silent pass.
  - real-operator mock mode -> honest FAILED with zero fabricated references.

Activation-proof: a ready DAG node is computed deterministically and an
in-flight / terminal run routes to the correct harness role (builder / human /
evaluator), reproducibly.

Run from harness root:
    PYTHONPATH=lib/capabilities python3 -m unittest discover \
        -t tests/gemini_deep_research/control -s tests/gemini_deep_research/control -p "test_*.py" -v
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

_HARNESS_ROOT = Path(__file__).resolve().parents[3]
for _p in (str(_HARNESS_ROOT), str(_HARNESS_ROOT / "lib"), str(_HARNESS_ROOT / "lib" / "capabilities")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from gemini_deep_research.core import (  # noqa: E402
    ControllerState,
    GeminiDRController,
    OptimizeFailed,
    RetryPolicy,
    all_states,
)
from gemini_deep_research.schemas import (  # noqa: E402
    AsyncState,
    DRPlan,
    DRResult,
    DRRunHandle,
    EventLog,
    OptimizedPrompt,
    Reference,
    ResearchRequest,
    ResultStatus,
)

from integrations.gemini_deep_research.orchestration.auto_activation import (  # noqa: E402
    ROLE_BUILDER,
    ROLE_EVALUATOR,
    ROLE_HUMAN,
    decide_run_role,
    ready_nodes,
)


def refs(n=3):
    cats = ["paper", "news", "blog", "docs"]
    return [Reference(cats[i % len(cats)], f"T{i}", f"https://x.com/{i}") for i in range(n)]


class FakeOp:
    def __init__(self, poll_states, *, refs_n=3, directive=True, report="body"):
        self.poll_states = list(poll_states)
        self.i = 0
        self.refs_n = refs_n
        self.directive = directive
        self.report = report
        self.submits = 0

    def optimize_prompt(self, req, tid):
        return OptimizedPrompt(req.request_id, "opt:" + req.question, "chat", self.directive, tid)

    def submit(self, p):
        self.submits += 1
        return DRPlan("job-neg", True, "btn")

    def confirm(self, plan):
        return DRRunHandle(plan.run_ref, AsyncState.RUNNING, True, "2026-05-29T00:00:00Z", 1)

    def poll(self, h):
        s = self.poll_states[min(self.i, len(self.poll_states) - 1)]
        self.i += 1
        return DRRunHandle(h.run_ref, s, True, h.started_at, h.attempt)

    def collect(self, h):
        return DRResult(h.run_ref, ResultStatus.SUCCEEDED, report_text=self.report,
                        references=refs(self.refs_n), evidence_refs=["ev/t.json"])


class _TmpLog(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.log = EventLog(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()


class TestNegativeControl(_TmpLog):
    def test_optimizer_unavailable_fails_before_submit(self):
        op = FakeOp([AsyncState.DONE], directive=False)  # no reference directive
        c = GeminiDRController(op, event_log=self.log)
        with self.assertRaises(OptimizeFailed):
            c.run(ResearchRequest.create("q"))
        self.assertEqual(c.state, ControllerState.FAIL)
        self.assertEqual(op.submits, 0)  # never reached O3 — no wasted DR submit

    def test_dr_failure_retries_to_limit_then_explicit_fail(self):
        op = FakeOp([AsyncState.FAILED])
        c = GeminiDRController(op, event_log=self.log, retry_policy=RetryPolicy(max_attempts=1))
        res = c.run(ResearchRequest.create("q"))
        self.assertEqual(res.status, ResultStatus.FAILED)
        self.assertEqual(c.state, ControllerState.FAIL)
        self.assertIn("attempts_exhausted", res.failure_reason)

    def test_multi_attempt_resubmit_loop_never_succeeds(self):
        op = FakeOp([AsyncState.FAILED])
        c = GeminiDRController(op, event_log=self.log, retry_policy=RetryPolicy(max_attempts=3))
        req = ResearchRequest.create("q")
        res = None
        for _ in range(6):  # bounded safety; must terminate well before
            res = c.run(req)
            if "attempts_exhausted" in (res.failure_reason or ""):
                break
        self.assertIsNotNone(res)
        self.assertNotEqual(res.status, ResultStatus.SUCCEEDED)
        self.assertIn("attempts_exhausted", res.failure_reason)
        self.assertEqual(c.attempt, 3)  # stopped exactly at the limit

    def test_waiting_human_stops_with_blocker_not_success(self):
        op = FakeOp([AsyncState.REAUTH_REQUIRED])
        c = GeminiDRController(op, event_log=self.log)
        res = c.run(ResearchRequest.create("q"))
        self.assertEqual(c.state, ControllerState.FAIL)
        self.assertNotEqual(res.status, ResultStatus.SUCCEEDED)
        self.assertIn("waiting_human", res.failure_reason)

    def test_done_but_incomplete_is_failure_not_silent_pass(self):
        op = FakeOp([AsyncState.DONE], refs_n=1)  # below MIN_REFS
        c = GeminiDRController(op, event_log=self.log)
        res = c.run(ResearchRequest.create("q"))
        self.assertEqual(res.status, ResultStatus.FAILED)
        self.assertIn("incomplete_result", res.failure_reason)

    def test_real_operator_mock_mode_no_fabricated_refs(self):
        os.environ.pop("GEMINI_DR_REAL_CALLS", None)
        from gemini_deep_research.compat.operator_adapter import DeepResearchBrowserAdapter

        op = DeepResearchBrowserAdapter(mock_sequence=["planning", "running", "done"])
        c = GeminiDRController(op, event_log=self.log, retry_policy=RetryPolicy(max_attempts=1))
        res = c.run(ResearchRequest.create("negative wiring smoke"))
        self.assertEqual(res.status, ResultStatus.FAILED)
        self.assertEqual(res.references, [])


class TestActivationProof(unittest.TestCase):
    def _graph(self, statuses):
        return {
            "nodes": [
                {"id": "A", "depends_on": [], "status": statuses.get("A", "pending")},
                {"id": "B", "depends_on": ["A"], "status": statuses.get("B", "pending")},
                {"id": "C", "depends_on": ["A"], "status": statuses.get("C", "pending")},
                {"id": "D", "depends_on": ["B", "C"], "status": statuses.get("D", "pending")},
            ]
        }

    def _write(self, graph):
        f = tempfile.NamedTemporaryFile("w", suffix=".task_graph.json", delete=False)
        json.dump(graph, f)
        f.close()
        self.addCleanup(lambda: os.unlink(f.name))
        return f.name

    def test_only_dep_satisfied_nodes_are_ready(self):
        path = self._write(self._graph({}))  # all pending
        self.assertEqual(ready_nodes(path), ["A"])  # only the root is ready

    def test_completing_root_activates_children(self):
        path = self._write(self._graph({"A": "reviewing"}))
        self.assertEqual(sorted(ready_nodes(path)), ["B", "C"])

    def test_join_node_waits_for_all_parents(self):
        path = self._write(self._graph({"A": "passed", "B": "passed"}))  # C still open
        ready = ready_nodes(path)
        self.assertIn("C", ready)
        self.assertNotIn("D", ready)  # D needs B AND C

    def test_in_flight_run_routes_to_builder(self):
        d = decide_run_role(ControllerState.MONITOR)
        self.assertTrue(d.ready)
        self.assertEqual(d.role, ROLE_BUILDER)

    def test_terminal_done_routes_to_evaluator(self):
        d = decide_run_role(ControllerState.DONE)
        self.assertTrue(d.ready)
        self.assertEqual(d.role, ROLE_EVALUATOR)

    def test_waiting_human_blocker_routes_to_human_not_ready(self):
        d = decide_run_role(ControllerState.MONITOR, blocker="waiting_human:reauth_required")
        self.assertFalse(d.ready)
        self.assertEqual(d.role, ROLE_HUMAN)

    def test_every_controller_state_has_a_role(self):
        for st in all_states():
            d = decide_run_role(st)
            self.assertIn(d.role, {ROLE_BUILDER, ROLE_EVALUATOR})


if __name__ == "__main__":
    unittest.main(verbosity=2)
