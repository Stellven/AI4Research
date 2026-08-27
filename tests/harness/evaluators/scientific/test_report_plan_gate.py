from copy import deepcopy

from evaluators.scientific import report_plan_gate


def _payload() -> dict:
    return {
        "schema": "scientific_report_plan.v1",
        "task_id": "task-report-plan",
        "sprint_id": "sprint-report-plan",
        "node_id": "report_plan",
        "status": "completed",
        "inputs": {},
        "outputs": {
            "report_plan": {
                "report_id": "report-1",
                "title": "Grounded comparison",
                "audience": "researcher",
                "sections": [
                    {
                        "section_id": "findings",
                        "title": "Findings",
                        "purpose": "Compare the evidence.",
                        "evidence_ids": ["evidence-1"],
                    }
                ],
                "supported_claim_ids": ["claim-1"],
                "excluded_claim_ids": [],
                "evidence_ids": ["evidence-1"],
            }
        },
        "artifacts": [],
        "provenance": {
            "operator_id": "autosci-report-planning-physical",
            "operator_version": "1",
            "implementation_package": "plugins.autosci",
            "timestamp": "2026-08-26T00:00:00Z",
            "input_sha256": "a" * 64,
            "output_sha256": "b" * 64,
        },
        "limitations": [],
    }


def test_report_plan_gate_accepts_evidence_linked_plan() -> None:
    result = report_plan_gate.evaluate(_payload())

    assert result.ok is True
    assert result.reasons == []


def test_report_plan_gate_rejects_sections_without_evidence() -> None:
    payload = deepcopy(_payload())
    payload["outputs"]["report_plan"]["sections"][0]["evidence_ids"] = []

    result = report_plan_gate.evaluate(payload)

    assert result.ok is False
    assert "sections[0].evidence_ids" in " ".join(result.reasons)
