from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

def test_p22_external_validity_holdout(repo_root: Path) -> None:
    fixture = repo_root / "tests/journeys/phase22/fixtures/significant/external_validity/multi_site_holdout.json"
    trust_registry = repo_root / "tests/journeys/phase22/fixtures/significant/trust_registry.json"
    trust_registry_sha256 = hashlib.sha256(trust_registry.read_bytes()).hexdigest()
    run_id = "p22-external-validity-holdout"
    run_dir = repo_root / "outputs/phase22-real-journeys" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    result_path = run_dir / "external-validity-result.json"
    command = [
        sys.executable,
        "-m",
        "harness.lib.research.external_validity",
        str(fixture),
        "--trusted-plan-sha256",
        "8c977513343d5e6ed9213a743abcdf7f8aa476fde54660d5308a621509337ae9",
        "--trust-registry",
        str(trust_registry),
        "--trust-registry-sha256",
        trust_registry_sha256,
        "--output",
        str(result_path),
    ]
    proc = subprocess.run(command, cwd=repo_root, text=True, capture_output=True, check=False)
    assert proc.returncode == 0, proc.stderr
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["status"] == "accepted", result["errors"]
    assert result["manifest"]["sha256"]
    assert result["external_plan"]["sha256"]
    assert len(result["site_results"]) == 2
    assert result["policy"]["preregistered_external_sites"] == ["fixture-hospital-lab-c", "fixture-university-lab-b"]
    assert result["claim_boundary"]["supported_on_preregistered_external_sites"] is True
    assert result["claim_boundary"]["supports_unobserved_sites"] is False
    assert result["claim_boundary"]["supports_universal_generalization"] is False
    assert all(item["evidence_artifact_sha256s"] and item["source_lineage_ids"] for item in result["site_results"])
    assert result["external_plan_trust"]["status"] == "accepted"
    assert result["site_identity_contract"]["status"] == "accepted"
    assert result["site_identity_contract"]["accepted_count"] == 3

    attack_registry = run_dir / "missing-holdout-site-registry.json"
    attack_payload = json.loads(trust_registry.read_text(encoding="utf-8"))
    attack_payload["site_identities"] = [
        item
        for item in attack_payload["site_identities"]
        if item.get("site_id") != "fixture-hospital-lab-c"
    ]
    attack_registry.write_text(json.dumps(attack_payload, indent=2) + "\n", encoding="utf-8")
    attack_registry_sha256 = hashlib.sha256(attack_registry.read_bytes()).hexdigest()
    attack_path = run_dir / "missing-site-identity-rejection.json"
    attack_command = [
        sys.executable,
        "-m",
        "harness.lib.research.external_validity",
        str(fixture),
        "--trusted-plan-sha256",
        "8c977513343d5e6ed9213a743abcdf7f8aa476fde54660d5308a621509337ae9",
        "--trust-registry",
        str(attack_registry),
        "--trust-registry-sha256",
        attack_registry_sha256,
        "--output",
        str(attack_path),
    ]
    attack_proc = subprocess.run(attack_command, cwd=repo_root, text=True, capture_output=True, check=False)
    attack_result = json.loads(attack_path.read_text(encoding="utf-8"))
    assert attack_proc.returncode == 2
    assert attack_result["status"] == "rejected"
    assert "trust_registry_invalid:trust_registry_sha256_not_policy_approved" in attack_result["errors"]

    repo_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo_root, text=True).strip()
    evidence = {
        "schema": "phase22_significant_evidence.v1",
        "run_id": run_id,
        "repo_head": repo_head,
        "production_entrypoint": "harness.lib.research.external_validity.evaluate_external_holdout",
        "command": command,
        "exit_code": proc.returncode,
        "negative_command": attack_command,
        "negative_exit_code": attack_proc.returncode,
        "status": "PASS_WITH_KNOWN_LIMITATIONS",
        "assertion_count": 12,
        "result": result,
        "negative_result": attack_result,
        "known_limitations": result["limitations"],
    }
    (run_dir / "journey-result.json").write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
