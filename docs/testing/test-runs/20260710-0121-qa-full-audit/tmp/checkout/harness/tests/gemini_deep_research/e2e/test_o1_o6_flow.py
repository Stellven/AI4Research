"""V1 — reproducible end-to-end O1-O6 flow test.

Exercises the full chain once: O1 intake (user-direct AND upstream caller) ->
O2 李教授 prompt optimization -> O3 submit DR -> O4 confirm -> O5 monitor/retry
-> O6 collect classified literature. Two layers of evidence:

1. ``TestO1toO6HappyPath`` / ``TestUpstreamCaller`` drive the real
   ``GeminiDRController`` over a scripted operator double through every outcome
   and assert a terminal DONE with classified, sourced references + a complete
   event trajectory + event-replay equality (no silent half-completion).
2. ``TestEndToEndThroughRealOperator`` drives the chain through the real
   ``DeepResearchBrowserAdapter`` -> ``browser_job_runtime`` in mock mode
   (GEMINI_DR_REAL_CALLS unset): proves the full wiring fires against the
   existing operator runtime and that without real DR output the run ends in an
   HONEST FAILED (no fabricated references), not a fake success.

Run from harness root:
    PYTHONPATH=lib/capabilities python3 -m unittest \
        tests.gemini_deep_research.e2e.test_o1_o6_flow -v
"""

from __future__ import annotations

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
    RetryPolicy,
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
    Source,
)

# O1-O6 outcome -> the event type that proves it fired.
_OUTCOME_EVENTS = ["input_received", "optimized", "submitted", "confirmed", "polled", "collected", "succeeded"]


def classified_refs():
    """Multi-category sourced references (O6 acceptance: classified literature)."""
    return [
        Reference("paper", "Cache-to-Cache KV Transfer", "https://arxiv.org/abs/2510.00001"),
        Reference("news", "Gemini Deep Research GA", "https://blog.google/dr"),
        Reference("blog", "How DR plans research", "https://example.com/dr-blog"),
        Reference("docs", "DR API reference", "https://ai.google.dev/dr"),
    ]


class ScriptedOperator:
    """In-memory BrowserOperatorPort double driving a full O1-O6 trajectory."""

    def __init__(self, poll_states, *, refs=None, report="full research report body"):
        self.poll_states = list(poll_states)
        self.i = 0
        self.refs = classified_refs() if refs is None else refs
        self.report = report
        self.submits = 0
        self.optimized_with_directive = False

    def optimize_prompt(self, req, template_id):
        # 李教授 template embeds the classified-reference directive (O2 contract).
        self.optimized_with_directive = True
        return OptimizedPrompt(
            req.request_id,
            f"[{template_id}] research: {req.question} (classify sources)",
            f"chat-{req.request_id}",
            True,
            template_id,
        )

    def submit(self, prompt):
        self.submits += 1
        return DRPlan("job-e2e", True, "gemini-start-research")

    def confirm(self, plan):
        return DRRunHandle(plan.run_ref, AsyncState.SUBMITTED, True, "2026-05-29T00:00:00Z", 1)

    def poll(self, handle):
        s = self.poll_states[min(self.i, len(self.poll_states) - 1)]
        self.i += 1
        return DRRunHandle(handle.run_ref, s, True, handle.started_at, handle.attempt)

    def collect(self, handle):
        return DRResult(handle.run_ref, ResultStatus.SUCCEEDED, report_text=self.report,
                        references=self.refs, evidence_refs=["ev/trace.json", "ev/report.md"])


