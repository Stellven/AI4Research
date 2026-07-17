#!/usr/bin/env python3
"""F-CLASS-18 gate_replay driver — route truth at the operatord seam.

operator_runtime.write_result emits a completed route record carrying the
actually-routed provider/model/operator/backend/exit_code — route facts survive
independent of any node/dashboard claim. Fault (SOLAR_GATE_LEDGER=0): no route
record -> route proof impossible (the class's original lie surface).
"""
import json
import os
from pathlib import Path

HARNESS_DIR = Path(os.environ["HARNESS_DIR"])
SPRINTS = HARNESS_DIR / "sprints"
SID = "f-class-18"

import gate_ledger as gl  # noqa: E402
import operator_runtime as opr  # noqa: E402

opr.write_result(
    operator_id="fake-builder",
    task_id="T-route-1",
    sprint_id=SID,
    node_id="S1",
    status="succeeded",
    exit_code=0,
    started_at="2026-07-07T00:00:00Z",
    finished_at="2026-07-07T00:01:00Z",
    log_tail="done",
    model_route={"effective_provider": "anthropic", "effective_model": "fake-local"},
)

rows = gl.read_records(SPRINTS, SID, kind="route_record")
route = rows[-1]["route"] if rows else {}
print(json.dumps({
    "route_records": len(rows),
    "route_provider": str(route.get("provider") or ""),
    "route_exit_code": route.get("exit_code"),
}))
