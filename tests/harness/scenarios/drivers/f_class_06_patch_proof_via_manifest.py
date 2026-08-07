#!/usr/bin/env python3
"""F-CLASS-06 gate_replay driver — patch proof discoverable via the manifest.

A patch sidecar with an odd (ff35c302-shaped) filename is invisible to the
legacy filename scan; the manifest's kind-keyed sidecar map finds it. Fault
(SOLAR_GATE_LEDGER=0) drops the manifest consult -> patch_discoverable False.
"""
import json
import os
from pathlib import Path

HARNESS_DIR = Path(os.environ["HARNESS_DIR"])
SPRINTS = HARNESS_DIR / "sprints"
SID = "f-class-06"

import artifact_manifest as am  # noqa: E402
import graph_node_dispatcher as gnd  # noqa: E402

weird_patch = SPRINTS / "S2-attempt2.PATCH.DIFF.txt"
weird_patch.parent.mkdir(parents=True, exist_ok=True)
weird_patch.write_text("--- a/x.py\n+++ b/x.py\n", encoding="utf-8")

am.write_manifest(
    SPRINTS, SID, {"id": "S2", "write_scope": []}, generation=1,
    roots={}, sidecars={"patch_diff": str(weird_patch)},
)

presence = gnd._proof_artifact_presence(SID, {"id": "S2"})
print(json.dumps({"patch_discoverable": bool(presence.get("patch_diff"))}))
