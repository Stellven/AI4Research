#!/usr/bin/env python3
"""F-CLASS-21 gate_replay driver — CONSULT HALF ONLY (round-4 G5).

This driver hand-builds the manifest with observed=[stray] because no live
producer of observed writes exists (node_verdict passes no observed=; operator
result.json has no artifact list; there is no workspace write-scan). It proves
the CONSULT: a manifest carrying ARTIFACT_ROOT_VIOLATION blocks
_evaluate_proof_obligations even though the declared obligation is satisfied.
It does NOT prove the dispatcher can detect a stray write — AC-R6.3 is not
enforced end-to-end in production (catalog row 'partial', pending_remainder
names the missing producer). Fault (SOLAR_GATE_LEDGER=0): the consult is off,
the contamination is invisible, and the gate passes.
"""
import json
import os
from pathlib import Path

HARNESS_DIR = Path(os.environ["HARNESS_DIR"])
SPRINTS = HARNESS_DIR / "sprints"
SID = "f-class-21"

import artifact_manifest as am  # noqa: E402
import graph_node_dispatcher as gnd  # noqa: E402

workspace = HARNESS_DIR / "workspace"
workspace.mkdir(parents=True, exist_ok=True)
SPRINTS.mkdir(parents=True, exist_ok=True)

# The node's legitimate obligation is satisfiable: a real handoff exists.
(SPRINTS / f"{SID}.S1-handoff.md").write_text("# handoff\n", encoding="utf-8")

# ...but the node also wrote into the repo/checkout root (outside every root).
stray = HARNESS_DIR / "repo-root-stray.md"
stray.write_text("contamination", encoding="utf-8")

am.write_manifest(
    SPRINTS, SID, {"id": "S1", "write_scope": []}, generation=1,
    roots={"canonical": str(workspace)},
    observed=[str(stray)],
)

node = {
    "id": "S1",
    "proof_obligations": [
        {"kind": "pass_condition", "requirement": "output_present", "field": "handoff_md"},
    ],
}
gate = gnd._evaluate_proof_obligations(SID, node)
reasons = {str(item.get("reason") or "") for item in gate.get("missing") or []}
print(json.dumps({
    "violation_blocked": (gate.get("ok") is False) and ("ARTIFACT_ROOT_VIOLATION" in reasons),
    "gate_ok": bool(gate.get("ok")),
}))
