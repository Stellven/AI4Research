"""Tests for research/schemas.py: all 8+ dataclass models.

Acceptance:
- Schema model field names match spec
- Enum validation rejects unknown values
- Content hash integrity enforced in SourceDocument and EvidenceItem
- Claim text length constraint enforced
- ReportAST chapter order contiguity enforced
- Zero @mock.patch — all tests use real dataclasses and real storage
"""

from __future__ import annotations

import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parent.parent.parent.parent / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

import pytest

from research.schemas import (
    BibEntry, Bibliography, Chapter, Claim, ClaimEvidenceLink, CitationSpan,
    CONNECTOR_TYPES, EVIDENCE_SOURCE_TYPES, EVIDENCE_TYPES, LINK_TYPES,
    QualityReport, REPORT_STATUSES, ReportAST, Section,
    SECTION_MAX_CHARS_CEILING, SECTION_MIN_CHARS_FLOOR,
    SOURCE_TIERS, SUPPORT_DIRECTIONS, SUPPORT_RATINGS, CORE_MODELS, NESTED_MODELS,
    SourceConnector, SourceDocument, SourceHit, EvidenceItem, model_field_names, to_dict,
)


class TestSchemaConstants:
    def test_connector_types_is_frozenset(self):
        assert isinstance(CONNECTOR_TYPES, frozenset)
        assert "brave" in CONNECTOR_TYPES
        assert "internal_mirage" in CONNECTOR_TYPES

    def test_evidence_types_covers_spec(self):
        assert "direct_quote" in EVIDENCE_TYPES
        assert "finding" in EVIDENCE_TYPES
        assert "methodology" in EVIDENCE_TYPES

    def test_support_directions_includes_neutral(self):
        assert "neutral" in SUPPORT_DIRECTIONS

    def test_support_ratings_includes_unrated(self):
        assert "unrated" in SUPPORT_RATINGS

    def test_report_statuses_covers_full_lifecycle(self):
        assert "drafting" in REPORT_STATUSES
        assert "completed" in REPORT_STATUSES
        assert "failed" in REPORT_STATUSES


class TestSourceConnector:
    def test_valid_connector(self):
        sc = SourceConnector(
            connector_id="sc_test_123", connector_type="brave",
            source_tier="academic", display_name="Test",
        )
        assert sc.connector_type == "brave"
        assert sc.status == "active"

    def test_rejects_unknown_connector_type(self):
        with pytest.raises(ValueError, match="connector_type"):
            SourceConnector(
                connector_id="sc_x", connector_type="fake_type",
                source_tier="academic", display_name="X",
            )

    def test_rejects_unknown_source_tier(self):
        with pytest.raises(ValueError, match="source_tier"):
            SourceConnector(
                connector_id="sc_x", connector_type="brave",
                source_tier="fake", display_name="X",
            )

    def test_rejects_invalid_depth_tier(self):
        with pytest.raises(ValueError, match="depth_tier"):
            SourceConnector(
                connector_id="sc_x", connector_type="brave",
                source_tier="academic", display_name="X", depth_tier=5,
            )

    def test_rejects_zero_depth_tier(self):
        with pytest.raises(ValueError, match="depth_tier"):
            SourceConnector(
                connector_id="sc_x", connector_type="brave",
                source_tier="academic", display_name="X", depth_tier=0,
            )

    def test_rejects_unknown_status(self):
        with pytest.raises(ValueError, match="status"):
            SourceConnector(
                connector_id="sc_x", connector_type="brave",
                source_tier="academic", display_name="X", status="unknown",
            )

    def test_rejects_empty_capabilities(self):
        with pytest.raises(ValueError, match="capabilities must be non-empty"):
            SourceConnector(
                connector_id="sc_x", connector_type="brave",
                source_tier="academic", display_name="X", capabilities=[],
            )

    def test_rejects_unknown_capabilities(self):
        with pytest.raises(ValueError, match="unknown values"):
            SourceConnector(
                connector_id="sc_x", connector_type="brave",
                source_tier="academic", display_name="X", capabilities=["search", "teleport"],
            )

    def test_auth_config_none_ok(self):
        sc = SourceConnector(
            connector_id="sc_x", connector_type="brave",
            source_tier="academic", display_name="X", auth_config=None,
        )
        assert sc.auth_config is None

    def test_auth_config_valid_type(self):
        sc = SourceConnector(
            connector_id="sc_x", connector_type="brave",
            source_tier="academic", display_name="X",
            auth_config={"type": "env_var", "key": "BRAVE_API_KEY"},
        )
        assert sc.auth_config["type"] == "env_var"

    def test_auth_config_invalid_type(self):
        with pytest.raises(ValueError, match="auth_config.type"):
            SourceConnector(
                connector_id="sc_x", connector_type="brave",
                source_tier="academic", display_name="X",
                auth_config={"type": "invalid"},
            )


