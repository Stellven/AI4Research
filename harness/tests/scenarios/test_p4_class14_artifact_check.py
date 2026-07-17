#!/usr/bin/env python3
"""P4 class-14 seam — `live_codex_epic_status.py artifact-check --contract`
must validate a finished contracted sprint end-to-end (catalog class 14:
"Wrapper epic observation", required seam: reads contract terminal states).

Found while proving the seam against the REAL P3 run-5 PASS fixture: the
checker loads the contract, resolves roots and artifacts correctly, then
fails its own test-command step two ways:
1. It runs the contract's validator_command inside a COPIED workspace with
   shell=True — but the v1.3 command (`python3 scripts/validate_...
   --workspace sprints/<sid>/workdir`) is written for the GATE EXECUTOR's
   cwd=HARNESS_DIR convention: in the copy neither the script nor the
   workdir path exists (python exit 2, "can't open file").
2. The artifact overlay places files at the contract's BARE artifact names
   (report.html at the copy root) while the validator's ROOT constant
   expects rsi-deep-research-report/<file> — so even a runnable command
   would fail ARTIFACT_MISSING.

Fix (contract mode only; explicit --test-command callers unchanged):
- overlay reconstructs the canonical layout in the copy: each artifact at
  <root_basename>/<artifact_path>;
- the contract-derived command is rewritten for copy execution: script path
  resolved absolute against the harness (harness/scripts first), any
  --workspace value and leftover <resolved_root> replaced with `.` (the
  copy root — the validator chdir's there, a no-op).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_HARNESS = Path(__file__).resolve().parents[2]
_HARNESS_LIB = str(_HARNESS / "lib")
if _HARNESS_LIB not in sys.path:
    sys.path.insert(0, _HARNESS_LIB)

import workflow_contract as wc  # noqa: E402

REPO = _HARNESS.parent
TOOL = REPO / "scripts" / "live_codex_epic_status.py"
WORKFLOWS_DIR = _HARNESS / "config" / "workflows"
SID = "p4-class14-fixture"


def _valid_artifacts(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    sources = [{"id": f"s{i}", "title": f"Source {i}", "citation_hint": f"Cite {i}"} for i in range(6)]
    claims = [{"claim_id": f"c{i}", "source_id": f"s{i % 6}", "claim_text": f"Claim text {i} [s{i % 6}]"} for i in range(12)]
    (root / "sources.json").write_text(json.dumps(sources), encoding="utf-8")
    (root / "claims.json").write_text(json.dumps(claims), encoding="utf-8")
    (root / "contradiction-matrix.json").write_text(json.dumps([{"claims": ["c1", "c2"], "kind": "scope"}]), encoding="utf-8")
    (root / "scope-contract.json").write_text(json.dumps({"question": "bounded rsi"}), encoding="utf-8")
    md = "# Bounded RSI report\n\n" + "\n".join(f"Finding {i} grounded in [s{i % 6}]." for i in range(30))
    (root / "report.md").write_text(md, encoding="utf-8")
    html = "<html><body>" + "".join(f"<p>Finding {i} grounded in [s{i % 6}].</p>" for i in range(40)) + "</body></html>"
    (root / "report.html").write_text(html, encoding="utf-8")
    (root / "evaluation-checklist.md").write_text(
        "# Checklist\n- D1 pass\n- D2 pass\n- D3 pass\n- D4 pass\n- D5 pass\n- D6 pass\n", encoding="utf-8")


@pytest.fixture()
def finished_sprint(tmp_path):
    harness = tmp_path / "harness"
    sprints = harness / "sprints"
    sprints.mkdir(parents=True)
    (harness / "config").mkdir()
    import shutil
    shutil.copytree(WORKFLOWS_DIR, harness / "config" / "workflows")
    shutil.copytree(_HARNESS / "scripts", harness / "scripts")
    contract = wc.find_contract("research.deepdive.rsi_demo", WORKFLOWS_DIR)
    graph = wc.instantiate(contract, {"sprint_id": SID, "sid": SID})
    for node in graph["nodes"]:
        node["status"] = "passed"
    (sprints / f"{SID}.task_graph.json").write_text(json.dumps(graph), encoding="utf-8")
    (sprints / f"{SID}.status.json").write_text(json.dumps({
        "sprint_id": SID, "status": "passed", "stage": "completed",
    }), encoding="utf-8")
    # the checker refuses executed work without route evidence (correct);
    # real runs carry this sidecar (shape from the P3 run-5 PASS bundle)
    (sprints / f"{SID}.route-proof.json").write_text(json.dumps({
        "ok": True, "sprint_id": SID, "selected_runtime": "codex",
        "allowed_providers": ["openai"], "enforced": True, "violations": [],
        "stage_count": 6,
        "stages": [
            {"task_id": f"pm-{SID}-D{i}", "node_id": f"D{i}", "provider": "openai",
             "submitted": True, "completed": True}
            for i in range(1, 7)
        ],
    }), encoding="utf-8")
    _valid_artifacts(sprints / SID / "workdir" / "rsi-deep-research-report")
    (tmp_path / "evidence").mkdir()
    (tmp_path / "workspace").mkdir()
    return tmp_path, harness


def _run_check(tmp_path, harness):
    proc = subprocess.run(
        [sys.executable, str(TOOL), "artifact-check",
         "--harness-dir", str(harness),
         "--id", SID,
         "--evidence-dir", str(tmp_path / "evidence"),
         "--workspace", str(tmp_path / "workspace"),
         "--contract", str(harness / "config" / "workflows" / "research.deepdive.rsi_demo.workflow.json"),
         "--contract-substitution", f"sid={SID}",
         "--contract-substitution", f"sprint_id={SID}",
         "--contract-substitution", f"resolved_root=sprints/{SID}/workdir"],
        capture_output=True, text=True, timeout=300,
    )
    return json.loads(proc.stdout)


def test_contract_artifact_check_validates_a_finished_contracted_sprint(finished_sprint):
    tmp_path, harness = finished_sprint
    # the stability gate needs the artifact signature unchanged across >=2
    # polls — exactly how the live wrapper drives this checker
    _run_check(tmp_path, harness)
    result = _run_check(tmp_path, harness)
    test_result = result.get("test_result") or {}
    assert test_result.get("ok"), (
        "contract-mode test command failed in the workspace copy: "
        f"{test_result.get('command')!r} rc={test_result.get('returncode')} "
        f"stderr={str(test_result.get('stderr'))[:200]}"
    )
    assert result.get("ok"), result.get("blocking_failures")


def test_contract_artifact_check_still_fails_on_missing_artifacts(finished_sprint):
    tmp_path, harness = finished_sprint
    root = harness / "sprints" / SID / "workdir" / "rsi-deep-research-report"
    (root / "claims.json").unlink()
    _run_check(tmp_path, harness)
    result = _run_check(tmp_path, harness)
    assert not result.get("ok"), "checker must fail when a required artifact is missing"
