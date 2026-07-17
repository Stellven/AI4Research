#!/usr/bin/env python3
"""F-CLASS-09 gate_replay driver — a recorded auto-resolution decision is sticky.

The node was auto-resolved to passed (decision recorded through the audited
writer). A stale late write then lands directly in node_results ("failed",
newer timestamp) and the doctor's drift repair would copy it over the inline
pass — the historical clobber. On the contracted path the doctor is
neutralized (would-be write becomes a non-applied record) and the ledger
projection still reports the recorded decision. Fault (SOLAR_GATE_LEDGER=0):
no decision record exists, the doctor applies the drift repair, and the
decision is gone -> decision_preserved False.
"""
import json
import os
from pathlib import Path

HARNESS_DIR = Path(os.environ["HARNESS_DIR"])
SPRINTS = HARNESS_DIR / "sprints"
SID = "f-class-09"

import gate_ledger as gl  # noqa: E402
import graph_scheduler as gs  # noqa: E402

SPRINTS.mkdir(parents=True, exist_ok=True)
graph = {
    "sprint_id": SID,
    "workflow_contract_id": "research.deepdive.rsi_demo",
    "nodes": [{"id": "S1", "status": "needs_human_review", "depends_on": []}],
    "node_results": {},
    "gate_results": {},
}

# The auto-resolution: through the audited writer (records when the ledger is on).
gs.mark_node_result(graph, "S1", "passed")
if gl.enabled():
    gl.append_record(SPRINTS, SID, node_id="S1", kind="auto_resolution",
                     author={"type": "policy"}, verdict="resolved_passed")

# The clobber: a stale late write lands directly in node_results with a NEWER
# timestamp (never through a writer, so it has no record).
graph["nodes"][0]["updated_at"] = "2026-07-07T00:00:00Z"
graph["node_results"]["S1"] = {"status": "failed", "updated_at": "2026-07-07T01:00:00Z"}

report = gs.doctor_graph(graph, repair=True)

if gl.enabled():
    truth = gl.project_node_status(SPRINTS, SID, "S1")
else:
    truth = gs.node_status(graph, "S1")

print(json.dumps({
    "decision_preserved": truth == "passed",
    "doctor_suppressed": bool(report.get("suppressed")),
    "reported_status": truth,
}))
