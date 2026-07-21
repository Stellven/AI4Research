"""Unit tests for harness/lib/research/schemas.py.

Test integrity: no @mock.patch — pure dataclass + invariant tests.
Validates field name set + invariants per S02 schemas.md.
"""

from __future__ import annotations

import sys
from pathlib import Path

_LIB_DIR = Path(__file__).resolve().parent.parent.parent / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

import pytest  # noqa: E402

import research  # noqa: E402
from research import hashing, ids, schemas  # noqa: E402


# ---------------------------------------------------------------------------
# Surface area: 8 core + 5 nested
# ---------------------------------------------------------------------------


class TestExports:
    def test_eight_core_models_present(self) -> None:
        names = {m.__name__ for m in schemas.CORE_MODELS}
        assert names == {
            "SourceConnector", "SourceHit", "SourceDocument",
            "EvidenceItem", "Claim", "ClaimEvidenceLink",
            "CitationSpan", "ReportAST",
        }
        assert len(schemas.CORE_MODELS) == 8

    def test_five_nested_models_present(self) -> None:
        names = {m.__name__ for m in schemas.NESTED_MODELS}
        assert names == {"Chapter", "Section", "Bibliography", "BibEntry", "QualityReport"}

    def test_schema_version_v1(self) -> None:
        assert research.SCHEMA_VERSION == "solar.deepresearch.schemas.v1"


# ---------------------------------------------------------------------------
# Field name fidelity to S02 schemas.md
# ---------------------------------------------------------------------------


SOURCE_CONNECTOR_FIELDS = {
    "connector_id", "connector_type", "source_tier", "display_name",
    "base_url", "auth_config", "rate_limit_rpm", "depth_tier",
    "status", "last_health_check", "capabilities",
    "created_at", "updated_at",
}

EVIDENCE_ITEM_FIELDS = {
    "evidence_id", "source_id", "source_type", "content_hash",
    "span_start", "span_end", "span_text",
    "section_path", "evidence_type", "relevance_score",
    "support_direction", "created_at", "schema_version",
}

REPORT_AST_FIELDS = {
    "ast_id", "sprint_id", "title", "depth_tier",
    "target_chars", "target_sections", "target_chapters",
    "status", "chapters", "bibliography", "quality_report",
    "created_at", "updated_at", "schema_version",
}


class TestFieldFidelity:
    def test_source_connector_field_set(self) -> None:
        assert set(schemas.model_field_names(schemas.SourceConnector)) == SOURCE_CONNECTOR_FIELDS

    def test_evidence_item_field_set(self) -> None:
        assert set(schemas.model_field_names(schemas.EvidenceItem)) == EVIDENCE_ITEM_FIELDS

    def test_report_ast_field_set(self) -> None:
        assert set(schemas.model_field_names(schemas.ReportAST)) == REPORT_AST_FIELDS


# ---------------------------------------------------------------------------
# SourceConnector invariants
# ---------------------------------------------------------------------------


def _valid_connector(**overrides) -> schemas.SourceConnector:
    base = dict(
        connector_id="sc_arxiv_192a",
        connector_type="arxiv",
        source_tier="academic",
        display_name="arXiv",
    )
    base.update(overrides)
    return schemas.SourceConnector(**base)


class TestSourceConnectorInvariants:
    def test_valid_connector_constructs(self) -> None:
        c = _valid_connector()
        assert c.depth_tier == 2
        assert c.capabilities == ["search"]

    def test_rejects_unknown_connector_type(self) -> None:
        with pytest.raises(ValueError, match="connector_type"):
            _valid_connector(connector_type="not_real")

    def test_rejects_bad_source_tier(self) -> None:
        with pytest.raises(ValueError, match="source_tier"):
            _valid_connector(source_tier="cosmic")

    def test_rejects_depth_tier_out_of_range(self) -> None:
        with pytest.raises(ValueError, match="depth_tier"):
            _valid_connector(depth_tier=5)
        with pytest.raises(ValueError, match="depth_tier"):
            _valid_connector(depth_tier=0)

    def test_rejects_unknown_capability(self) -> None:
        with pytest.raises(ValueError, match="capabilities"):
            _valid_connector(capabilities=["search", "summarize"])

    def test_rejects_bad_auth_config_type(self) -> None:
        with pytest.raises(ValueError, match="auth_config"):
            _valid_connector(auth_config={"type": "magic"})


# ---------------------------------------------------------------------------
# SourceHit invariants
# ---------------------------------------------------------------------------


class TestSourceHitInvariants:
    def test_valid_hit(self) -> None:
        h = schemas.SourceHit(
            hit_id="hit_x", connector_id="sc_x", query="q", rank=0, title="t",
        )
        assert h.fetch_status == "pending"

    def test_rejects_negative_rank(self) -> None:
        with pytest.raises(ValueError, match="rank"):
            schemas.SourceHit(
                hit_id="hit_x", connector_id="sc_x", query="q", rank=-1, title="t",
            )

    def test_rejects_empty_query(self) -> None:
        with pytest.raises(ValueError, match="query"):
            schemas.SourceHit(
                hit_id="hit_x", connector_id="sc_x", query="", rank=0, title="t",
            )

    def test_failed_status_requires_error(self) -> None:
        with pytest.raises(ValueError, match="fetch_error"):
            schemas.SourceHit(
                hit_id="hit_x", connector_id="sc_x", query="q", rank=0,
                title="t", fetch_status="failed",
            )


