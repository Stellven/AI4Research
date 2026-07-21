"""Tests for contradiction_matrix_view — CLI formatting and dict conversion."""

from __future__ import annotations

import json
import pathlib

from lib.research.survey.cli.contradiction_matrix_view import (
    format_contradiction_matrix,
    to_dict_contradiction_matrix,
)

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def _active_result() -> dict:
    return {
        "verdict": "pass",
        "verdict_reasons": [],
        "matrix_row_count": 3,
        "decorative": False,
        "rows": [
            {"claim_id": "c1", "synthesis_referenced": True, "supporting_count": 3, "contradicting_count": 1, "uncertain_count": 0},
            {"claim_id": "c2", "synthesis_referenced": True, "supporting_count": 2, "contradicting_count": 0, "uncertain_count": 1},
            {"claim_id": "c3", "synthesis_referenced": True, "supporting_count": 1, "contradicting_count": 2, "uncertain_count": 0},
        ],
    }


def _decorative_result() -> dict:
    return {
        "verdict": "warn",
        "verdict_reasons": ["decorative_matrix_warning"],
        "matrix_row_count": 2,
        "decorative": True,
        "rows": [
            {"claim_id": "c1", "synthesis_referenced": False, "supporting_count": 2, "contradicting_count": 0, "uncertain_count": 1},
            {"claim_id": "c2", "synthesis_referenced": False, "supporting_count": 1, "contradicting_count": 0, "uncertain_count": 0},
        ],
    }


# ---------------------------------------------------------------------------
# 1. format contains total_claims and claims_with_negative
# ---------------------------------------------------------------------------

def test_format_active_contains_fields():
    text = format_contradiction_matrix(_active_result())
    assert "total_claims:" in text
    assert "claims_with_negative:" in text
    assert "decorative" not in text or "false" in text.lower() or "[WARN]" not in text


# ---------------------------------------------------------------------------
# 2. claims_with_negative counts correctly
# ---------------------------------------------------------------------------

def test_claims_with_negative_count():
    text = format_contradiction_matrix(_active_result())
    # c1 has contradicting=1, c3 has contradicting=2 → 2 claims with negative
    assert "claims_with_negative: 2" in text


# ---------------------------------------------------------------------------
# 3. decorative=true triggers WARN line
# ---------------------------------------------------------------------------

def test_decorative_triggers_warn():
    text = format_contradiction_matrix(_decorative_result())
    assert "[WARN] decorative matrix" in text


# ---------------------------------------------------------------------------
# 4. view reads decorative from input, does not recompute
# ---------------------------------------------------------------------------

def test_view_reads_decorative_field():
    result = _active_result()
    result["decorative"] = True
    # Force decorative=True but rows have referenced=True — view should still warn
    text = format_contradiction_matrix(result)
    assert "[WARN] decorative matrix" in text


# ---------------------------------------------------------------------------
# 5. to_dict returns serializable dict
# ---------------------------------------------------------------------------

def test_to_dict_is_json_serializable():
    d = to_dict_contradiction_matrix(_active_result())
    serialized = json.dumps(d)
    parsed = json.loads(serialized)
    assert parsed["verdict"] == "pass"
    assert parsed["matrix_row_count"] == 3
    assert len(parsed["rows"]) == 3


# ---------------------------------------------------------------------------
# 6. Fixture: decorative matches schema
# ---------------------------------------------------------------------------

def test_decorative_fixture_matches():
    with open(FIXTURES / "contradiction_matrix_decorative.json") as f:
        fixture = json.load(f)
    d = to_dict_contradiction_matrix(_decorative_result())
    assert fixture["verdict"] == d["verdict"]
    assert fixture["decorative"] == d["decorative"]
    assert len(fixture["rows"]) == len(d["rows"])


# ---------------------------------------------------------------------------
# 7. Fixture: active matches schema
# ---------------------------------------------------------------------------

def test_active_fixture_matches():
    with open(FIXTURES / "contradiction_matrix_active.json") as f:
        fixture = json.load(f)
    d = to_dict_contradiction_matrix(_active_result())
    assert fixture["verdict"] == d["verdict"]
    assert fixture["matrix_row_count"] == d["matrix_row_count"]
    assert fixture["rows"][0]["claim_id"] == d["rows"][0]["claim_id"]
