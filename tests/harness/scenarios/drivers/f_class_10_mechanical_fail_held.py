#!/usr/bin/env python3
"""F-CLASS-10 gate_replay driver — mechanical FAIL cannot flip a passed node.

Two shapes at the node_verdict seam (round-4 G1 added the second):

* driver shape: recorded passed, NO handoff, no eval — node_status()=="passed".
* v5 shape:     recorded passed, handoff PRESENT, no eval, repair budget
  exhausted — node_status()=="reviewing" via the fail-closed downgrade; this is
  the state that actually PRODUCES research_eval_json_missing, and pre-fix it
  bypassed the hold and terminally failed the node.

Fault (SOLAR_GATE_LEDGER=0): legacy flips both — the v5 shape all the way to
terminal "failed".
"""
import json
import os
from pathlib import Path

HARNESS_DIR = Path(os.environ["HARNESS_DIR"])
SPRINTS = HARNESS_DIR / "sprints"

import graph_node_dispatcher as gnd  # noqa: E402

SPRINTS.mkdir(parents=True, exist_ok=True)


def run_case(sid: str, with_handoff: bool, repair_attempts=None):
    node = {"id": "S1", "status": "passed", "depends_on": [],
            "updated_at": "2026-07-07T00:00:00Z"}
    if repair_attempts is not None:
        node["repair_attempts"] = repair_attempts
    graph_path = SPRINTS / f"{sid}.task_graph.json"
    graph_path.write_text(json.dumps({
        "sprint_id": sid,
        "workflow_contract_id": "research.deepdive.rsi_demo",
        "nodes": [node],
        "node_results": {"S1": {"status": "passed", "updated_at": "2026-07-07T00:00:00Z"}},
        "gate_results": {},
    }), encoding="utf-8")
    if with_handoff:
        (SPRINTS / f"{sid}.S1-handoff.md").write_text("# handoff\n", encoding="utf-8")
    result = gnd.node_verdict(str(graph_path), "S1", "fail",
                              reason="research_eval_json_missing", dry_run=True)
    reloaded = json.loads(graph_path.read_text(encoding="utf-8"))
    return reloaded["nodes"][0]["status"], str(result.get("reason") or "")


final_status, held_reason = run_case("f-class-10", with_handoff=False)
v5_final_status, v5_held_reason = run_case("f-class-10-v5", with_handoff=True,
                                           repair_attempts=1)
print(json.dumps({
    "final_status": final_status,
    "held_reason": held_reason,
    "v5_final_status": v5_final_status,
    "v5_held_reason": v5_held_reason,
}))