# ---------------------------------------------------------------------------
# SourceDocument + content_hash integrity
# ---------------------------------------------------------------------------


class TestSourceDocumentInvariants:
    def test_valid_document(self) -> None:
        text = "the quick brown fox"
        d = schemas.SourceDocument(
            doc_id="doc_x", connector_id="sc_x", title="t",
            raw_text=text, content_hash=hashing.content_hash(text),
            content_length=len(text),
        )
        assert d.language == "unknown"
        assert d.schema_version == "v1"

    def test_rejects_content_hash_mismatch(self) -> None:
        with pytest.raises(ValueError, match="content_hash"):
            schemas.SourceDocument(
                doc_id="doc_x", connector_id="sc_x", title="t",
                raw_text="real text",
                content_hash="0" * 64,
                content_length=len("real text"),
            )

    def test_rejects_content_length_mismatch(self) -> None:
        text = "twelve chars"
        with pytest.raises(ValueError, match="content_length"):
            schemas.SourceDocument(
                doc_id="doc_x", connector_id="sc_x", title="t",
                raw_text=text, content_hash=hashing.content_hash(text),
                content_length=999,
            )

    def test_rejects_empty_raw_text(self) -> None:
        with pytest.raises(ValueError, match="raw_text"):
            schemas.SourceDocument(
                doc_id="doc_x", connector_id="sc_x", title="t",
                raw_text="", content_hash=hashing.content_hash(""),
                content_length=0,
            )


# ---------------------------------------------------------------------------
# EvidenceItem provenance + integrity (the most-load-bearing invariants)
# ---------------------------------------------------------------------------


def _valid_evidence(**overrides) -> schemas.EvidenceItem:
    span_text = overrides.pop("span_text", "evidence span text")
    base = dict(
        source_id="doc_x",
        source_type="document",
        span_start=0,
        span_end=len(span_text),
        span_text=span_text,
        content_hash=hashing.content_hash(span_text),
    )
    base.update(overrides)
    if "evidence_id" not in base:
        base["evidence_id"] = ids.evidence_id(
            base["source_id"], base["span_start"], base["span_end"], base["content_hash"],
        )
    return schemas.EvidenceItem(**base)


class TestEvidenceItemInvariants:
    def test_valid_evidence(self) -> None:
        e = _valid_evidence()
        assert e.evidence_id.startswith("ev_")
        assert e.support_direction == "supporting"

    def test_rejects_missing_source_id(self) -> None:
        with pytest.raises(ValueError, match="source_id"):
            _valid_evidence(source_id="")

    def test_rejects_span_end_before_span_start(self) -> None:
        with pytest.raises(ValueError, match="span_end"):
            _valid_evidence(span_start=10, span_end=10)

    def test_rejects_negative_span_start(self) -> None:
        with pytest.raises(ValueError, match="span_start"):
            _valid_evidence(span_start=-1, span_end=4)

    def test_rejects_content_hash_mismatch(self) -> None:
        with pytest.raises(ValueError, match="content_hash"):
            schemas.EvidenceItem(
                evidence_id="ev_x", source_id="doc_x", source_type="document",
                content_hash="0" * 64,
                span_start=0, span_end=4, span_text="text",
            )

    def test_rejects_relevance_out_of_range(self) -> None:
        with pytest.raises(ValueError, match="relevance_score"):
            _valid_evidence(relevance_score=1.5)

    def test_rejects_bad_evidence_type(self) -> None:
        with pytest.raises(ValueError, match="evidence_type"):
            _valid_evidence(evidence_type="hallucinated")


# ---------------------------------------------------------------------------
# Claim + ClaimEvidenceLink invariants
# ---------------------------------------------------------------------------


class TestClaimInvariants:
    def test_valid_claim(self) -> None:
        c = schemas.Claim(
            claim_id="clm_0001_aaaaaaaa",
            claim_text="DeepResearch requires evidence.",
            section_path="ch1/sec1",
            source_method="extracted_from_evidence",
        )
        assert c.is_key is True
        assert c.support_rating == "unrated"

    def test_rejects_empty_claim_text(self) -> None:
        with pytest.raises(ValueError, match="claim_text"):
            schemas.Claim(
                claim_id="clm_0001_x", claim_text="",
                section_path="ch1/sec1", source_method="author_assertion",
            )

    def test_rejects_bad_source_method(self) -> None:
        with pytest.raises(ValueError, match="source_method"):
            schemas.Claim(
                claim_id="clm_0001_x", claim_text="ok",
                section_path="ch1/sec1", source_method="invented",
            )


