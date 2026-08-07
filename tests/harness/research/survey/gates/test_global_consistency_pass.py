"""Tests for global_consistency_pass (QG-3 + QG-5)."""

from __future__ import annotations

import pytest

from lib.research.survey.gates.global_consistency_pass import (
    check_claim_id_reuse,
    check_terminology_drift,
    global_consistency_pass,
)


# ---------------------------------------------------------------------------
# 1. No conflicts — clean pass
# ---------------------------------------------------------------------------

def test_clean_pass():
    sections = [
        {"section_id": "s1", "claim_ids": ["c1", "c2"], "terms": ["Transformer"]},
        {"section_id": "s2", "claim_ids": ["c3", "c4"], "terms": ["Attention"]},
    ]
    report = global_consistency_pass(sections=sections)
    assert report.verdict == "pass"
    assert len(report.claim_id_conflicts) == 0


# ---------------------------------------------------------------------------
# 2. QG-3 claim_id reuse detected
# ---------------------------------------------------------------------------

def test_claim_id_reuse():
    sections = [
        {"section_id": "s1", "claim_ids": ["c1", "c2"], "terms": []},
        {"section_id": "s2", "claim_ids": ["c2", "c3"], "terms": []},
    ]
    report = global_consistency_pass(sections=sections)
    assert report.verdict == "warning"
    assert len(report.claim_id_conflicts) == 1
    assert report.claim_id_conflicts[0]["claim_id"] == "c2"
    assert report.claim_id_conflicts[0]["count"] == 2


# ---------------------------------------------------------------------------
# 3. QG-5 terminology drift detected
# ---------------------------------------------------------------------------

def test_terminology_drift():
    sections = [
        {"section_id": "s1", "claim_ids": [], "terms": ["Transformer"]},
        {"section_id": "s2", "claim_ids": [], "terms": ["transformer"]},
        {"section_id": "s3", "claim_ids": [], "terms": ["Transformers"]},
    ]
    report = global_consistency_pass(sections=sections)
    assert report.verdict == "warning"
    assert len(report.terminology_drift) >= 1
    drift = report.terminology_drift[0]
    assert "Transformer" in drift["forms"] or "transformer" in drift["forms"]


# ---------------------------------------------------------------------------
# 4. No input — not_applicable
# ---------------------------------------------------------------------------

def test_no_input():
    report = global_consistency_pass()
    assert report.verdict == "not_applicable"


# ---------------------------------------------------------------------------
# 5. Both claim reuse and term drift
# ---------------------------------------------------------------------------

def test_combined_issues():
    sections = [
        {"section_id": "s1", "claim_ids": ["c1"], "terms": ["LLM"]},
        {"section_id": "s2", "claim_ids": ["c1"], "terms": ["llm"]},
    ]
    report = global_consistency_pass(sections=sections)
    assert report.verdict == "warning"
    assert len(report.claim_id_conflicts) >= 1
    assert len(report.terminology_drift) >= 1
    assert len(report.issues) >= 2


# ---------------------------------------------------------------------------
# 6. Empty sections list — clean pass
# ---------------------------------------------------------------------------

def test_empty_sections():
    report = global_consistency_pass(sections=[])
    assert report.verdict == "pass"
