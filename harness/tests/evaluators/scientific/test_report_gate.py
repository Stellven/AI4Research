from pathlib import Path

from evaluators.scientific import publication_gate, report_gate
from evaluators.scientific.common import load_json

FIXTURES = Path(__file__).parent / "fixtures"


def test_report_gate_accepts_evidence_linked_report():
    result = report_gate.evaluate(load_json(FIXTURES / "pass/scientific_report.json"))

    assert result.ok is True
    assert result.status == "passed"
    assert result.reasons == []


def test_report_gate_rejects_unsupported_or_evidence_free_report():
    result = report_gate.evaluate(load_json(FIXTURES / "fail/scientific_report.json"))

    assert result.ok is False
    assert result.status == "failed"
    joined = " ".join(result.reasons)
    assert "evidence_ids" in joined
    assert "unsupported_claims" in joined


def test_publication_gate_accepts_file_linked_bundle():
    result = publication_gate.evaluate(load_json(FIXTURES / "pass/publication_bundle.json"))

    assert result.ok is True
    assert result.status == "passed"
    assert result.reasons == []


def test_publication_gate_rejects_missing_files_and_source_report_link():
    result = publication_gate.evaluate(load_json(FIXTURES / "fail/publication_bundle.json"))

    assert result.ok is False
    assert result.status == "failed"
    joined = " ".join(result.reasons)
    assert "files" in joined
    assert "source_report_id" in joined
