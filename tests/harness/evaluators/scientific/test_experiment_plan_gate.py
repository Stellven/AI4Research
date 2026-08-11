from pathlib import Path
from copy import deepcopy

from evaluators.scientific import experiment_plan_gate
from evaluators.scientific.common import load_json

FIXTURES = (Path(__file__).resolve().parents[4] / 'tests' / 'harness' / 'evaluators' / 'scientific') / "fixtures"


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


def test_experiment_plan_gate_accepts_complete_verification_ready_contract():
    payload = deepcopy(load_json(FIXTURES / "pass/experiment_plan.json"))
    plan = payload["outputs"]["experiment_plan"]
    plan.update(
        {
            "dataset": {"path": "samples.csv", "format": "csv", "role": "evaluation"},
            "variants": [
                {"name": "baseline", "description": "case-sensitive classifier"},
                {"name": "normalization", "description": "normalized classifier"},
            ],
            "thresholds": [{"metric": "accuracy_uplift", "operator": ">=", "value": 0.2}],
            "random_seed": 7,
            "stopping_conditions": ["all rows processed", "timeout at 60 seconds"],
            "command_argv": ["python3", "run.py", "samples.csv", "result.json"],
            "approval_preflight": {
                "status": "ready",
                "approval_state": "approved_pending_runtime",
                "command_authorized": True,
                "before_state_ready": True,
            },
            "execution_ready": True,
        }
    )

    result = experiment_plan_gate.evaluate(payload)

    assert result.ok is True


def test_experiment_plan_gate_rejects_false_ready_claim_without_complete_preflight():
    payload = deepcopy(load_json(FIXTURES / "pass/experiment_plan.json"))
    plan = payload["outputs"]["experiment_plan"]
    plan.update(
        {
            "dataset": {"path": "samples.csv", "format": "csv", "role": "evaluation"},
            "variants": [{"name": "baseline", "description": "only one variant"}],
            "thresholds": [],
            "random_seed": 7,
            "stopping_conditions": [],
            "command_argv": ["python3", "run.py"],
            "approval_preflight": {
                "status": "incomplete",
                "approval_state": "approved_missing_preflight",
                "command_authorized": False,
                "before_state_ready": False,
            },
            "execution_ready": True,
        }
    )

    result = experiment_plan_gate.evaluate(payload)

    assert result.ok is False
    joined = " ".join(result.reasons)
    assert "variants" in joined
    assert "thresholds" in joined
    assert "stopping_conditions" in joined
    assert "execution_ready=true" in joined
