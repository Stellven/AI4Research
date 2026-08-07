from pathlib import Path

from evaluators.scientific import claim_verdict_gate
from evaluators.scientific.common import load_json

FIXTURES = (Path(__file__).resolve().parents[4] / 'tests' / 'harness' / 'evaluators' / 'scientific') / "fixtures"


def test_claim_verdict_gate_accepts_evidence_linked_verdict():
    path = FIXTURES / "pass/claim_verdict.json"
    result = claim_verdict_gate.evaluate(load_json(path), path)

    assert result.ok is True
    assert result.status == "passed"
    assert result.reasons == []


def test_claim_verdict_gate_rejects_source_free_verdict():
    path = FIXTURES / "fail/claim_verdict.json"
    result = claim_verdict_gate.evaluate(load_json(path), path)

    assert result.ok is False
    assert result.status == "failed"
    joined = " ".join(result.reasons)
    assert "evidence_ids" in joined
    assert "limitations" in joined
    assert "artifacts" in joined


def test_claim_verdict_gate_requires_claim_id_in_evidence_ids():
    path = FIXTURES / "pass/claim_verdict.json"
    payload = load_json(path)
    payload["outputs"]["verdicts"][0]["evidence_ids"] = ["experiment.sample.001"]
    result = claim_verdict_gate.evaluate(payload, path)

    assert result.ok is False
    assert "claim_id" in " ".join(result.reasons)


def test_claim_verdict_gate_rejects_upgraded_inconclusive_evidence():
    path = FIXTURES / "pass/claim_verdict.json"
    payload = load_json(path)
    payload["outputs"]["verdicts"][0]["evidence_outcome"] = "inconclusive"
    payload["outputs"]["verdicts"][0]["verdict"] = "supported"
    result = claim_verdict_gate.evaluate(payload, path)

    assert result.ok is False
    joined = " ".join(result.reasons)
    assert "cannot upgrade inconclusive evidence" in joined


def test_claim_verdict_gate_accepts_explicit_insufficient_verdict():
    path = FIXTURES / "pass/claim_verdict.json"
    payload = load_json(path)
    verdict = payload["outputs"]["verdicts"][0]
    verdict["verdict"] = "insufficient"
    verdict["support_classification"] = "insufficient_evidence"
    verdict["evidence_outcome"] = "insufficient_evidence"
    verdict["confidence"] = 0.35
    verdict["limitations"] = ["Evidence is bounded and cannot establish the claim scope."]

    result = claim_verdict_gate.evaluate(payload, path)

    assert result.ok is True


def test_claim_verdict_gate_rejects_supported_overclaim_risk():
    path = FIXTURES / "pass/claim_verdict.json"
    payload = load_json(path)
    verdict = payload["outputs"]["verdicts"][0]
    verdict["verdict"] = "supported"
    verdict["overclaim_risks"] = ["Claim says all future datasets but evidence is local."]

    result = claim_verdict_gate.evaluate(payload, path)

    assert result.ok is False
    assert "overclaim_risks" in " ".join(result.reasons)
