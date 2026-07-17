#!/usr/bin/env python3
"""F-CLASS-29 gate_replay driver — gates consume verdict CONTENT, not node status.

The LDES shape: the critic node executes successfully (status passed) but its
verdict record says block. The gate must block on the verdict content. Fault
(SOLAR_GATE_LEDGER=0): the ledger consult is off and the gate passes on node
completion alone — the class's original failure.
"""
import json
import os
from pathlib import Path

HARNESS_DIR = Path(os.environ["HARNESS_DIR"])
SPRINTS = HARNESS_DIR / "sprints"
SID = "f-class-29"

import gate_ledger as gl  # noqa: E402
import graph_scheduler as gs  # noqa: E402

SPRINTS.mkdir(parents=True, exist_ok=True)
graph = {
    "sprint_id": SID,
    "workflow_contract_id": "research.deepdive.rsi_demo",
    "nodes": [{"id": "C1", "status": "reviewing", "depends_on": [], "gate": "G1"}],
    "node_results": {},
    "gate_results": {},
}

# The critic's verdict record: block (append_record is flag-independent, so the
# record exists in BOTH worlds — the red run shows the legacy gate IGNORES it).
gl.append_record(SPRINTS, SID, node_id="C1", kind="eval_verdict",
                 author={"type": "evaluator", "operator_id": "critic-1"},
                 verdict="block", verdict_kind="content")

gs.mark_node_result(graph, "C1", "passed")

gate = graph["gate_results"].get("G1") or {}
print(json.dumps({
    "gate_blocked": str(gate.get("status") or "") == "blocked",
    "gate_reason": str(gate.get("reason") or ""),
    "node_status": gs.node_status(graph, "C1"),
}))