class TestClaimEvidenceLinkInvariants:
    def test_valid_link(self) -> None:
        link = schemas.ClaimEvidenceLink(
            link_id="cel_x", claim_id="clm_0001_x", evidence_id="ev_x",
        )
        assert link.link_type == "supports"

    def test_rejects_bad_link_type(self) -> None:
        with pytest.raises(ValueError, match="link_type"):
            schemas.ClaimEvidenceLink(
                link_id="cel_x", claim_id="clm_0001_x", evidence_id="ev_x",
                link_type="undermines",
            )


# ---------------------------------------------------------------------------
# CitationSpan marker invariant
# ---------------------------------------------------------------------------


class TestCitationSpanInvariants:
    def test_valid_citation(self) -> None:
        cs = schemas.CitationSpan(
            citation_id="cit_x", evidence_id="ev_x", claim_id="clm_x",
            section_path="ch1/sec1", span_start=0, span_end=5, span_text="hello",
            marker_text="[cite:ev_x]", marker_position=10,
        )
        assert cs.verified is False

    def test_rejects_bad_marker_text(self) -> None:
        with pytest.raises(ValueError, match="marker_text"):
            schemas.CitationSpan(
                citation_id="cit_x", evidence_id="ev_x", claim_id="clm_x",
                section_path="ch1/sec1", span_start=0, span_end=5, span_text="hello",
                marker_text="see paper",  # missing [cite:...] format
                marker_position=10,
            )

    def test_verified_true_requires_verification_result(self) -> None:
        with pytest.raises(ValueError, match="verification_result"):
            schemas.CitationSpan(
                citation_id="cit_x", evidence_id="ev_x", claim_id="clm_x",
                section_path="ch1/sec1", span_start=0, span_end=5, span_text="hello",
                marker_text="[cite:ev_x]", marker_position=10,
                verified=True, verification_result=None,
            )


# ---------------------------------------------------------------------------
# ReportAST nested structure invariants
# ---------------------------------------------------------------------------


class TestReportASTInvariants:
    def _make_section(self, chapter_n: int, n: int) -> schemas.Section:
        return schemas.Section(
            section_id=f"ch{chapter_n}/sec{n}",
            title=f"Section {n}", order=n,
        )

    def test_valid_empty_report(self) -> None:
        r = schemas.ReportAST(
            ast_id="ast_x", sprint_id="sp", title="t",
            target_chars=100000, target_sections=0, target_chapters=0,
        )
        assert r.status == "drafting"
        assert r.chapters == []

    def test_valid_with_chapters(self) -> None:
        ch1 = schemas.Chapter(
            chapter_id="ch1", title="C1", order=1,
            sections=[self._make_section(1, 1), self._make_section(1, 2)],
        )
        ch2 = schemas.Chapter(
            chapter_id="ch2", title="C2", order=2,
            sections=[self._make_section(2, 1)],
        )
        r = schemas.ReportAST(
            ast_id="ast_x", sprint_id="sp", title="t",
            target_chars=10000, target_sections=3, target_chapters=2,
            chapters=[ch1, ch2],
        )
        assert r.target_sections == 3

    def test_rejects_section_max_chars_over_ceiling(self) -> None:
        with pytest.raises(ValueError, match="ceiling"):
            schemas.Section(
                section_id="ch1/sec1", title="t", order=1, max_chars=8000,
            )

    def test_rejects_target_sections_mismatch(self) -> None:
        ch1 = schemas.Chapter(
            chapter_id="ch1", title="C1", order=1,
            sections=[self._make_section(1, 1)],
        )
        with pytest.raises(ValueError, match="target_sections"):
            schemas.ReportAST(
                ast_id="ast_x", sprint_id="sp", title="t",
                target_chars=10000, target_sections=99, target_chapters=1,
                chapters=[ch1],
            )

    def test_rejects_noncontiguous_chapter_order(self) -> None:
        ch1 = schemas.Chapter(chapter_id="ch1", title="C1", order=1)
        ch3 = schemas.Chapter(chapter_id="ch3", title="C3", order=3)
        with pytest.raises(ValueError, match="contiguous"):
            schemas.ReportAST(
                ast_id="ast_x", sprint_id="sp", title="t",
                target_chars=10000, target_sections=0, target_chapters=2,
                chapters=[ch1, ch3],
            )

    def test_rejects_bad_depth_tier(self) -> None:
        with pytest.raises(ValueError, match="depth_tier"):
            schemas.ReportAST(
                ast_id="ast_x", sprint_id="sp", title="t", depth_tier=5,
                target_chars=1, target_sections=0, target_chapters=0,
            )


# ---------------------------------------------------------------------------
# Introspection helpers
# ---------------------------------------------------------------------------


class TestIntrospection:
    def test_model_field_names_returns_tuple(self) -> None:
        names = schemas.model_field_names(schemas.SourceConnector)
        assert isinstance(names, tuple)
        assert "connector_id" in names

    def test_to_dict_roundtrip(self) -> None:
        c = _valid_connector()
        d = schemas.to_dict(c)
        assert d["connector_id"] == "sc_arxiv_192a"
        # Reconstruct from dict
        c2 = schemas.SourceConnector(**d)
        assert c2 == c
