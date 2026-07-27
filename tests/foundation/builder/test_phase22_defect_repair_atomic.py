from __future__ import annotations

import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
HARNESS_LIB = REPO / "harness" / "lib"
sys.path.insert(0, str(HARNESS_LIB))

import graph_scheduler  # noqa: E402


def test_atomic_defect_repair__external_blocker(monkeypatch, tmp_path: Path) -> None:
    graph = {
        "sprint_id": "phase22-defect-repair-external-blocker",
        "nodes": [
            {
                "id": "DR1",
                "status": "pending",
                "goal": "Repair a defect after upstream provider access is restored.",
                "logical_operator": "ImplementationWorker",
                "depends_on": ["external:sprint-provider-access-restored"],
                "estimated_cost": 1,
                "write_scope": ["workspace/defect-repair.patch"],
                "acceptance": ["external blocker is resolved before defect repair dispatch"],
                "required_capabilities": ["implementation"],
            }
        ],
    }
    monkeypatch.setattr(graph_scheduler, "SPRINTS_DIR", tmp_path)

    validation = graph_scheduler.validate_graph(graph)
    blockers = graph_scheduler.blocked_external_prerequisites(graph)

    assert validation["ok"] is True
    assert len(blockers) == 1
    assert blockers[0]["node_id"] == "DR1"
    assert blockers[0]["requirement"] == "external:sprint-provider-access-restored"
    assert blockers[0]["sprint_id"] == "sprint-provider-access-restored"
    assert blockers[0]["reason"] == "missing_status"
    assert blockers[0]["source"] == "depends_on"
    assert graph_scheduler.ready_nodes(graph) == []
