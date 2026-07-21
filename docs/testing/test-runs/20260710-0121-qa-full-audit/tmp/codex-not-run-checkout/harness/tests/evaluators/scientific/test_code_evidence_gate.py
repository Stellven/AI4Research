from copy import deepcopy
from pathlib import Path

from evaluators.scientific import code_evidence_gate
from evaluators.scientific.common import load_json

FIXTURES = Path(__file__).parent / "fixtures"


def test_code_evidence_gate_accepts_relevance_labeled_mapping():
    result = code_evidence_gate.evaluate(load_json(FIXTURES / "pass/code_evidence_map.json"))

    assert result.ok is True
    assert result.status == "passed"
    assert result.reasons == []


def test_code_evidence_gate_rejects_missing_relevance_label():
    result = code_evidence_gate.evaluate(load_json(FIXTURES / "fail/code_evidence_map.json"))

    assert result.ok is False
    assert result.status == "failed"
    joined = " ".join(result.reasons)
    assert "relevance_label" in joined
    assert "relevance_reason" in joined


def test_code_evidence_gate_rejects_mapped_placeholder_file():
    payload = deepcopy(load_json(FIXTURES / "pass/code_evidence_map.json"))
    payload["outputs"]["mappings"][0]["files"] = ["N/A"]

    result = code_evidence_gate.evaluate(payload)

    assert result.ok is False
    assert result.status == "failed"
    assert "concrete file path" in " ".join(result.reasons)


def test_code_evidence_gate_accepts_unknown_placeholder_with_reason():
    payload = deepcopy(load_json(FIXTURES / "pass/code_evidence_map.json"))
    mapping = payload["outputs"]["mappings"][0]
    mapping["files"] = ["N/A"]
    mapping["mapping_status"] = "unknown"
    mapping["relevance_label"] = "unknown"
    mapping["relevance_reason"] = "Repository path was unavailable."
    mapping["unknown_reason"] = "Repository path was unavailable."

    result = code_evidence_gate.evaluate(payload)

    assert result.ok is True
    assert result.status == "passed"
