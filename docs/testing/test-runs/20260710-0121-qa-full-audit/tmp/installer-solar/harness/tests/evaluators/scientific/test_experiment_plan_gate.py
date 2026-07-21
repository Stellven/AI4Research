from pathlib import Path

from evaluators.scientific import experiment_plan_gate
from evaluators.scientific.common import load_json

FIXTURES = Path(__file__).parent / "fixtures"


def test_experiment_plan_gate_accepts_bounded_plan():
    result = experiment_plan_gate.evaluate(load_json(FIXTURES / "pass/experiment_plan.json"))

    assert result.ok is True
    assert result.status == "passed"
    assert result.reasons == []


def test_experiment_plan_gate_rejects_missing_plan_details():
    result = experiment_plan_gate.evaluate(load_json(FIXTURES / "fail/experiment_plan.json"))

    assert result.ok is False
    assert result.status == "failed"
    joined = " ".join(result.reasons)
    assert "metrics" in joined
    assert "procedure" in joined
