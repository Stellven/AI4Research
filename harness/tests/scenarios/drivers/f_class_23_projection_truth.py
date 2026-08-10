#!/usr/bin/env python3
"""F-CLASS-23 gate_replay driver — projection truth survives an untruthful writer.

The node legitimately failed (recorded). An un-audited writer then edits the
graph dict directly to "passed" — the dashboard-shaped lie. On the contracted
path the consumer truth source is the ledger projection, which still says
failed (terminal absorbing; the lie has no record). Fault (SOLAR_GATE_LEDGER=0):
the only truth source is the lying node status -> truth_holds False.
"""
import json
import os
from pathlib import Path

HARNESS_DIR = Path(os.environ["HARNESS_DIR"])
SPRINTS = HARNESS_DIR / "sprints"
SID = "f-class-23"

import gate_ledger as gl  # noqa: E402
import graph_scheduler as gs  # noqa: E402

SPRINTS.mkdir(parents=True, exist_ok=True)
graph = {
    "sprint_id": SID,
    "workflow_contract_id": "research.deepdive.rsi_demo",
    "nodes": [{"id": "S1", "status": "reviewing", "depends_on": []}],
    "node_results": {},
    "gate_results": {},
}

gs.mark_node_result(graph, "S1", "failed", note="evaluator FAIL")

# The lie: a direct dict write outside the audited writer surface.
graph["nodes"][0]["status"] = "passed"
graph["node_results"]["S1"]["status"] = "passed"

if gl.enabled():
    truth = gl.project_node_status(SPRINTS, SID, "S1")
else:
    truth = gs.node_status(graph, "S1")

print(json.dumps({
    "truth_holds": truth == "failed",
    "reported_status": truth,
}))
