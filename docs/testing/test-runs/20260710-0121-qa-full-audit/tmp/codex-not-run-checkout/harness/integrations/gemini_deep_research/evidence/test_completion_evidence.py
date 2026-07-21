"""U3 unit tests. Run from harness root:

    python3 -m unittest integrations.gemini_deep_research.evidence.test_completion_evidence -v
"""

import json
import tempfile
import unittest
from pathlib import Path

from integrations.gemini_deep_research.evidence import (
    build_evidence,
    verify_evidence,
    write_evidence,
)
from gemini_deep_research.core import GeminiDRController, RetryPolicy
from gemini_deep_research.schemas import (
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


def refs(n=3):
    cats = ["paper", "news", "blog"]
    return [Reference(cats[i % 3], f"T{i}", f"https://x.com/{i}") for i in range(n)]


class FakeOp:
    def __init__(self, states, *, rcount=3, report="body"):
        self.states = list(states)
        self.i = 0
        self.rcount = rcount
        self.report = report

    def optimize_prompt(self, req, tid):
        return OptimizedPrompt(req.request_id, "p:" + req.question, "chat", True, tid)

    def submit(self, p):
        return DRPlan("job-ev", True, "btn")

    def confirm(self, plan):
        return DRRunHandle("job-ev", AsyncState.RUNNING, True, "2026-05-29T00:00:00Z", 1)

    def poll(self, h):
        s = self.states[min(self.i, len(self.states) - 1)]
        self.i += 1
        return DRRunHandle(h.run_ref, s, True, h.started_at, h.attempt)

    def collect(self, h):
        return DRResult("job-ev", ResultStatus.SUCCEEDED, report_text=self.report,
                        references=refs(self.rcount), evidence_refs=["ev/trace.json", "ev/shot.png"])


class TestEvidence(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.log = EventLog(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _run(self, op, max_attempts=3):
        c = GeminiDRController(op, event_log=self.log, retry_policy=RetryPolicy(max_attempts=max_attempts))
        req = ResearchRequest.create("evidence q")
        c.run(req)
        return req.request_id

    def test_complete_run_evidence(self):
        rid = self._run(FakeOp([AsyncState.RUNNING, AsyncState.DONE]))
        ev = build_evidence(rid, self.log)
        self.assertEqual(ev.verdict, "complete")
        self.assertEqual(ev.result_status, "succeeded")
        self.assertEqual(ev.references_count, 3)
        self.assertGreaterEqual(ev.category_count, 1)
        self.assertIn("running", ev.async_state_trajectory)
        self.assertIn("done", ev.async_state_trajectory)
        self.assertEqual(ev.evidence_refs, ["ev/trace.json", "ev/shot.png"])

    def test_incomplete_run_evidence(self):
        rid = self._run(FakeOp([AsyncState.DONE], rcount=1))  # below MIN_REFS
        ev = build_evidence(rid, self.log)
        self.assertEqual(ev.verdict, "incomplete")
        self.assertIsNotNone(ev.success_reason)

    def test_no_run_evidence(self):
        ev = build_evidence("never", self.log)
        self.assertEqual(ev.verdict, "no_run")

    def test_write_and_reload(self):
        rid = self._run(FakeOp([AsyncState.DONE]))
        ev = build_evidence(rid, self.log)
        path = write_evidence(ev, self._tmp.name)
        self.assertTrue(path.exists())
        loaded = json.loads(Path(path).read_text())
        self.assertEqual(loaded["run_ref"], rid)
        self.assertEqual(loaded["verdict"], "complete")

    def test_evaluator_reverification_agrees(self):
        rid = self._run(FakeOp([AsyncState.RUNNING, AsyncState.DONE]))
        chk = verify_evidence(rid, self.log, "complete")
        self.assertTrue(chk["agrees"])
        self.assertEqual(chk["rederived"], "complete")

    def test_evaluator_catches_false_claim(self):
        rid = self._run(FakeOp([AsyncState.FAILED]), max_attempts=1)
        chk = verify_evidence(rid, self.log, "complete")  # lying claim
        self.assertFalse(chk["agrees"])  # re-derivation exposes it


if __name__ == "__main__":
    unittest.main(verbosity=2)
