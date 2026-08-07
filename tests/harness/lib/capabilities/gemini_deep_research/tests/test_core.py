"""Unit tests for the Gemini Deep Research core runtime (C4).

Covers: schema validation, persistence secret-refusal, state-machine
transitions/coverage, controller O1-O6 happy/fail/guard paths, retry policy,
success criteria, and event-replay state reconstruction equality.

Run:
    python3 -m unittest gemini_deep_research.tests.test_core -v
"""

from . import conftest_path  # noqa: F401  (sys.path bootstrap)

import tempfile
import unittest
from pathlib import Path

from gemini_deep_research.core import (
    ControllerState,
    GeminiDRController,
    InvalidTransition,
    OptimizeFailed,
    RetryPolicy,
    all_states,
    assert_transition,
    can_transition,
    evaluate_success,
)
from gemini_deep_research.core.retry import Disposition
from gemini_deep_research.schemas import (
    AsyncState,
    DRPlan,
    DRResult,
    DRRunHandle,
    EventLog,
    InvalidResearchRequest,
    OptimizedPrompt,
    Reference,
    ResearchRequest,
    ResultStatus,
    Source,
)


def make_refs(n=3):
    cats = ["paper", "news", "blog", "docs"]
    return [Reference(cats[i % len(cats)], f"T{i}", f"https://example.com/{i}") for i in range(n)]


class FakeOperator:
    """In-memory BrowserOperatorPort double driving a scripted poll trajectory."""

    def __init__(self, poll_states, *, refs=None, report="report body", directive=True):
        self.poll_states = list(poll_states)
        self.i = 0
        self.refs = make_refs() if refs is None else refs
        self.report = report
        self.directive = directive
        self.submitted = 0

    def optimize_prompt(self, req, template_id):
        return OptimizedPrompt(req.request_id, "optimized: " + req.question, "chat-1", self.directive, template_id)

    def submit(self, prompt):
        self.submitted += 1
        return DRPlan("job-fake", True, "btn-start")

    def confirm(self, plan):
        return DRRunHandle(plan.run_ref, AsyncState.RUNNING, True, "2026-05-29T00:00:00Z", 1)

    def poll(self, handle):
        s = self.poll_states[min(self.i, len(self.poll_states) - 1)]
        self.i += 1
        return DRRunHandle(handle.run_ref, s, True, handle.started_at, handle.attempt)

    def collect(self, handle):
        return DRResult(handle.run_ref, ResultStatus.SUCCEEDED, report_text=self.report,
                        references=self.refs, evidence_refs=["ev/trace.json"])


