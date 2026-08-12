from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

def test_p22_external_validity_holdout(repo_root: Path) -> None:
    fixture = repo_root / "tests/journeys/phase22/fixtures/significant/external_validity/multi_site_holdout.json"
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
        "1254aa136cabca6867d36a420337d5efbdd3f7e83b0e738c65c241e821d12c72",
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
    assert result["policy"]["preregistered_external_sites"] == ["hospital-lab-c", "university-lab-b"]
    assert result["claim_boundary"]["supported_on_preregistered_external_sites"] is True
    assert result["claim_boundary"]["supports_unobserved_sites"] is False
    assert result["claim_boundary"]["supports_universal_generalization"] is False
    assert all(item["evidence_artifact_sha256s"] and item["source_lineage_ids"] for item in result["site_results"])

    repo_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo_root, text=True).strip()
    evidence = {
        "schema": "phase22_significant_evidence.v1",
        "run_id": run_id,
        "repo_head": repo_head,
        "production_entrypoint": "harness.lib.research.external_validity.evaluate_external_holdout",
        "command": command,
        "exit_code": proc.returncode,
        "status": "PASS_WITH_KNOWN_LIMITATIONS",
        "assertion_count": 8,
        "result": result,
        "known_limitations": result["limitations"],
    }
    (run_dir / "journey-result.json").write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
