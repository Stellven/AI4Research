from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import jsonschema

from harness.lib.research.decision_artifact import DecisionArtifactError, construct_decision_artifact


REPO_ROOT = Path(__file__).resolve().parents[3]
TOOL = REPO_ROOT / "harness" / "tools" / "decision_artifact.py"
SCHEMA = REPO_ROOT / "harness" / "schemas" / "evidence" / "decision_artifact.v1.schema.json"


def _request(tmp_path: Path, *, observed: str = "supported") -> tuple[dict, Path]:
    evidence = tmp_path / "claim-verdict.json"
    evidence.write_text(
        json.dumps({"outputs": {"verdicts": [{"claim_id": "claim-1", "verdict": observed}]}}),
        encoding="utf-8",
    )
    request = {
        "schema": "decision_request.v1",
        "decision_id": "decision-1",
        "title": "Choose a verification route",
        "problem": "Select a route without overstating local evidence.",
        "alternatives": [
            {"alternative_id": "bounded", "title": "Bounded rollout", "description": "Use the verified local route."},
            {"alternative_id": "global", "title": "Global rollout", "description": "Deploy without further review."},
        ],
        "criteria": [
            {"criterion_id": "evidence", "name": "Evidence support", "weight": 0.7},
            {"criterion_id": "risk", "name": "Residual risk", "weight": 0.3},
        ],
        "evidence": [
            {
                "evidence_id": "claim-1-verdict",
                "source_path": str(evidence),
                "support_pointer": "/outputs/verdicts/0/verdict",
                "supported_values": ["supported"],
                "summary": "The local claim verifier marked the bounded claim supported.",
            }
        ],
        "assessments": [
            {
                "alternative_id": "bounded",
                "criterion_id": "evidence",
                "score": 5,
                "rationale": "The option stays within the verified scope.",
                "evidence_ids": ["claim-1-verdict"],
            },
            {
                "alternative_id": "bounded",
                "criterion_id": "risk",
                "score": 3,
                "rationale": "Independent review is still outstanding.",
                "evidence_ids": ["claim-1-verdict"],
            },
            {
                "alternative_id": "global",
                "criterion_id": "evidence",
                "score": 0,
                "rationale": "No evidence supports a global claim.",
                "evidence_ids": ["claim-1-verdict"],
            },
        ],
        "risks": [
            {
                "risk_id": "scope-drift",
                "description": "The local result may be generalized beyond its measured scope.",
                "mitigation": "Keep the rollout bounded and request independent review.",
                "evidence_ids": ["claim-1-verdict"],
            }
        ],
        "recommendation": {
            "alternative_id": "bounded",
            "rationale": "The bounded route is the only option supported by current evidence.",
            "criterion_ids": ["evidence", "risk"],
            "evidence_ids": ["claim-1-verdict"],
        },
        "limitations": ["One local dataset does not establish external validity."],
        "unresolved_review_items": ["Independent reviewer must assess external validity."],
    }
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(request), encoding="utf-8")
    return request, request_path


def test_constructor_emits_schema_valid_review_required_artifact(tmp_path: Path) -> None:
    request, request_path = _request(tmp_path)

    artifact = construct_decision_artifact(request, request_path=request_path, source_root=tmp_path)

    jsonschema.Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8"))).validate(artifact)
    assert artifact["recommendation"]["criterion_ids"] == ["evidence", "risk"]
    assert artifact["recommendation"]["evidence_ids"] == ["claim-1-verdict"]
    assert artifact["evidence_links"][0]["observed_support"] == "supported"
    assert artifact["review"]["status"] == "pending"
    assert artifact["approval"] == {
        "status": "not_requested",
        "approved_by": None,
        "approval_evidence": [],
    }


def test_cli_executes_constructor_and_writes_artifact(tmp_path: Path) -> None:
    _, request_path = _request(tmp_path)
    output = tmp_path / "decision.json"

    proc = subprocess.run(
        [sys.executable, str(TOOL), "--input", str(request_path), "--output", str(output), "--source-root", str(tmp_path)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    assert json.loads(output.read_text(encoding="utf-8"))["schema"] == "decision_artifact.v1"
    assert json.loads(proc.stdout)["status"] == "completed"


def test_unsupported_evidence_fails_closed_without_artifact(tmp_path: Path) -> None:
    _, request_path = _request(tmp_path, observed="inconclusive")
    output = tmp_path / "decision.json"

    proc = subprocess.run(
        [sys.executable, str(TOOL), "--input", str(request_path), "--output", str(output), "--source-root", str(tmp_path)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 2
    assert not output.exists()
    assert "not supportive" in json.loads(proc.stderr)["error"]


def test_unknown_evidence_reference_and_claimed_approval_are_rejected(tmp_path: Path) -> None:
    request, request_path = _request(tmp_path)
    unknown = copy.deepcopy(request)
    unknown["recommendation"]["evidence_ids"] = ["missing-evidence"]
    try:
        construct_decision_artifact(unknown, request_path=request_path, source_root=tmp_path)
    except DecisionArtifactError as exc:
        assert "unknown references" in str(exc)
    else:
        raise AssertionError("unknown evidence was accepted")

    claimed = copy.deepcopy(request)
    claimed["approval"] = {"status": "approved", "approved_by": "fixture"}
    try:
        construct_decision_artifact(claimed, request_path=request_path, source_root=tmp_path)
    except DecisionArtifactError as exc:
        assert "cannot assert review or approval state" in str(exc)
    else:
        raise AssertionError("unverified approval was accepted")
