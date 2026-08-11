from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest

from harness.lib.research.decision_artifact import (
    DecisionArtifactError,
    _resolve_json_pointer,
    construct_decision_artifact,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
TOOL = REPO_ROOT / "harness" / "tools" / "decision_artifact.py"
SCHEMA = REPO_ROOT / "harness" / "schemas" / "evidence" / "decision_artifact.v1.schema.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_request(path: Path, request: dict) -> Path:
    path.write_text(json.dumps(request), encoding="utf-8")
    return path


def _request(tmp_path: Path, *, observed: str = "supported") -> tuple[dict, Path]:
    evidence = tmp_path / "claim-verdict.json"
    evidence.write_text(
        json.dumps(
            {
                "schema": "claim_verdict.v1",
                "outputs": {"verdicts": [{"claim_id": "claim-1", "verdict": observed}]},
            }
        ),
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
                "evidence_type": "claim_verdict",
                "claim_id": "claim-1",
                "source_path": str(evidence),
                "expected_sha256": _sha256(evidence),
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
            {
                "alternative_id": "global",
                "criterion_id": "risk",
                "score": 0,
                "rationale": "The unreviewed broad rollout has uncontrolled external-validity risk.",
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
    return request, _write_request(tmp_path / "request.json", request)


def _construct(request: dict, request_path: Path, tmp_path: Path) -> dict:
    _write_request(request_path, request)
    return construct_decision_artifact(request, request_path=request_path, source_root=tmp_path)


def _run_cli(request_path: Path, output: Path, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "--input",
            str(request_path),
            "--output",
            str(output),
            "--source-root",
            str(tmp_path),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_constructor_emits_schema_valid_review_required_artifact(tmp_path: Path) -> None:
    request, request_path = _request(tmp_path)

    artifact = construct_decision_artifact(request, request_path=request_path, source_root=tmp_path)

    jsonschema.Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8"))).validate(artifact)
    assert artifact["recommendation"]["criterion_ids"] == ["evidence", "risk"]
    assert artifact["recommendation"]["evidence_ids"] == ["claim-1-verdict"]
    assert artifact["evidence_links"][0]["observed_support"] == "supported"
    assert artifact["evidence_links"][0]["evidence_type"] == "claim_verdict"
    assert artifact["review"]["status"] == "pending"
    assert artifact["approval"] == {
        "status": "not_requested",
        "approved_by": None,
        "approval_evidence": [],
    }


def test_cli_validates_schema_and_atomically_replaces_output(tmp_path: Path) -> None:
    _, request_path = _request(tmp_path)
    output = tmp_path / "decision.json"
    output.write_text("stale", encoding="utf-8")

    proc = _run_cli(request_path, output, tmp_path)

    assert proc.returncode == 0, proc.stderr
    artifact = json.loads(output.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8"))).validate(artifact)
    assert json.loads(proc.stdout)["status"] == "completed"
    assert not list(tmp_path.glob(".decision.json.*.tmp"))


def test_unsupported_evidence_fails_closed_and_removes_stale_output(tmp_path: Path) -> None:
    _, request_path = _request(tmp_path, observed="inconclusive")
    output = tmp_path / "decision.json"
    output.write_text('{"schema":"decision_artifact.v1"}', encoding="utf-8")

    proc = _run_cli(request_path, output, tmp_path)

    assert proc.returncode == 2
    assert not output.exists()
    assert "not supportive" in json.loads(proc.stderr)["error"]
    assert not list(tmp_path.glob(".decision.json.*.tmp"))


def test_hash_mismatch_unknown_type_and_caller_semantics_are_rejected(tmp_path: Path) -> None:
    request, request_path = _request(tmp_path)
    request["evidence"][0]["expected_sha256"] = "0" * 64
    with pytest.raises(DecisionArtifactError, match="hash mismatch"):
        _construct(request, request_path, tmp_path)

    request, request_path = _request(tmp_path)
    request["evidence"][0]["evidence_type"] = "caller_defined"
    with pytest.raises(DecisionArtifactError, match="unknown evidence type"):
        _construct(request, request_path, tmp_path)

    request, request_path = _request(tmp_path)
    request["evidence"][0]["supported_values"] = ["inconclusive"]
    with pytest.raises(DecisionArtifactError, match="unsupported fields"):
        _construct(request, request_path, tmp_path)


def test_request_object_must_match_hashed_request_path(tmp_path: Path) -> None:
    request, request_path = _request(tmp_path)
    changed = copy.deepcopy(request)
    changed["title"] = "Unpersisted title"

    with pytest.raises(DecisionArtifactError, match="does not match request_path"):
        construct_decision_artifact(changed, request_path=request_path, source_root=tmp_path)


def test_duplicate_and_unknown_references_are_rejected(tmp_path: Path) -> None:
    request, request_path = _request(tmp_path)
    request["recommendation"]["evidence_ids"] = ["claim-1-verdict", "claim-1-verdict"]
    with pytest.raises(DecisionArtifactError, match="duplicate references"):
        _construct(request, request_path, tmp_path)

    request, request_path = _request(tmp_path)
    request["recommendation"]["evidence_ids"] = ["missing-evidence"]
    with pytest.raises(DecisionArtifactError, match="unknown references"):
        _construct(request, request_path, tmp_path)


def test_full_matrix_all_criteria_and_evidence_coverage_are_required(tmp_path: Path) -> None:
    request, request_path = _request(tmp_path)
    request["assessments"].pop()
    with pytest.raises(DecisionArtifactError, match="assessment matrix is incomplete"):
        _construct(request, request_path, tmp_path)

    request, request_path = _request(tmp_path)
    request["recommendation"]["criterion_ids"] = ["evidence"]
    with pytest.raises(DecisionArtifactError, match="cover every decision criterion"):
        _construct(request, request_path, tmp_path)

    request, request_path = _request(tmp_path)
    second_evidence = tmp_path / "second-verdict.json"
    second_evidence.write_text(
        json.dumps(
            {
                "schema": "claim_verdict.v1",
                "outputs": {"verdicts": [{"claim_id": "claim-2", "verdict": "supported"}]},
            }
        ),
        encoding="utf-8",
    )
    request["evidence"].append(
        {
            "evidence_id": "claim-2-verdict",
            "evidence_type": "claim_verdict",
            "claim_id": "claim-2",
            "source_path": str(second_evidence),
            "expected_sha256": _sha256(second_evidence),
            "summary": "A second typed verdict supports the risk assessment.",
        }
    )
    request["assessments"][1]["evidence_ids"] = ["claim-2-verdict"]
    with pytest.raises(DecisionArtifactError, match="do not cover recommendation assessments"):
        _construct(request, request_path, tmp_path)


def test_unverified_approval_is_rejected(tmp_path: Path) -> None:
    request, request_path = _request(tmp_path)
    request["approval"] = {"status": "approved", "approved_by": "fixture"}

    with pytest.raises(DecisionArtifactError, match="cannot assert review or approval state"):
        _construct(request, request_path, tmp_path)


@pytest.mark.parametrize("pointer", ["/items/-1", "/items/01", "/a~2b", "/a~"])
def test_json_pointer_rejects_negative_noncanonical_and_invalid_escapes(pointer: str) -> None:
    with pytest.raises(DecisionArtifactError):
        _resolve_json_pointer({"items": ["first"], "a/b": "value"}, pointer)


def test_json_pointer_applies_rfc6901_escapes() -> None:
    assert _resolve_json_pointer({"a/b": {"~key": "value"}}, "/a~1b/~0key") == "value"
