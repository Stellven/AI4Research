#!/usr/bin/env python3
"""F-CLASS-30 gate_replay driver — verdict provenance is recorded and non-consumable.

A self-graded PASS (the executing agent wrote its own eval.json; no independent
evaluator report) is rejected by the legacy guard in both worlds — the Lane 3
retirement is the PROVENANCE: a gate_check record naming the self-graded block
plus the fail-closed consumability rule. Fault (SOLAR_GATE_LEDGER=0): the
rejection leaves no evidence trail -> provenance_recorded False.
"""
import json
import os
from pathlib import Path

HARNESS_DIR = Path(os.environ["HARNESS_DIR"])
SPRINTS = HARNESS_DIR / "sprints"
SID = "f-class-30"

import gate_ledger as gl  # noqa: E402
import graph_node_dispatcher as gnd  # noqa: E402

SPRINTS.mkdir(parents=True, exist_ok=True)
# Executor-authored world: a real handoff + an eval.json with NO independent
# evaluator report (no eval.md, no eval-dispatch sidecar) => self-graded.
(SPRINTS / f"{SID}.S1-handoff.md").write_text("# handoff\ndone\n", encoding="utf-8")
(SPRINTS / f"{SID}.S1-eval.json").write_text(json.dumps({
    "verdict": "PASS", "generation_mode": "manual_node_eval", "summary": "I grade myself a pass",
}), encoding="utf-8")

graph_path = SPRINTS / f"{SID}.task_graph.json"
graph_path.write_text(json.dumps({
    "sprint_id": SID,
    "workflow_contract_id": "research.deepdive.rsi_demo",
    "nodes": [{"id": "S1", "status": "reviewing", "depends_on": [],
               "artifacts": {"handoff_md": str(SPRINTS / f"{SID}.S1-handoff.md")}}],
    "node_results": {},
    "gate_results": {},
}), encoding="utf-8")

result = gnd.node_verdict(str(graph_path), "S1", "pass", dry_run=True)

blocked = str(result.get("reason") or "") == "self_graded_eval_requires_independent_report"
provenance = [
    row for row in gl.read_records(SPRINTS, SID, node_id="S1", kind="gate_check")
    if row.get("self_graded")
]
backfill_rec = {"kind": "eval_verdict", "author": {"type": "evaluator"},
                "verdict": "PASS", "generation_mode": "repair_backfill"}
print(json.dumps({
    "self_graded_blocked": blocked,
    "provenance_recorded": bool(provenance),
    "backfill_consumable": gl.is_gate_consumable(backfill_rec),
}))
