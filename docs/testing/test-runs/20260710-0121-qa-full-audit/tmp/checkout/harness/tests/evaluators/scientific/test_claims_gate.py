from pathlib import Path

from evaluators.scientific import claims_gate
from evaluators.scientific.common import load_json

FIXTURES = Path(__file__).parent / "fixtures"


def test_claims_gate_accepts_grounded_unverified_claims():
    result = claims_gate.evaluate(load_json(FIXTURES / "pass/research_claims.json"))

    assert result.ok is True
    assert result.status == "passed"
    assert result.reasons == []


def test_claims_gate_rejects_verified_or_source_free_claims():
    result = claims_gate.evaluate(load_json(FIXTURES / "fail/research_claims.json"))

    assert result.ok is False
    assert result.status == "failed"
    joined = " ".join(result.reasons)
    assert "verification_status" in joined
    assert "claim_type" in joined
    assert "source_anchor" in joined