class TestSourceHit:
    def test_valid_hit(self):
        hit = SourceHit(
            hit_id="hit_abc", connector_id="sc_test", query="test query",
            rank=0, title="Test Hit",
        )
        assert hit.fetch_status == "pending"

    def test_rejects_negative_rank(self):
        with pytest.raises(ValueError, match="rank"):
            SourceHit(
                hit_id="hit_x", connector_id="sc_test", query="q",
                rank=-1, title="X",
            )

    def test_rejects_empty_query(self):
        with pytest.raises(ValueError, match="query must be non-empty"):
            SourceHit(
                hit_id="hit_x", connector_id="sc_test", query="",
                rank=0, title="X",
            )

    def test_rejects_oversized_query(self):
        long_q = "x" * 501
        with pytest.raises(ValueError, match="<= 500 chars"):
            SourceHit(
                hit_id="hit_x", connector_id="sc_test", query=long_q,
                rank=0, title="X",
            )

    def test_failed_requires_error(self):
        with pytest.raises(ValueError, match="fetch_error"):
            SourceHit(
                hit_id="hit_x", connector_id="sc_test", query="q",
                rank=0, title="X", fetch_status="failed",
                fetch_error=None,
            )


class TestSourceDocument:
    def test_valid_document(self):
        from research.hashing import content_hash
        text = "Hello world document content"
        sd = SourceDocument(
            doc_id="doc_abc", connector_id="sc_test", title="Test",
            raw_text=text, content_hash=content_hash(text), content_length=len(text),
        )
        assert sd.content_length == len(text)

    def test_rejects_empty_text(self):
        with pytest.raises(ValueError, match="raw_text must be non-empty"):
            SourceDocument(
                doc_id="doc_x", connector_id="sc_test", title="X",
                raw_text="", content_hash="h", content_length=0,
            )

    def test_rejects_length_mismatch(self):
        with pytest.raises(ValueError, match="content_length"):
            SourceDocument(
                doc_id="doc_x", connector_id="sc_test", title="X",
                raw_text="hello", content_hash="h", content_length=999,
            )

    def test_rejects_hash_mismatch(self):
        with pytest.raises(ValueError, match="content_hash mismatch"):
            SourceDocument(
                doc_id="doc_x", connector_id="sc_test", title="X",
                raw_text="hello", content_hash="badhash0000000000000000000000000000000000000",
                content_length=5,
            )

    def test_authority_score_bounds(self):
        from research.hashing import content_hash
        sd = SourceDocument(
            doc_id="doc_x", connector_id="sc_test", title="X",
            raw_text="text", content_hash=content_hash("text"), content_length=4,
            authority_score=0.5,
        )
        assert sd.authority_score == 0.5

    def test_rejects_authority_out_of_range(self):
        from research.hashing import content_hash
        with pytest.raises(ValueError, match="authority_score must be in"):
            SourceDocument(
                doc_id="doc_x", connector_id="sc_test", title="X",
                raw_text="text", content_hash=content_hash("text"), content_length=4,
                authority_score=1.5,
            )


