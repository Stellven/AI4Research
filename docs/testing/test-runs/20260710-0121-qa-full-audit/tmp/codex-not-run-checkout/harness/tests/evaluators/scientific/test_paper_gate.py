from __future__ import annotations

from evaluators.scientific import paper_gate


def _paper_payload() -> dict:
    return {
        "schema": "research_paper.v1",
        "task_id": "task-paper",
        "sprint_id": "sprint-paper",
        "node_id": "node-paper",
        "status": "completed",
        "inputs": {"source_ref": "paper.pdf"},
        "outputs": {
            "paper": {
                "paper_id": "paper-pdf",
                "title": "PDF Paper",
                "source_type": "latex",
                "source_ref": "raw/tmp/papers/paper.tex",
                "identifiers": {},
                "abstract": "A PDF-derived abstract.",
                "parse_status": "parsed",
                "sections": [
                    {
                        "section_id": "body",
                        "title": "Body",
                        "text": "Extracted PDF body text.",
                        "source_anchor": "paper.pdf#body",
                    }
                ],
                "preparation": {
                    "original_format": "pdf",
                    "extracted_text_path": "raw/tmp/papers/paper.txt",
                    "prepared_path": "raw/tmp/papers/paper.tex",
                },
            }
        },
        "artifacts": [
            {"type": "extracted_pdf_text", "path": "raw/tmp/papers/paper.txt"},
            {"type": "synthetic_latex", "path": "raw/tmp/papers/paper.tex"},
        ],
        "provenance": {
            "operator_id": "test",
            "implementation_package": "test",
            "timestamp": "2026-06-25T00:00:00Z",
        },
        "limitations": [],
    }


def test_paper_gate_accepts_pdf_with_extracted_text_artifact() -> None:
    result = paper_gate.evaluate(_paper_payload())

    assert result.ok is True
    assert result.status == "passed"


def test_paper_gate_rejects_completed_pdf_without_extracted_text_artifact() -> None:
    payload = _paper_payload()
    payload["outputs"]["paper"]["preparation"].pop("extracted_text_path")
    payload["artifacts"] = [{"type": "synthetic_latex", "path": "raw/tmp/papers/paper.tex"}]

    result = paper_gate.evaluate(payload)

    assert result.ok is False
    joined = " ".join(result.reasons)
    assert "extracted_text_path" in joined
    assert "extracted_pdf_text" in joined
