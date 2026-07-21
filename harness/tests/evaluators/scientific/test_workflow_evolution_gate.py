from pathlib import Path

from evaluators.scientific import workflow_evolution_gate
from evaluators.scientific.common import load_json

FIXTURES = Path(__file__).parent / "fixtures"


def test_workflow_evolution_gate_accepts_reviewable_proposal():
    result = workflow_evolution_gate.evaluate(
        load_json(FIXTURES / "pass/workflow_evolution.json"),
        FIXTURES / "pass/workflow_evolution.json",
    )

    assert result.ok is True
    assert result.status == "passed"
    assert result.reasons == []


def test_workflow_evolution_gate_rejects_unreviewed_or_ungrounded_change():
    result = workflow_evolution_gate.evaluate(
        load_json(FIXTURES / "fail/workflow_evolution.json"),
        FIXTURES / "fail/workflow_evolution.json",
    )

    assert result.ok is False
    assert result.status == "failed"
    joined = " ".join(result.reasons)
    assert "failed_nodes" in joined
    assert "review_required" in joined
    assert "protected_core_edits_applied" in joined