class TestEvidenceItem:
    def test_valid_evidence(self):
        from research.hashing import content_hash
        text = "evidence span text"
        ei = EvidenceItem(
            evidence_id="ev_abc", source_id="doc_123", source_type="document",
            content_hash=content_hash(text), span_start=0, span_end=len(text),
            span_text=text,
        )
        assert ei.evidence_type == "direct_quote"
        assert ei.relevance_score == 0.5

    def test_rejects_empty_source_id(self):
        from research.hashing import content_hash
        with pytest.raises(ValueError, match="source_id must be non-null"):
            EvidenceItem(
                evidence_id="ev_x", source_id="", source_type="document",
                content_hash=content_hash("t"), span_start=0, span_end=1, span_text="t",
            )

    def test_rejects_unknown_source_type(self):
        from research.hashing import content_hash
        with pytest.raises(ValueError, match="source_type"):
            EvidenceItem(
                evidence_id="ev_x", source_id="doc_1",
                content_hash=content_hash("t"), span_start=0, span_end=1, span_text="t",
                source_type="audio",
            )

    def test_rejects_negative_span_start(self):
        from research.hashing import content_hash
        with pytest.raises(ValueError, match="span_start must be >= 0"):
            EvidenceItem(
                evidence_id="ev_x", source_id="doc_1", source_type="document",
                content_hash=content_hash("t"), span_start=-1, span_end=1, span_text="t",
            )

    def test_rejects_span_end_not_greater_than_start(self):
        from research.hashing import content_hash
        with pytest.raises(ValueError, match="span_end.*must be > span_start"):
            EvidenceItem(
                evidence_id="ev_x", source_id="doc_1", source_type="document",
                content_hash=content_hash("t"), span_start=5, span_end=5, span_text="t",
            )

    def test_rejects_empty_span_text(self):
        from research.hashing import content_hash
        with pytest.raises(ValueError, match="span_text must be non-empty"):
            EvidenceItem(
                evidence_id="ev_x", source_id="doc_1", source_type="document",
                content_hash="a" * 64, span_start=0, span_end=1, span_text="",
            )

    def test_rejects_hash_mismatch(self):
        with pytest.raises(ValueError, match="content_hash mismatch"):
            EvidenceItem(
                evidence_id="ev_x", source_id="doc_1", source_type="document",
                content_hash="badhash0000000000000000000000000000000",
                span_start=0, span_end=3, span_text="abc",
            )

    def test_rejects_unknown_evidence_type(self):
        from research.hashing import content_hash
        with pytest.raises(ValueError, match="evidence_type"):
            EvidenceItem(
                evidence_id="ev_x", source_id="doc_1", source_type="document",
                content_hash=content_hash("t"), span_start=0, span_end=1, span_text="t",
                evidence_type="hearsay",
            )

    def test_relevance_score_bounds(self):
        from research.hashing import content_hash
        ei = EvidenceItem(
            evidence_id="ev_x", source_id="doc_1", source_type="document",
            content_hash=content_hash("t"), span_start=0, span_end=1, span_text="t",
            relevance_score=0.0,
        )
        assert ei.relevance_score == 0.0

    def test_rejects_relevance_out_of_range(self):
        from research.hashing import content_hash
        with pytest.raises(ValueError, match="relevance_score"):
            EvidenceItem(
                evidence_id="ev_x", source_id="doc_1", source_type="document",
                content_hash=content_hash("t"), span_start=0, span_end=1, span_text="t",
                relevance_score=1.5,
            )


class TestClaim:
    def test_valid_claim(self):
        claim = Claim(
            claim_id="clm_0001_abc", claim_text="AI models can hallucinate",
            section_path="ch1/sec1", source_method="extracted_from_evidence",
        )
        assert claim.is_key is True
        assert claim.support_rating == "unrated"

    def test_rejects_empty_text(self):
        with pytest.raises(ValueError, match="claim_text must be non-empty"):
            Claim(
                claim_id="clm_0001_a", claim_text="", section_path="ch1/sec1",
                source_method="extracted_from_evidence",
            )

    def test_rejects_oversized_text(self):
        with pytest.raises(ValueError, match="<= 500 chars"):
            Claim(
                claim_id="clm_0001_a", claim_text="x" * 501,
                section_path="ch1/sec1", source_method="extracted_from_evidence",
            )

    def test_rejects_unknown_claim_type(self):
        with pytest.raises(ValueError, match="claim_type"):
            Claim(
                claim_id="clm_0001_a", claim_text="text",
                section_path="ch1/sec1", source_method="extracted_from_evidence",
                claim_type="speculative",
            )

    def test_rejects_unknown_support_rating(self):
        with pytest.raises(ValueError, match="support_rating"):
            Claim(
                claim_id="clm_0001_a", claim_text="text",
                section_path="ch1/sec1", source_method="extracted_from_evidence",
                support_rating="terrible",
            )

    def test_rejects_unknown_source_method(self):
        with pytest.raises(ValueError, match="source_method"):
            Claim(
                claim_id="clm_0001_a", claim_text="text",
                section_path="ch1/sec1", source_method="guessed",
            )

    def test_confidence_bounds(self):
        claim = Claim(
            claim_id="clm_0001_a", claim_text="text",
            section_path="ch1/sec1", source_method="extracted_from_evidence",
            confidence=0.0,
        )
        assert claim.confidence == 0.0

    def test_rejects_confidence_out_of_range(self):
        with pytest.raises(ValueError, match="confidence must be in"):
            Claim(
                claim_id="clm_0001_a", claim_text="text",
                section_path="ch1/sec1", source_method="extracted_from_evidence",
                confidence=1.5,
            )


class TestClaimEvidenceLink:
    def test_valid_link(self):
        cel = ClaimEvidenceLink(
            link_id="cel_abc", claim_id="clm_001_x", evidence_id="ev_002_y",
        )
        assert cel.link_type == "supports"
        assert cel.is_primary is False

    def test_rejects_unknown_link_type(self):
        with pytest.raises(ValueError, match="link_type"):
            ClaimEvidenceLink(
                link_id="cel_x", claim_id="clm_1", evidence_id="ev_2", link_type="destroys",
            )

    def test_relevance_score_bounds(self):
        cel = ClaimEvidenceLink(
            link_id="cel_x", claim_id="clm_1", evidence_id="ev_2", relevance_score=1.0,
        )
        assert cel.relevance_score == 1.0

    def test_rejects_relevance_out_of_range(self):
        with pytest.raises(ValueError, match="relevance_score must be in"):
            ClaimEvidenceLink(
                link_id="cel_x", claim_id="clm_1", evidence_id="ev_2", relevance_score=2.0,
            )


