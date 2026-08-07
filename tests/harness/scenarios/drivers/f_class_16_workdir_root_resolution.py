#!/usr/bin/env python3
"""F-CLASS-16 gate_replay driver — the v9 workdir/workspace divergence.

The artifact is declared relative to the canonical workspace but actually
written under the workdir alias root. The manifest resolves it (canonical
probe first, then aliases) and the proof-presence consult reports it present;
publish produces the canonical copy. Fault (SOLAR_GATE_LEDGER=0): the consult
is off and the artifact is lost to discovery -> output_present False.
"""
import json
import os
from pathlib import Path

HARNESS_DIR = Path(os.environ["HARNESS_DIR"])
SPRINTS = HARNESS_DIR / "sprints"
SID = "f-class-16"
REL = "rsi-deep-research-report/sources.json"

import artifact_manifest as am  # noqa: E402
import graph_node_dispatcher as gnd  # noqa: E402

workspace = HARNESS_DIR / "workspace"
workdir = HARNESS_DIR / "workdir"
workspace.mkdir(parents=True, exist_ok=True)
stray = workdir / REL
stray.parent.mkdir(parents=True, exist_ok=True)
stray.write_text('{"sources": []}', encoding="utf-8")

roots = {"canonical": str(workspace), "workdir": str(workdir)}
manifest = am.write_manifest(
    SPRINTS, SID, {"id": "S2", "write_scope": [REL]}, generation=1, roots=roots,
)
am.publish_canonical(manifest, roots["canonical"])

presence = gnd._proof_artifact_presence(SID, {"id": "S2"})
print(json.dumps({
    "output_present": bool(presence.get(f"output:{REL}")),
    "resolved_root": manifest["rows"][0]["resolved_root"],
    "canonical_copy": (workspace / REL).exists(),
}))
