"""U2 unit tests. Run from harness root:

    python3 -m unittest integrations.gemini_deep_research.ui.test_status_view -v
"""

import unittest

from integrations.gemini_deep_research.ui import status_view as sv
from integrations.gemini_deep_research.ui import build_epic_tree, render_text, to_dict

EPIC = (
    "epic-20260529-跑通-gemini-deep-research-我的具体要求是-1-"
    "从用户那里或者上游调用-上游算子那里获取问题输入-2"
)


class TestBlockerGating(unittest.TestCase):
    def test_active_sprint_hides_stale_blocker(self):
        status = {
            "status": "active",
            "phase": "planning_complete",
            "history": [{"event": "x", "blocked_by": ["sprint-foo-s02-architecture"]}],
        }
        self.assertEqual(sv._extract_blockers(status), [])

    def test_queued_sprint_shows_blocker(self):
        status = {
            "status": "queued",
            "phase": "epic_waiting_dependency",
            "history": [{"event": "x", "blocked_by": ["sprint-foo-s03-core-runtime"]}],
        }
        self.assertEqual(sv._extract_blockers(status), ["blocked_by:runtime"])

    def test_waiting_phase_shows_blocker(self):
        status = {
            "status": "active",
            "phase": "epic_waiting_dependency",
            "history": [{"blocked_by": ["a-ui", "b-evidence"]}],
        }
        self.assertEqual(sv._extract_blockers(status), ["blocked_by:ui,evidence"])


class TestEpicTreeReal(unittest.TestCase):
    def setUp(self):
        self.tree = build_epic_tree(EPIC)

    def test_five_child_sprints(self):
        self.assertGreaterEqual(len(self.tree.sprints), 5)

    def test_capabilities_surfaced(self):
        self.assertTrue(any(sp.capabilities for sp in self.tree.sprints))

    def test_nodes_present(self):
        for sp in self.tree.sprints:
            self.assertTrue(sp.nodes, f"{sp.sprint_id} has no nodes")

    def test_render_text_contains_epic_and_tree(self):
        txt = render_text(self.tree)
        self.assertIn("EPIC", txt)
        self.assertIn("s03-core-runtime", txt)

    def test_active_sprint_no_stale_blocker_in_render(self):
        # S03 is active; its render must not show a stale architecture blocker
        for sp in self.tree.sprints:
            if sp.sprint_id.endswith("s03-core-runtime") and sp.status == "active":
                self.assertEqual(sp.blockers, [])

    def test_to_dict_shape(self):
        d = to_dict(self.tree)
        self.assertEqual(d["epic_id"], EPIC)
        self.assertIn("sprints", d)
        self.assertIn("nodes", d["sprints"][0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
