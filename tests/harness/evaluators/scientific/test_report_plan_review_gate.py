from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from evaluators.scientific import report_plan_review_gate


def _payload(tmp_path: Path) -> dict:
    plan_hash = hashlib.sha256(b"plan").hexdigest()
    artifact = tmp_path / "review.json"
    artifact.write_text("{}", encoding="utf-8")
    return {
        "schema": "scientific_report_plan_review.v1",
        "task_id": "task-review",
        "sprint_id": "sprint-review",
        "node_id": "artifact_review",
        "status": "completed",
        "inputs": {},
        "outputs": {
            "review": {
                "artifact_id": "report-plan-1",
                "target_schema": "scientific_report_plan.v1",
                "review_stage": "pre_draft_plan",
                "review_mode": "review_llm",
                "review_available": True,
                "score": 0.6,
                "recommendation": "revise_plan",
                "evidence_ids": ["finding-1"],
                "reviewed_artifact_sha256": plan_hash,
            },
            "findings": [{
                "finding_id": "finding-1",
                "severity": "high",
                "category": "coverage",
                "evidence": "One requirement needs stronger coverage.",
                "suggestion": "Retain it as a limitation or address it in the draft.",
            }],
            "artifact": {"schema": "scientific_report_plan.v1", "sha256": plan_hash},
        },
        "artifacts": [{"type": "review_json", "path": str(artifact)}],
        "provenance": {
            "operator_id": "autosci-artifact-review-physical",
            "implementation_package": "plugins/autosci",
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        },
        "limitations": ["Pre-draft findings remain subject to the final Evidence Gate."],
    }


def test_predraft_review_gate_accepts_revise_recommendation_as_diagnostic(tmp_path: Path) -> None:
    result = report_plan_review_gate.evaluate(_payload(tmp_path), path=tmp_path / "evidence.json")

    assert result.ok is True
    assert result.status == "passed"


def test_predraft_review_gate_rejects_missing_model_review(tmp_path: Path) -> None:
    payload = _payload(tmp_path)
    payload["outputs"]["review"]["review_mode"] = "local_surrogate"
    payload["outputs"]["review"]["review_available"] = False

    result = report_plan_review_gate.evaluate(payload, path=tmp_path / "evidence.json")

    assert result.ok is False
    assert "completed Review LLM" in " ".join(result.reasons)
