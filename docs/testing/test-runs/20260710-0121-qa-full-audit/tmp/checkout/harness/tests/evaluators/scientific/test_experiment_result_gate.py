from pathlib import Path

from evaluators.scientific import experiment_result_gate
from evaluators.scientific.common import load_json

FIXTURES = Path(__file__).parent / "fixtures"


def test_experiment_result_gate_accepts_metric_and_evidence_ids():
    result = experiment_result_gate.evaluate(load_json(FIXTURES / "pass/experiment_result.json"))

    assert result.ok is True
    assert result.status == "passed"
    assert result.reasons == []


def test_experiment_result_gate_rejects_empty_metrics_and_evidence():
    result = experiment_result_gate.evaluate(load_json(FIXTURES / "fail/experiment_result.json"))

    assert result.ok is False
    assert result.status == "failed"
    joined = " ".join(result.reasons)
    assert "metrics" in joined
    assert "evidence_ids" in joined
