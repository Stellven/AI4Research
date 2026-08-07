from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest


AUDIT_ROOT = Path(__file__).resolve().parents[3]
CHECKOUT = AUDIT_ROOT / "tmp" / "codex-not-run-checkout"
GATE_DIR = CHECKOUT / "harness" / "evaluators" / "scientific"
PYTHON = CHECKOUT / ".venv" / "bin" / "python"

GATES = {
    "paper_gate": "research_paper.v1",
    "claims_gate": "research_claims.v1",
    "method_gate": "research_method.v1",
    "code_evidence_gate": "code_evidence_map.v1",
    "idea_gate": "idea_candidate.v1",
    "experiment_plan_gate": "experiment_plan.v1",
    "experiment_result_gate": "experiment_result.v1",
    "experiment_status_gate": "experiment_status.v1",
    "claim_verdict_gate": "claim_verdict.v1",
    "artifact_review_gate": "artifact_review.v1",
    "report_gate": "scientific_report.v1",
    "publication_gate": "publication_bundle.v1",
    "workflow_evolution_gate": "workflow_evolution.v1",
    "autosci_feature_parity_gate": "autosci_feature_parity.v1",
    "autosci_operator_smoke_gate": "autosci_operator_smoke.v1",
    "autosci_runtime_evidence_gate": "autosci_runtime_evidence.v1",
    "autosci_skill_run_gate": "autosci_skill_run.v1",
}


def run_gate(name: str, evidence: Path) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(CHECKOUT / "harness")
    return subprocess.run(
        [str(PYTHON), str(GATE_DIR / f"{name}.py"), str(evidence)],
        cwd=CHECKOUT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=30,
    )


@pytest.mark.parametrize("name,expected_schema", GATES.items(), ids=GATES)
def test_gate_cli_missing_evidence_is_typed_failure(name: str, expected_schema: str, tmp_path: Path) -> None:
    missing = tmp_path / "missing-evidence.json"
    proc = run_gate(name, missing)
    assert proc.returncode == 2, proc.stderr
    result = json.loads(proc.stdout)
    assert result["ok"] is False
    assert result["status"] == "failed"
    assert result["schema"] == expected_schema
    assert result["path"] == str(missing)
    assert result["reasons"]
    assert "FileNotFoundError" in " ".join(result["reasons"])


@pytest.mark.parametrize("name,expected_schema", GATES.items(), ids=GATES)
def test_gate_cli_malformed_evidence_is_typed_failure(name: str, expected_schema: str, tmp_path: Path) -> None:
    malformed = tmp_path / "malformed-evidence.json"
    malformed.write_text("{not-json", encoding="utf-8")
    proc = run_gate(name, malformed)
    assert proc.returncode == 2, proc.stderr
    result = json.loads(proc.stdout)
    assert result["ok"] is False
    assert result["status"] == "failed"
    assert result["schema"] == expected_schema
    assert result["path"] == str(malformed)
    assert result["reasons"]
    assert "JSONDecodeError" in " ".join(result["reasons"])