class TempLogMixin:
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.log = EventLog(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()


class TestSchemas(unittest.TestCase):
    def test_valid_request_roundtrip(self):
        r = ResearchRequest.create("  hello world  ", source="user")
        self.assertEqual(r.source, Source.USER)
        self.assertEqual(ResearchRequest.from_dict(r.to_dict()).question, r.question)

    def test_empty_question_rejected(self):
        with self.assertRaises(InvalidResearchRequest):
            ResearchRequest.create("   ")

    def test_oversized_question_rejected(self):
        with self.assertRaises(InvalidResearchRequest):
            ResearchRequest.create("x" * 9000)

    def test_upstream_requires_ref(self):
        with self.assertRaises(InvalidResearchRequest):
            ResearchRequest.create("q", source="upstream")
        ok = ResearchRequest.create("q", source="upstream", upstream_ref="op-1")
        self.assertEqual(ok.upstream_ref, "op-1")

    def test_invalid_source(self):
        with self.assertRaises(InvalidResearchRequest):
            ResearchRequest(question="q", source="weird", request_id="i", created_at="t")

    def test_optimized_prompt_directive_required(self):
        with self.assertRaises(InvalidResearchRequest):
            OptimizedPrompt("id", "txt", "sess", False, "t").validate()

    def test_reference_bad_url(self):
        with self.assertRaises(InvalidResearchRequest):
            Reference("cat", "title", "ftp://nope").validate()

    def test_drresult_succeeded_requires_refs(self):
        with self.assertRaises(InvalidResearchRequest):
            DRResult("r", ResultStatus.SUCCEEDED, report_text="x", references=[]).validate()

    def test_drresult_failed_requires_reason(self):
        with self.assertRaises(InvalidResearchRequest):
            DRResult("r", ResultStatus.FAILED).validate()
        DRResult("r", ResultStatus.FAILED, failure_reason="boom").validate()

    def test_drresult_roundtrip(self):
        res = DRResult("r", ResultStatus.SUCCEEDED, report_text="body", references=make_refs())
        back = DRResult.from_dict(res.to_dict())
        self.assertEqual(len(back.references), 3)
        self.assertEqual(back.references[0].url, "https://example.com/0")


class TestPersistence(TempLogMixin, unittest.TestCase):
    def test_append_and_read_seq(self):
        self.log.append("run", "a", {"k": 1})
        self.log.append("run", "b", {"k": 2})
        evs = self.log.read_all("run")
        self.assertEqual([e.seq for e in evs], [0, 1])
        self.assertEqual(evs[1].payload["k"], 2)

    def test_secret_refused(self):
        for key in ("token", "cookie", "password", "authorization"):
            with self.assertRaises(ValueError):
                self.log.append("run", "x", {key: "leak"})

    def test_read_missing_run_empty(self):
        self.assertEqual(self.log.read_all("nope"), [])


class TestStateMachine(unittest.TestCase):
    def test_all_states_present(self):
        names = {s.value for s in all_states()}
        self.assertEqual(
            names,
            {"input", "optimize", "submit", "confirm", "monitor", "done", "retry", "fail"},
        )

    def test_legal_transitions(self):
        self.assertTrue(can_transition(ControllerState.INPUT, ControllerState.OPTIMIZE))
        self.assertTrue(can_transition(ControllerState.MONITOR, ControllerState.MONITOR))
        self.assertTrue(can_transition(ControllerState.RETRY, ControllerState.SUBMIT))

    def test_illegal_transition_raises(self):
        with self.assertRaises(InvalidTransition):
            assert_transition(ControllerState.DONE, ControllerState.SUBMIT)
        with self.assertRaises(InvalidTransition):
            assert_transition(ControllerState.INPUT, ControllerState.MONITOR)

    def test_every_state_reachable_from_input(self):
        # BFS over transition graph; RETRY/CONFIRM/MONITOR/DONE/FAIL must be reachable
        from gemini_deep_research.core.state_machine import _TRANSITIONS

        seen = {ControllerState.INPUT}
        frontier = [ControllerState.INPUT]
        while frontier:
            s = frontier.pop()
            for nxt in _TRANSITIONS[s]:
                if nxt not in seen:
                    seen.add(nxt)
                    frontier.append(nxt)
        self.assertEqual(seen, set(all_states()))


class TestRetryAndSuccess(unittest.TestCase):
    def test_backoff_caps(self):
        p = RetryPolicy()
        self.assertEqual(p.backoff_seconds(1), 30)
        self.assertEqual(p.backoff_seconds(2), 60)
        self.assertEqual(p.backoff_seconds(10), 300)  # capped

    def test_classify(self):
        p = RetryPolicy()
        self.assertEqual(p.classify(AsyncState.DONE), Disposition.OK)
        self.assertEqual(p.classify(AsyncState.REAUTH_REQUIRED), Disposition.WAITING_HUMAN)
        self.assertEqual(p.classify(AsyncState.WAITING_HUMAN), Disposition.WAITING_HUMAN)
        self.assertEqual(p.classify(AsyncState.FAILED), Disposition.RETRY)

    def test_success_criteria(self):
        good = DRResult("r", ResultStatus.SUCCEEDED, report_text="x", references=make_refs(3))
        self.assertTrue(evaluate_success(AsyncState.DONE, good).ok)
        # too few refs
        few = DRResult("r", ResultStatus.SUCCEEDED, report_text="x", references=make_refs(2))
        self.assertFalse(evaluate_success(AsyncState.DONE, few).ok)
        # not done
        self.assertFalse(evaluate_success(AsyncState.RUNNING, good).ok)


class TestControllerPaths(TempLogMixin, unittest.TestCase):
    def test_happy_path(self):
        op = FakeOperator([AsyncState.RUNNING, AsyncState.DONE])
        c = GeminiDRController(op, event_log=self.log)
        req = ResearchRequest.create("q happy")
        res = c.run(req)
        self.assertEqual(res.status, ResultStatus.SUCCEEDED)
        self.assertEqual(c.state, ControllerState.DONE)
        self.assertEqual(len(res.references), 3)

    def test_optimize_no_directive_fails_before_o3(self):
        op = FakeOperator([AsyncState.DONE], directive=False)
        c = GeminiDRController(op, event_log=self.log)
        with self.assertRaises(OptimizeFailed):
            c.run(ResearchRequest.create("q"))
        self.assertEqual(c.state, ControllerState.FAIL)
        self.assertEqual(op.submitted, 0)  # never reached O3

    def test_waiting_human_stops(self):
        op = FakeOperator([AsyncState.REAUTH_REQUIRED])
        c = GeminiDRController(op, event_log=self.log)
        res = c.run(ResearchRequest.create("q"))
        self.assertEqual(c.state, ControllerState.FAIL)
        self.assertIn("waiting_human", res.failure_reason)

    def test_failed_exhausts_attempts(self):
        op = FakeOperator([AsyncState.FAILED])
        c = GeminiDRController(op, event_log=self.log, retry_policy=RetryPolicy(max_attempts=1))
        res = c.run(ResearchRequest.create("q"))
        self.assertEqual(c.state, ControllerState.FAIL)
        self.assertIn("attempts_exhausted", res.failure_reason)

    def test_done_but_incomplete_marks_failed(self):
        op = FakeOperator([AsyncState.DONE], refs=make_refs(1))  # below MIN_REFS
        c = GeminiDRController(op, event_log=self.log)
        res = c.run(ResearchRequest.create("q"))
        self.assertEqual(res.status, ResultStatus.FAILED)
        self.assertIn("incomplete_result", res.failure_reason)


class TestEventReplay(TempLogMixin, unittest.TestCase):
    def test_replay_equals_live_happy(self):
        op = FakeOperator([AsyncState.RUNNING, AsyncState.DONE])
        c = GeminiDRController(op, event_log=self.log)
        req = ResearchRequest.create("q replay")
        c.run(req)
        live = c.snapshot()
        rebuilt = GeminiDRController.rebuild(req.request_id, self.log)
        self.assertEqual(rebuilt.state, live.state)
        self.assertEqual(rebuilt.result.status, live.result.status)
        self.assertEqual(rebuilt.handle.async_state, live.handle.async_state)

    def test_replay_equals_live_fail(self):
        op = FakeOperator([AsyncState.FAILED])
        c = GeminiDRController(op, event_log=self.log, retry_policy=RetryPolicy(max_attempts=1))
        req = ResearchRequest.create("q replay fail")
        c.run(req)
        live = c.snapshot()
        rebuilt = GeminiDRController.rebuild(req.request_id, self.log)
        self.assertEqual(rebuilt.state, live.state)
        self.assertEqual(rebuilt.state, ControllerState.FAIL)

    def test_replay_unknown_run_is_input(self):
        snap = GeminiDRController.rebuild("never-existed", self.log)
        self.assertEqual(snap.state, ControllerState.INPUT)
        self.assertIsNone(snap.run_ref)


if __name__ == "__main__":
    unittest.main(verbosity=2)
