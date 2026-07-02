from pathlib import Path

from evaluators.scientific import experiment_status_gate
from evaluators.scientific.common import load_json

FIXTURES = Path(__file__).parent / "fixtures"


def test_experiment_status_gate_accepts_completed_status_with_evidence():
    result = experiment_status_gate.evaluate(load_json(FIXTURES / "pass/experiment_status.json"))

    assert result.ok is True
    assert result.status == "passed"
    assert result.reasons == []


def test_experiment_status_gate_rejects_empty_status_details():
    result = experiment_status_gate.evaluate(load_json(FIXTURES / "fail/experiment_status.json"))

    assert result.ok is False
    assert result.status == "failed"
    joined = " ".join(result.reasons)
    assert "observations" in joined
    assert "next_actions" in joined
    assert "evidence_ids" in joined
