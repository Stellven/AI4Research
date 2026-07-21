"""U1 unit tests. Run:

    python3 -m unittest integrations.gemini_deep_research.orchestration.test_auto_activation -v
(from the harness root)
"""

import json
import tempfile
import unittest
from pathlib import Path

from integrations.gemini_deep_research.orchestration import (
    ROLE_BUILDER,
    ROLE_EVALUATOR,
    ROLE_HUMAN,
    decide_run_role,
    ready_nodes,
)
from gemini_deep_research.core.state_machine import ControllerState


class TestRunRole(unittest.TestCase):
    def test_inflight_states_route_to_builder(self):
        for st in (
            ControllerState.INPUT,
            ControllerState.OPTIMIZE,
            ControllerState.SUBMIT,
            ControllerState.CONFIRM,
            ControllerState.MONITOR,
            ControllerState.RETRY,
        ):
            d = decide_run_role(st)
            self.assertEqual(d.role, ROLE_BUILDER, st)
            self.assertTrue(d.ready)

    def test_done_routes_to_evaluator(self):
        d = decide_run_role(ControllerState.DONE)
        self.assertEqual(d.role, ROLE_EVALUATOR)
        self.assertTrue(d.ready)

    def test_fail_routes_to_evaluator(self):
        self.assertEqual(decide_run_role(ControllerState.FAIL).role, ROLE_EVALUATOR)

    def test_blocker_overrides_to_human_not_ready(self):
        d = decide_run_role(ControllerState.MONITOR, blocker="waiting_human:reauth_required")
        self.assertEqual(d.role, ROLE_HUMAN)
        self.assertFalse(d.ready)

    def test_every_controller_state_mapped(self):
        for st in ControllerState:
            self.assertIsNotNone(decide_run_role(st).role)


class TestReadyNodes(unittest.TestCase):
    def _graph(self, nodes, results):
        d = {"nodes": nodes, "node_results": results}
        f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        json.dump(d, f)
        f.close()
        return f.name

    def test_root_node_ready_when_open(self):
        g = self._graph(
            [{"id": "A", "depends_on": []}, {"id": "B", "depends_on": ["A"]}],
            {"A": {"status": "assigned"}, "B": {"status": "pending"}},
        )
        self.assertEqual(ready_nodes(g), ["A"])  # B blocked by open A
        Path(g).unlink()

    def test_dependent_ready_after_dep_reviewing(self):
        g = self._graph(
            [{"id": "A", "depends_on": []}, {"id": "B", "depends_on": ["A"]}],
            {"A": {"status": "reviewing"}, "B": {"status": "pending"}},
        )
        self.assertEqual(ready_nodes(g), ["B"])  # A done(reviewing) -> B ready
        Path(g).unlink()

    def test_all_done_none_ready(self):
        g = self._graph(
            [{"id": "A", "depends_on": []}, {"id": "B", "depends_on": ["A"]}],
            {"A": {"status": "passed"}, "B": {"status": "reviewing"}},
        )
        self.assertEqual(ready_nodes(g), [])
        Path(g).unlink()

    def test_real_s03_graph_all_reviewing_none_ready(self):
        g = (
            "sprints/sprint-20260529-跑通-gemini-deep-research-我的具体要求是-1-"
            "从用户那里或者上游调用-上游算子那里获取问题输入-2-s03-core-runtime.task_graph.json"
        )
        if Path(g).exists():
            self.assertEqual(ready_nodes(g), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
