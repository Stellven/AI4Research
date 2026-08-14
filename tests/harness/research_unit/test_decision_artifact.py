from __future__ import annotations

import copy
import hashlib
import json
import os
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


def _request(
    tmp_path: Path,
    *,
    observed: str = "supported",
    experiment_outcome: str = "supports",
) -> tuple[dict, Path]:
    experiment = tmp_path / "experiment-result.json"
    experiment.write_text(
        json.dumps(
            {
                "schema": "experiment_result.v1",
                "task_id": "task-exp-1",
                "sprint_id": "sprint-1",
                "node_id": "node-exp-1",
                "status": "completed",
                "inputs": {},
                "outputs": {
                    "result": {
                        "experiment_id": "exp-1",
                        "outcome": experiment_outcome,
                        "metrics": [{"name": "accuracy", "value": 0.9}],
                        "evidence_ids": ["exp-1", "runtime:exp-1"],
                    }
                },
                "artifacts": [],
                "provenance": {
                    "operator_id": "unit-test",
                    "implementation_package": "tests",
                    "timestamp": "2026-08-11T00:00:00Z",
                },
                "limitations": [],
            }
        ),
        encoding="utf-8",
    )
    evidence = tmp_path / "claim-verdict.json"
    evidence.write_text(
        json.dumps(
            {
                "schema": "claim_verdict.v1",
                "task_id": "task-claim-1",
                "sprint_id": "sprint-1",
                "node_id": "node-claim-1",
                "status": "completed",
                "inputs": {},
                "outputs": {
                    "verdicts": [
                        {
                            "claim_id": "claim-1",
                            "verdict": observed,
                            "confidence": 0.9,
                            "basis": "The typed experiment result supports this bounded claim.",
                            "evidence_ids": ["claim-1", "exp-1", "runtime:exp-1"],
                            "experiment_id": "exp-1",
                            "experiment_evidence_ids": ["exp-1", "runtime:exp-1"],
                            "limitations": [],
                        }
                    ]
                },
                "artifacts": [],
                "provenance": {
                    "operator_id": "unit-test",
                    "implementation_package": "tests",
                    "timestamp": "2026-08-11T00:00:00Z",
                },
                "limitations": [],
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
                "supporting_experiment_evidence_id": "experiment-1-result",
                "source_path": str(evidence),
                "expected_sha256": _sha256(evidence),
                "summary": "The local claim verifier marked the bounded claim supported.",
            },
            {
                "evidence_id": "experiment-1-result",
                "evidence_type": "experiment_result",
                "source_path": str(experiment),
                "expected_sha256": _sha256(experiment),
                "summary": "The schema-valid completed experiment explicitly supports the bounded claim.",
            },
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
            "evidence_ids": ["claim-1-verdict", "experiment-1-result"],
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
    assert artifact["recommendation"]["evidence_ids"] == ["claim-1-verdict", "experiment-1-result"]
    assert artifact["evidence_links"][0]["observed_support"] == "supported"
    assert artifact["evidence_links"][0]["evidence_type"] == "claim_verdict"
    assert artifact["evidence_links"][0]["supporting_evidence_ids"] == ["experiment-1-result"]
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


def test_schema_valid_completed_refuting_experiment_fails_closed(tmp_path: Path) -> None:
    _, request_path = _request(tmp_path, experiment_outcome="refutes")
    output = tmp_path / "decision.json"
    output.write_text("stale", encoding="utf-8")

    proc = _run_cli(request_path, output, tmp_path)

    assert proc.returncode == 2
    assert not output.exists()
    error = json.loads(proc.stderr)["error"]
    assert "expected 'supports', observed 'refutes'" in error


def test_typed_upstream_must_validate_against_repository_schemas(tmp_path: Path) -> None:
    request, request_path = _request(tmp_path)
    claim_path = Path(request["evidence"][0]["source_path"])
    claim = json.loads(claim_path.read_text(encoding="utf-8"))
    del claim["outputs"]["verdicts"][0]["confidence"]
    claim_path.write_text(json.dumps(claim), encoding="utf-8")
    request["evidence"][0]["expected_sha256"] = _sha256(claim_path)
    with pytest.raises(DecisionArtifactError, match="fails claim_verdict.v1 schema"):
        _construct(request, request_path, tmp_path)

    request, request_path = _request(tmp_path)
    experiment_path = Path(request["evidence"][1]["source_path"])
    experiment = json.loads(experiment_path.read_text(encoding="utf-8"))
    del experiment["outputs"]["result"]["evidence_ids"]
    experiment_path.write_text(json.dumps(experiment), encoding="utf-8")
    request["evidence"][1]["expected_sha256"] = _sha256(experiment_path)
    with pytest.raises(DecisionArtifactError, match="fails experiment_result.v1 schema"):
        _construct(request, request_path, tmp_path)


def test_output_aliases_are_rejected_before_input_or_evidence_unlink(tmp_path: Path) -> None:
    request, request_path = _request(tmp_path)
    request_before = request_path.read_bytes()

    input_alias = _run_cli(request_path, request_path, tmp_path)

    assert input_alias.returncode == 2
    assert "aliases protected input/evidence" in json.loads(input_alias.stderr)["error"]
    assert request_path.read_bytes() == request_before

    evidence_path = Path(request["evidence"][0]["source_path"])
    evidence_before = evidence_path.read_bytes()
    hardlink_output = tmp_path / "hardlink-output.json"
    os.link(evidence_path, hardlink_output)

    evidence_alias = _run_cli(request_path, hardlink_output, tmp_path)

    assert evidence_alias.returncode == 2
    assert "aliases protected input/evidence" in json.loads(evidence_alias.stderr)["error"]
    assert evidence_path.read_bytes() == evidence_before
    assert hardlink_output.exists()


@pytest.mark.parametrize("raw_request", ["{not-json", "[1, 2, 3]"])
def test_malformed_or_nonobject_request_removes_nonalias_stale_output(
    tmp_path: Path, raw_request: str
) -> None:
    request_path = tmp_path / "request.json"
    request_path.write_text(raw_request, encoding="utf-8")
    output = tmp_path / "decision.json"
    output.write_text("stale", encoding="utf-8")

    proc = _run_cli(request_path, output, tmp_path)

    assert proc.returncode == 2
    assert not output.exists()
    assert request_path.read_text(encoding="utf-8") == raw_request


def test_non_utf8_request_removes_nonalias_stale_output(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    request_path.write_bytes(b"\xff\xfe\x00")
    output = tmp_path / "decision.json"
    output.write_text("stale", encoding="utf-8")

    proc = _run_cli(request_path, output, tmp_path)

    assert proc.returncode == 2
    assert not output.exists()
    assert request_path.read_bytes() == b"\xff\xfe\x00"


def test_malformed_and_nonobject_aliases_preserve_protected_input(tmp_path: Path) -> None:
    malformed = tmp_path / "malformed.json"
    malformed.write_text("{not-json", encoding="utf-8")
    malformed_before = malformed.read_bytes()

    direct_alias = _run_cli(malformed, malformed, tmp_path)

    assert direct_alias.returncode == 2
    assert "aliases protected input/evidence" in json.loads(direct_alias.stderr)["error"]
    assert malformed.read_bytes() == malformed_before

    nonobject = tmp_path / "nonobject.json"
    nonobject.write_text("[1, 2, 3]", encoding="utf-8")
    nonobject_before = nonobject.read_bytes()
    hardlink_output = tmp_path / "nonobject-hardlink.json"
    os.link(nonobject, hardlink_output)

    hardlink_alias = _run_cli(nonobject, hardlink_output, tmp_path)

    assert hardlink_alias.returncode == 2
    assert "aliases protected input/evidence" in json.loads(hardlink_alias.stderr)["error"]
    assert nonobject.read_bytes() == nonobject_before
    assert hardlink_output.exists()


def test_symlink_output_alias_is_rejected_without_deleting_evidence(tmp_path: Path) -> None:
    request, request_path = _request(tmp_path)
    evidence_path = Path(request["evidence"][0]["source_path"])
    evidence_before = evidence_path.read_bytes()
    output = tmp_path / "symlink-output.json"
    try:
        output.symlink_to(evidence_path)
    except OSError:
        pytest.skip("symlink creation is unavailable in this Windows environment")

    proc = _run_cli(request_path, output, tmp_path)

    assert proc.returncode == 2
    assert "aliases protected input/evidence" in json.loads(proc.stderr)["error"]
    assert evidence_path.read_bytes() == evidence_before
    assert output.is_symlink()


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
    request["recommendation"]["evidence_ids"] = ["claim-1-verdict"]
    with pytest.raises(DecisionArtifactError, match="omit typed supporting evidence"):
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
    second_evidence = tmp_path / "second-experiment.json"
    second_evidence.write_text(
        json.dumps(
            {
                "schema": "experiment_result.v1",
                "task_id": "task-exp-2",
                "sprint_id": "sprint-1",
                "node_id": "node-exp-2",
                "status": "completed",
                "inputs": {},
                "outputs": {
                    "result": {
                        "experiment_id": "exp-2",
                        "outcome": "supports",
                        "metrics": [],
                        "evidence_ids": ["exp-2"],
                    }
                },
                "artifacts": [],
                "provenance": {
                    "operator_id": "unit-test",
                    "implementation_package": "tests",
                    "timestamp": "2026-08-11T00:00:00Z",
                },
                "limitations": [],
            }
        ),
        encoding="utf-8",
    )
    request["evidence"].append(
        {
            "evidence_id": "experiment-2-result",
            "evidence_type": "experiment_result",
            "source_path": str(second_evidence),
            "expected_sha256": _sha256(second_evidence),
            "summary": "A second typed experiment supports the risk assessment.",
        }
    )
    request["assessments"][1]["evidence_ids"] = ["experiment-2-result"]
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
