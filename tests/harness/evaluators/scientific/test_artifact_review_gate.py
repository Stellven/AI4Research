from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from evaluators.scientific import artifact_review_gate


def payload(tmp_path: Path) -> dict:
    target = tmp_path / "review-target.md"
    target.write_text(
        "# Review Target\n\nThe method uses a dataset, metric, baseline, and evidence artifact.\n",
        encoding="utf-8",
    )
    report = tmp_path / "artifact_review.md"
    report.write_text("# Review\n", encoding="utf-8")
    return {
        "schema": "artifact_review.v1",
        "task_id": "task-review",
        "sprint_id": "sprint-review",
        "node_id": "node-review",
        "status": "completed",
        "inputs": {"target": str(target)},
        "outputs": {
            "review": {
                "artifact_id": "artifact:review-target",
                "target": str(target),
                "review_mode": "local_surrogate",
                "review_available": False,
                "difficulty": "hard",
                "focus": "method",
                "score": 0.7,
                "recommendation": "pass_with_review_required",
                "evidence_ids": ["artifact:review-target"],
                "review_llm": {
                    "status": "unavailable",
                    "tool": "mcp__llm-review__chat",
                    "reason": "No Review LLM evidence was supplied.",
                },
                "proof_contract": {
                    "schema": "scientific_review_proof.v1",
                    "verdict": "supported",
                    "blockers": [],
                    "claims": [{"claim_id": "claim-1", "verdict": "supported"}],
                    "reviewer_separation": {
                        "artifact_reloaded_from_disk": True,
                        "proof_bundle_reloaded_from_disk": True,
                        "writer_output_excluded_from_reviewer_context": True,
                        "independence": {"status": "same_provider_limitation"},
                    },
                },
            },
            "findings": [],
            "artifact": {"artifact_id": "artifact:review-target", "path": str(target), "target": str(target)},
        },
        "artifacts": [
            {"type": "review_target", "path": str(target)},
            {"type": "artifact_review_markdown", "path": str(report)},
        ],
        "provenance": {
            "operator_id": "test",
            "implementation_package": "test",
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        },
        "limitations": [
            "Review LLM MCP evidence is not connected for this local surrogate.",
            "Same-provider limitation: no second reviewer provider is configured.",
        ],
    }


def test_artifact_review_gate_accepts_local_surrogate_with_disclosure(tmp_path: Path) -> None:
    result = artifact_review_gate.evaluate(payload(tmp_path), path=tmp_path / "review.json")

    assert result.ok is True
    assert result.status == "passed"


def test_artifact_review_gate_rejects_local_surrogate_claiming_review_available(tmp_path: Path) -> None:
    item = payload(tmp_path)
    item["outputs"]["review"]["review_available"] = True
    item["limitations"] = []

    result = artifact_review_gate.evaluate(item, path=tmp_path / "review.json")

    assert result.ok is False
    joined = " ".join(result.reasons)
    assert "review_available=false" in joined
    assert "Review LLM" in joined
