from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[4]
TOOL = REPO / "tools" / "approval_runtime_proof.py"
ROUTE_CONFIG = REPO / "harness" / "plugins" / "autosci" / "config" / "feature_parity_routes.v1.json"


def run_tool(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["HARNESS_DIR"] = str(tmp_path)
    return subprocess.run(
        [sys.executable, str(TOOL), *args],
        cwd=REPO,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def payload(proc: subprocess.CompletedProcess[str]) -> dict:
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return json.loads(proc.stdout)


def write_contract(tmp_path: Path, *, missing_after: bool = False) -> Path:
    root = tmp_path / "artifacts/runtime/exp-run"
    root.mkdir(parents=True)
    allowlist = root / "allowlist.json"
    runtime = root / "runtime.json"
    before = root / "before.json"
    after = root / "after.json"
    allowlist.write_text('{"approved": true}\n', encoding="utf-8")
    runtime.write_text(
        json.dumps(
            {
                "schema": "autosci_runtime_evidence.v1",
                "status": "completed",
                "outputs": {"runtime": {"exit_code": 0, "evidence_ids": ["runtime:exp-run"]}},
            }
        ),
        encoding="utf-8",
    )
    before.write_text('{"state": "before"}\n', encoding="utf-8")
    if not missing_after:
        after.write_text('{"state": "after"}\n', encoding="utf-8")
    contract = root / "approval-contract.json"
    contract.write_text(
        json.dumps(
            {
                "schema": "autosci_approval_contract.v1",
                "action": "run_experiment",
                "side_effects": ["local_execution"],
                "approval_ref": "approval-exp-run",
                "approval_state": "verified",
                "approved": True,
                "allowlist_ready": True,
                "before_ready": True,
                "ready_for_execution": True,
                "runtime_ready": True,
                "after_ready": True,
                "execution_verified": True,
                "allowlist_evidence": [{"path": "artifacts/runtime/exp-run/allowlist.json"}],
                "runtime_evidence": [{"path": "artifacts/runtime/exp-run/runtime.json"}],
                "before_artifacts": [{"path": "artifacts/runtime/exp-run/before.json"}],
                "after_artifacts": [{"path": "artifacts/runtime/exp-run/after.json"}],
                "missing": [],
            }
        ),
        encoding="utf-8",
    )
    return contract


def test_verified_approval_contract_writes_runtime_proof_manifest(tmp_path: Path) -> None:
    contract = write_contract(tmp_path)
    proof = tmp_path / "artifacts/runtime/exp-run/approval.proof.json"
    result = payload(
        run_tool(
            tmp_path,
            "from-contract",
            str(contract),
            "--native-skill",
            "exp-run",
            "--runtime-proof-out",
            str(proof),
        )
    )
    assert result["status"] == "completed"
    assert result["runtime_proof_manifest_status"] == "written"
    manifest = json.loads(proof.read_text(encoding="utf-8"))
    proof_entry = manifest["proofs"][0]
    assert proof_entry["native_skill"] == "exp-run"
    assert proof_entry["categories"] == [
        "approval_boundary_evidence",
        "side_effect_execution_evidence",
        "external_runtime_evidence",
    ]
    assert proof_entry["collection_mode"] == "approved_side_effect"
    assert proof_entry["production_ready"] is True
    assert proof_entry["provenance"]["source"] == "approval_contract"
    assert proof_entry["provenance"]["artifact_kind"] == "approval_runtime_contract"
    assert proof_entry["evidence_refs"] == [
        "artifacts/runtime/exp-run/approval-contract.json",
        "artifacts/runtime/exp-run/allowlist.json",
        "artifacts/runtime/exp-run/runtime.json",
        "artifacts/runtime/exp-run/before.json",
        "artifacts/runtime/exp-run/after.json",
    ]


def test_unverified_approval_contract_does_not_write_runtime_proof(tmp_path: Path) -> None:
    contract = write_contract(tmp_path, missing_after=True)
    proof = tmp_path / "artifacts/runtime/exp-run/approval.proof.json"
    result = payload(
        run_tool(
            tmp_path,
            "from-contract",
            str(contract),
            "--native-skill",
            "exp-run",
            "--runtime-proof-out",
            str(proof),
        )
    )
    assert result["status"] == "inconclusive"
    assert result["runtime_proof_manifest_status"] == "not_written"
    assert any("after.json" in error for error in result["errors"])
    assert not proof.exists()


def test_approval_runtime_proof_tool_is_exposed_for_approval_routes() -> None:
    config = json.loads(ROUTE_CONFIG.read_text(encoding="utf-8"))
    routes = {item["native_skill"]: item for item in config["routes"]}
    expected = {
        "daily-arxiv",
        "edit",
        "exp-eval",
        "exp-pilot-eval",
        "exp-pilot-run",
        "exp-run",
        "init",
        "paper-compile",
        "poster",
        "prefill",
        "refine",
        "research",
        "reset",
        "setup",
        "visualize",
    }
    for skill in expected:
        assert "tools/approval_runtime_proof.py from-contract" in routes[skill]["primary_tools"]
