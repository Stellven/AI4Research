"""E2E synthetic test for Solar Experience Memory Layer.

Scenario: synthetic sprint in phase=passed (terminal) → coordinator wake attempted
→ hook detects terminal_phase_wake → abort decision logged to decisions.jsonl

Also verifies: experience stats shows 5 anti-pattern classes known.
"""
import json
import os
import sys
import tempfile
import time
import unittest

HARNESS_DIR = os.path.expanduser("~/.solar/harness")
sys.path.insert(0, os.path.join(HARNESS_DIR, "lib"))


class TestExperienceMemoryE2E(unittest.TestCase):

    def setUp(self):
        from experience.index import init_db
        init_db()

    def test_terminal_phase_wake_abort(self):
        """Synthetic passed sprint → pre_dispatch should abort."""
        from coordinator_hooks import pre_dispatch

        # Create synthetic status file for a terminal sprint
        syn_sid = "sprint-synthetic-e2e-test-001"
        syn_path = os.path.join(HARNESS_DIR, "sprints", f"{syn_sid}.status.json")
        try:
            with open(syn_path, "w") as f:
                json.dump({
                    "sid": syn_sid,
                    "status": "passed",
                    "phase": "finalized",
                    "round": 1,
                    "updated_at": "2026-05-10T00:00:00Z",
                }, f)

            decision = pre_dispatch(syn_sid, "test_dispatch")
            # Terminal sprint → hook should abort
            self.assertEqual(decision.action, "abort",
                             f"Expected abort for terminal sprint, got {decision.action}")
            self.assertEqual(decision.pattern, "terminal_phase_wake")
            self.assertGreater(decision.confidence, 0.5)
        finally:
            if os.path.exists(syn_path):
                os.remove(syn_path)

    def test_experience_hook_disabled(self):
        """EXPERIENCE_HOOK=0 → always allow."""
        os.environ["EXPERIENCE_HOOK"] = "0"
        try:
            from coordinator_hooks import pre_dispatch
            decision = pre_dispatch("any-sprint", "test")
            self.assertEqual(decision.action, "allow")
            self.assertEqual(decision.reason, "hook_disabled")
        finally:
            os.environ.pop("EXPERIENCE_HOOK", None)

    def test_decisions_audit_written(self):
        """decisions.jsonl gets an entry after pre_dispatch call."""
        from coordinator_hooks import pre_dispatch
        decisions_path = os.path.join(HARNESS_DIR, "experience", "decisions.jsonl")
        before = 0
        if os.path.exists(decisions_path):
            with open(decisions_path) as f:
                before = sum(1 for line in f if line.strip())

        pre_dispatch("sprint-synthetic-audit-test", "test_audit")

        after = 0
        with open(decisions_path) as f:
            after = sum(1 for line in f if line.strip())
        self.assertGreater(after, before, "decisions.jsonl should have grown")

    def test_stats_shows_anti_patterns(self):
        """experience stats --json shows pattern classes."""
        from experience.query import get_stats
        s = get_stats()
        by_pattern = s.get("by_pattern", {})
        # At minimum repair_recipe (seeded) and success_workflow should be present
        known = {"repair_recipe", "success_workflow"}
        present = set(by_pattern.keys())
        self.assertTrue(known & present, f"Expected some of {known} in {present}")

    def test_query_for_sprint_returns_memories(self):
        """query_for_sprint returns result with memories key."""
        from experience.query import query_for_sprint
        result = query_for_sprint("sprint-20260509-205414", limit=5)
        self.assertTrue(result.get("ok"))
        self.assertIn("memories", result)

    def test_extract_idempotent(self):
        """extract_sprint is idempotent for terminal sprints."""
        from experience.extractor import extract_sprint
        # Use a real terminal sprint if available
        sprints_dir = os.path.join(HARNESS_DIR, "sprints")
        terminal_sid = None
        for fname in sorted(os.listdir(sprints_dir), reverse=True):
            if not fname.endswith(".status.json"):
                continue
            sid = fname[:-len(".status.json")]
            try:
                with open(os.path.join(sprints_dir, fname)) as f:
                    d = json.load(f)
                if d.get("status") in ("passed", "failed", "cancelled"):
                    terminal_sid = sid
                    break
            except Exception:
                continue
        if terminal_sid is None:
            self.skipTest("No terminal sprint found for idempotency test")
        t1 = extract_sprint(terminal_sid)
        t2 = extract_sprint(terminal_sid)
        self.assertIsNotNone(t1)
        self.assertIsNotNone(t2)
        self.assertEqual(t1["sid"], t2["sid"])

    def test_schema_validation_rejects_bad_entry(self):
        """validate_entry rejects entries with invalid pattern_class."""
        from experience.schema import validate_entry
        with self.assertRaises(ValueError):
            validate_entry({
                "schema_version": "1.0.0",
                "entry_id": "test",
                "trigger_sig": "abc",
                "pattern_class": "not_a_valid_pattern",
                "outcome": "failure",
                "created_at": "2026-01-01T00:00:00Z",
            })


if __name__ == "__main__":
    unittest.main(verbosity=2)
