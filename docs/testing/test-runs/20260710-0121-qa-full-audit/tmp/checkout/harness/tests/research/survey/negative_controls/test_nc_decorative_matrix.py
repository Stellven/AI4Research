"""Negative control: decorative contradiction matrix cannot pass silently."""

from __future__ import annotations

import json
from pathlib import Path

from research.survey.gates.controversy_matrix import controversy_gate

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "nc_decorative_matrix.json"


def test_decorative_matrix_warns() -> None:
    data = json.loads(FIXTURE.read_text())
    result = controversy_gate(data["evidence_pack"], data["claim_evidence_rows"])
    assert result["verdict"] == "warn"
    assert result["decorative"] is True
    assert "decorative_matrix_warning" in result["verdict_reasons"]
    assert result["matrix_row_count"] == 1