class _TmpLog(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.log = EventLog(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()


class TestO1toO6HappyPath(_TmpLog):
    def test_full_chain_produces_classified_literature(self):
        op = ScriptedOperator([AsyncState.SUBMITTED, AsyncState.PLANNING, AsyncState.RUNNING, AsyncState.DONE])
        c = GeminiDRController(op, event_log=self.log)
        req = ResearchRequest.create("survey cross-model KV cache transfer methods")

        res = c.run(req)

        # O6: terminal success with classified, sourced literature.
        self.assertEqual(c.state, ControllerState.DONE)
        self.assertEqual(res.status, ResultStatus.SUCCEEDED)
        self.assertGreaterEqual(len(res.references), 3)
        categories = {r.category for r in res.references}
        self.assertGreaterEqual(len(categories), 2, "references must be classified across categories")
        for r in res.references:
            self.assertTrue(r.url.startswith("http"), f"unsourced reference: {r}")
        self.assertTrue(res.report_text)
        # O2 actually ran the optimizer with a directive.
        self.assertTrue(op.optimized_with_directive)

    def test_every_outcome_emits_its_event(self):
        op = ScriptedOperator([AsyncState.PLANNING, AsyncState.RUNNING, AsyncState.DONE])
        c = GeminiDRController(op, event_log=self.log)
        req = ResearchRequest.create("e2e event trajectory")
        c.run(req)
        types_seen = [e.type for e in self.log.read_all(req.request_id)]
        for expected in _OUTCOME_EVENTS:
            self.assertIn(expected, types_seen, f"O-chain missing event {expected}")
        # at least one transient poll before terminal -> monitoring actually looped
        self.assertGreaterEqual(types_seen.count("polled"), 2)

    def test_replay_equals_live(self):
        op = ScriptedOperator([AsyncState.RUNNING, AsyncState.DONE])
        c = GeminiDRController(op, event_log=self.log)
        req = ResearchRequest.create("e2e replay")
        c.run(req)
        live = c.snapshot()
        rebuilt = GeminiDRController.rebuild(req.request_id, self.log)
        self.assertEqual(rebuilt.state, live.state)
        self.assertEqual(rebuilt.result.status, live.result.status)
        self.assertEqual(len(rebuilt.result.references), len(live.result.references))


class TestUpstreamCaller(_TmpLog):
    """Requirement #1: input may come from the user OR an upstream operator."""

    def test_upstream_caller_same_entrypoint(self):
        op = ScriptedOperator([AsyncState.RUNNING, AsyncState.DONE])
        c = GeminiDRController(op, event_log=self.log)
        req = ResearchRequest.create("upstream-fed question", source="upstream", upstream_ref="op-node-42")
        res = c.run(req)
        self.assertEqual(req.source, Source.UPSTREAM)
        self.assertEqual(res.status, ResultStatus.SUCCEEDED)
        # the upstream ref is preserved in the persisted intake event.
        intake = self.log.read_all(req.request_id)[0]
        self.assertEqual(intake.type, "input_received")
        self.assertEqual(intake.payload["request"]["upstream_ref"], "op-node-42")


class TestEndToEndThroughRealOperator(_TmpLog):
    """Drive the chain through the REAL DeepResearchBrowserAdapter in mock mode.

    Proves the integration is wired to the existing browser_job_runtime (a real
    job is created/polled/collected) and that, with real calls gated OFF, the
    run ends in an honest FAILED instead of fabricating a successful result.
    """

    def test_mock_mode_is_honest_failure_not_fake_success(self):
        os.environ.pop("GEMINI_DR_REAL_CALLS", None)
        from gemini_deep_research.compat.operator_adapter import DeepResearchBrowserAdapter

        op = DeepResearchBrowserAdapter(mock_sequence=["planning", "running", "done"])
        c = GeminiDRController(op, event_log=self.log, retry_policy=RetryPolicy(max_attempts=1))
        req = ResearchRequest.create("real-wiring smoke through browser_job_runtime")
        res = c.run(req)

        # full O1-O6 wiring fired against the real operator runtime ...
        types_seen = [e.type for e in self.log.read_all(req.request_id)]
        self.assertIn("submitted", types_seen)
        self.assertIn("confirmed", types_seen)
        self.assertIn("polled", types_seen)
        # ... but without real DR output we do NOT claim success.
        self.assertEqual(res.status, ResultStatus.FAILED)
        self.assertEqual(res.references, [])
        self.assertIsNotNone(res.failure_reason)


if __name__ == "__main__":
    unittest.main(verbosity=2)
