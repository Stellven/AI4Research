"""Tests for gates/controversy_matrix.py — O3 Contradiction Matrix.

S03 N5 tests per S02 contradiction-matrix-arch.md.
No mocks, no randomness, no network calls.
"""

from __future__ import annotations

import sys
from pathlib import Path

_LIB_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

import pytest

from research.survey.gates._registry import _registry
from research.survey.gates.config_defaults import CLAIM_GRANULARITY
from research.survey.schemas import ClaimEvidenceLink, ContradictionMatrix, to_dict

from research.survey.gates.controversy_matrix import (
    MissingRef,
    SynthesisReferenceReport,
    build_contradiction_matrix,
    check_synthesis_references,
    controversy_gate,
    detect_decorative_matrix,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _pack(claim_ids=None, section_id="s1.1"):
    return {
        "pack_id": "pack_test",
        "section_id": section_id,
        "claim_ids": claim_ids if claim_ids is not None else ["c1"],
        "contradiction_slots": ["contradiction:s1.1:required"],
        "source_ids": [],
        "source_types": [],
        "evidence_ids": [],
        "status": "ready",
        "blockers": [],
    }


def _link(claim_id, evidence_id, source_id, relation_type, strength="moderate"):
    return {
        "claim_id": claim_id,
        "evidence_id": evidence_id,
        "source_id": source_id,
        "relation_type": relation_type,
        "relation_strength": strength,
    }


# ---------------------------------------------------------------------------
# build_contradiction_matrix
# ---------------------------------------------------------------------------


class TestBuildMatrix:
    def test_basic_matrix_with_three_relation_types(self):
        rows = build_contradiction_matrix(
            _pack(claim_ids=["c1"]),
            [
                _link("c1", "e1", "s1", "supporting"),
                _link("c1", "e2", "s2", "contradicting"),
                _link("c1", "e3", "s3", "uncertain"),
            ],
            claim_texts={"c1": "Model X outperforms Y on benchmark Z"},
            source_type_map={"s1": "paper", "s2": "code", "s3": "benchmark"},
        )
        assert len(rows) == 1
        r = rows[0]
        assert r.claim_id == "c1"
        assert r.claim_text == "Model X outperforms Y on benchmark Z"
        assert len(r.supporting_evidence) == 1
        assert len(r.contradicting_evidence) == 1
        assert len(r.uncertain_evidence) == 1
        assert r.supporting_evidence[0].source_type == "paper"
        assert r.contradicting_evidence[0].source_type == "code"
        assert not r.synthesis_referenced

    def test_multiple_claims(self):
        rows = build_contradiction_matrix(
            _pack(claim_ids=["c1", "c2"]),
            [
                _link("c1", "e1", "s1", "supporting"),
                _link("c2", "e2", "s2", "contradicting"),
            ],
        )
        assert len(rows) == 2
        assert rows[0].claim_id == "c1"
        assert rows[1].claim_id == "c2"

    def test_empty_claim_evidence(self):
        rows = build_contradiction_matrix(_pack(claim_ids=["c1"]), [])
        assert len(rows) == 1
        assert rows[0].supporting_evidence == []
        assert rows[0].contradicting_evidence == []
        assert rows[0].uncertain_evidence == []

    def test_unknown_relation_type_goes_to_empty(self):
        rows = build_contradiction_matrix(
            _pack(claim_ids=["c1"]),
            [_link("c1", "e1", "s1", "tangential")],
        )
        assert len(rows) == 1
        assert rows[0].supporting_evidence == []
        assert rows[0].contradicting_evidence == []
        assert rows[0].uncertain_evidence == []

    def test_chapter_map_assigns_chapter(self):
        rows = build_contradiction_matrix(
            _pack(claim_ids=["c1"], section_id="sec_1"),
            [],
            chapter_map={"sec_1": "ch_1"},
        )
        assert rows[0].chapter_ids == ["ch_1"]

    def test_to_dict_roundtrip(self):
        rows = build_contradiction_matrix(
            _pack(claim_ids=["c1"]),
            [_link("c1", "e1", "s1", "supporting", "strong")],
            source_type_map={"s1": "paper"},
        )
        d = to_dict(rows[0])
        assert d["claim_id"] == "c1"
        assert d["supporting_evidence"][0]["source_type"] == "paper"
        assert d["supporting_evidence"][0]["relation_strength"] == "strong"


# ---------------------------------------------------------------------------
# check_synthesis_references
# ---------------------------------------------------------------------------


class TestSynthesisReferences:
    def _matrix(self, claim_ids):
        return [
            ContradictionMatrix(
                claim_id=cid,
                claim_text="",
                supporting_evidence=[],
                contradicting_evidence=[],
                uncertain_evidence=[],
                chapter_ids=[],
                synthesis_referenced=False,
            )
            for cid in claim_ids
        ]

    def test_full_reference_pass(self):
        rows = self._matrix(["c1", "c2"])
        syntheses = [
            {"chapter_id": "ch1", "synthesis_text": "As shown in [claim:c1]."},
            {"chapter_id": "ch2", "synthesis_text": "The claim c2 is supported."},
        ]
        report = check_synthesis_references(rows, syntheses)
        assert report.unreferenced_chapters == []
        assert not report.decorative_warning
        assert report.per_claim_reference_count["c1"] == 1
        assert report.per_claim_reference_count["c2"] == 1
        assert rows[0].synthesis_referenced is True

    def test_unreferenced_chapter_detected(self):
        rows = self._matrix(["c1"])
        syntheses = [
            {"chapter_id": "ch1", "synthesis_text": "Some text without claims."},
            {"chapter_id": "ch2", "synthesis_text": "See [claim:c1]."},
        ]
        report = check_synthesis_references(rows, syntheses)
        assert "ch1" in report.unreferenced_chapters
        assert "ch2" not in report.unreferenced_chapters

    def test_decorative_warning(self):
        rows = self._matrix(["c1", "c2"])
        syntheses = [
            {"chapter_id": "ch1", "synthesis_text": "No references here."},
        ]
        report = check_synthesis_references(rows, syntheses)
        assert report.decorative_warning is True
        assert report.per_claim_reference_count == {"c1": 0, "c2": 0}

    def test_empty_matrix_no_decorative(self):
        report = check_synthesis_references([], [])
        assert not report.decorative_warning


# ---------------------------------------------------------------------------
# detect_decorative_matrix
# ---------------------------------------------------------------------------


class TestDetectDecorative:
    def test_all_unreferenced_is_decorative(self):
        rows = [
            ContradictionMatrix("c1", "", [], [], [], [], False),
            ContradictionMatrix("c2", "", [], [], [], [], False),
        ]
        assert detect_decorative_matrix(rows) is True

    def test_any_referenced_not_decorative(self):
        rows = [
            ContradictionMatrix("c1", "", [], [], [], [], True),
            ContradictionMatrix("c2", "", [], [], [], [], False),
        ]
        assert detect_decorative_matrix(rows) is False

    def test_empty_matrix_not_decorative(self):
        assert detect_decorative_matrix([]) is False


# ---------------------------------------------------------------------------
# Gate registration + end-to-end
# ---------------------------------------------------------------------------


class TestGateRegistration:
    def test_controversy_registered(self):
        fn = _registry.get("controversy")
        assert fn is controversy_gate

    def test_gate_e2e_normal(self):
        result = controversy_gate(
            _pack(claim_ids=["c1"]),
            [
                _link("c1", "e1", "s1", "supporting"),
                _link("c1", "e2", "s2", "contradicting"),
            ],
            source_type_map={"s1": "paper", "s2": "benchmark"},
            chapter_syntheses=[
                {"chapter_id": "ch1", "synthesis_text": "Ref [claim:c1] shows."},
            ],
        )
        assert result["verdict"] == "pass"
        assert result["matrix_row_count"] == 1
        assert not result["decorative"]

    def test_gate_e2e_decorative(self):
        result = controversy_gate(
            _pack(claim_ids=["c1"]),
            [_link("c1", "e1", "s1", "supporting")],
            chapter_syntheses=[
                {"chapter_id": "ch1", "synthesis_text": "No refs."},
            ],
        )
        assert result["verdict"] == "warn"
        assert "decorative_matrix_warning" in result["verdict_reasons"]

    def test_gate_e2e_empty_matrix(self):
        result = controversy_gate(
            _pack(claim_ids=[]),
            [],
        )
        assert result["verdict"] == "warn"
        assert "empty_matrix" in result["verdict_reasons"]

    def test_uses_claim_granularity(self):
        assert CLAIM_GRANULARITY == "dual_indexing"