class TestCitationSpan:
    def test_valid_citation(self):
        cit = CitationSpan(
            citation_id="cit_abc", evidence_id="ev_1", claim_id="clm_2",
            section_path="ch1/sec1", span_start=0, span_end=4, span_text="data",
            marker_text="[cite:ev_1]", marker_position=10,
            verified=True, verification_result="match",
        )
        assert cit.verified is True
        assert cit.verification_result == "match"

    def test_rejects_empty_span_text(self):
        with pytest.raises(ValueError, match="span_text must be non-empty"):
            CitationSpan(
                citation_id="cit_x", evidence_id="ev_1", claim_id="clm_2",
                section_path="ch1/sec1", span_start=0, span_end=4, span_text="",
                marker_text="[cite:ev_1]", marker_position=10,
            )

    def test_rejects_invalid_marker_format(self):
        with pytest.raises(ValueError, match="marker_text must match"):
            CitationSpan(
                citation_id="cit_x", evidence_id="ev_1", claim_id="clm_2",
                section_path="ch1/sec1", span_start=0, span_end=4, span_text="data",
                marker_text="(ref:ev_1)", marker_position=10,
            )

    def test_rejects_verified_without_result(self):
        with pytest.raises(ValueError, match="verification_result must be set"):
            CitationSpan(
                citation_id="cit_x", evidence_id="ev_1", claim_id="clm_2",
                section_path="ch1/sec1", span_start=0, span_end=4, span_text="data",
                marker_text="[cite:ev_1]", marker_position=10, verified=True,
            )

    def test_rejects_unknown_verification_result(self):
        with pytest.raises(ValueError, match="verification_result"):
            CitationSpan(
                citation_id="cit_x", evidence_id="ev_1", claim_id="clm_2",
                section_path="ch1/sec1", span_start=0, span_end=4, span_text="data",
                marker_text="[cite:ev_1]", marker_position=10,
                verification_result="kinda_match",
            )


class TestReportStructures:
    def test_section_max_chars_ceiling(self):
        assert SECTION_MAX_CHARS_CEILING == 4000
        assert SECTION_MIN_CHARS_FLOOR == 1500

    def test_valid_report_ast(self):
        sec = Section(section_id="ch1/sec1", title="Intro", order=1)
        ch = Chapter(chapter_id="ch1", title="Chapter 1", order=1, sections=[sec])
        ast = ReportAST(
            ast_id="ast_abc", sprint_id="sprint_001", title="Report",
            target_chars=1000, target_sections=1, target_chapters=1,
            chapters=[ch],
        )
        assert ast.status == "drafting"

    def test_rejects_chapter_count_mismatch(self):
        sec = Section(section_id="ch1/sec1", title="Intro", order=1)
        ch = Chapter(chapter_id="ch1", title="Chapter 1", order=1, sections=[sec])
        with pytest.raises(ValueError, match="target_chapters"):
            ReportAST(
                ast_id="ast_abc", sprint_id="s1", title="R",
                target_chars=1000, target_sections=1, target_chapters=99,
                chapters=[ch],
            )

    def test_rejects_noncontiguous_chapter_orders(self):
        s1 = Section(section_id="ch1/sec1", title="S1", order=1)
        s2 = Section(section_id="ch2/sec1", title="S2", order=1)
        ch1 = Chapter(chapter_id="ch1", title="Ch1", order=1, sections=[s1])
        ch3 = Chapter(chapter_id="ch3", title="Ch3", order=3, sections=[s2])
        with pytest.raises(ValueError, match="chapter orders must be"):
            ReportAST(
                ast_id="ast_x", sprint_id="s1", title="R",
                target_chars=1000, target_sections=2, target_chapters=2,
                chapters=[ch1, ch3],
            )

    def test_core_models_count(self):
        assert len(CORE_MODELS) >= 8

    def test_to_dict_returns_dict(self):
        from research.hashing import content_hash
        ei = EvidenceItem(
            evidence_id="ev_x", source_id="doc_1", source_type="document",
            content_hash=content_hash("t"), span_start=0, span_end=1, span_text="t",
        )
        d = to_dict(ei)
        assert isinstance(d, dict)
        assert d["source_id"] == "doc_1"

    def test_model_field_names(self):
        names = model_field_names(EvidenceItem)
        assert "span_text" in names
        assert "evidence_id" in names
