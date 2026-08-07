#!/usr/bin/env python3
"""F-CLASS-13 gate_replay driver — stale-generation eval archived WITH a record.

A pre-repair PASS eval (generation 0) reaches a node on repair attempt 1. The
archive machinery holds it in both worlds (714eb781); the Lane 3 retirement is
the durable, non-consumable ledger record proving WHY it was held. Fault
(SOLAR_GATE_LEDGER=0): the evidence trail vanishes -> archived_record_present
False (the class's original invisibility).
"""
import json
import os
from pathlib import Path

HARNESS_DIR = Path(os.environ["HARNESS_DIR"])
SPRINTS = HARNESS_DIR / "sprints"
SID = "f-class-13"

import gate_ledger as gl  # noqa: E402
import graph_scheduler as gs  # noqa: E402
import graph_node_dispatcher as gnd  # noqa: E402

SPRINTS.mkdir(parents=True, exist_ok=True)
eval_json = SPRINTS / f"{SID}.S1-eval.json"
eval_json.write_text(json.dumps({
    "verdict": "PASS", "eval_generation": 0, "summary": "stale pre-repair pass",
}), encoding="utf-8")

graph_path = SPRINTS / f"{SID}.task_graph.json"
graph_path.write_text(json.dumps({
    "sprint_id": SID,
    "workflow_contract_id": "research.deepdive.rsi_demo",
    "nodes": [{
        "id": "S1", "status": "reviewing", "depends_on": [],
        "eval_json": str(eval_json),
        "repair_attempts": 1,
        "repair_context": {"attempt": 1, "created_at": "2026-07-07T00:00:00Z"},
    }],
    "node_results": {},
    "gate_results": {},
}), encoding="utf-8")

graph = gs.load_graph(str(graph_path))
gnd._reconcile_existing_dispatches(graph, str(graph_path))

node_flipped = gs.node_status(graph, "S1") == "passed"
records = [
    row for row in gl.read_records(SPRINTS, SID, node_id="S1", kind="eval_verdict")
    if row.get("archived") and not gl.is_gate_consumable(row, current_generation=1)
]
print(json.dumps({
    "node_flipped": node_flipped,
    "archived_record_present": bool(records),
}))
