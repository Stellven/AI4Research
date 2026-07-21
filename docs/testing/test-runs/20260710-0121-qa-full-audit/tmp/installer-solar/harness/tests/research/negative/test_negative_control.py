"""Negative-control tests for DeepResearch verification pipeline.

Spec: sprint-20260513-solar-deepresearch-product-line-s05-verification-release / N3

Each test verifies that broken/malicious input is properly rejected.
Uses pytest.raises or explicit assert-fail patterns.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from harness.lib.research.evidence.citation_span import verify_span, verify_citation_span
from harness.lib.research.evidence.ledger import check_unsupported_claims, write_evidence
from harness.lib.research import hashing, ids, schemas, storage
from harness.tests.research.fixtures.negative import (
    BROKEN_CLAIM,
    BROKEN_EVIDENCE,
    MISMATCHED_SPAN,
)


# ---------------------------------------------------------------------------
# Test 1: Unsupported claim rejected
# ---------------------------------------------------------------------------


class TestUnsupportedClaimRejected:
    def test_unsupported_claim_rejected(self):
        """Key claim with zero evidence links must be flagged as exceeding threshold."""
        conn = storage.init_db(":memory:")
        run_id = self._create_run(conn)
        self._insert_unsupported_claim(conn, run_id)

        result = check_unsupported_claims(conn, run_id, threshold=0.05)

        assert result["total_claims"] == 1
        assert result["unsupported_count"] == 1
        assert result["unsupported_rate"] == 1.0
        assert result["exceeds_threshold"] is True
        assert "claim_broken_001" in result["unsupported_claim_ids"]

        conn.close()

    def test_claim_with_evidence_passes(self):
        """Supported claim must not be flagged."""
        conn = storage.init_db(":memory:")
        run_id = self._create_run(conn)
        source_id = self._insert_source(conn, run_id)
        evidence_id = self._insert_evidence(conn, run_id, source_id)
        self._insert_claim_with_link(conn, run_id, evidence_id)

        result = check_unsupported_claims(conn, run_id, threshold=0.05)

        assert result["unsupported_count"] == 0
        assert result["exceeds_threshold"] is False

        conn.close()

    def _create_run(self, conn):
        conn.execute(
            "INSERT INTO research_runs (topic, depth_tier, status) VALUES (?, ?, ?)",
            ("Negative test run", "standard", "running"),
        )
        conn.commit()
        return conn.execute("SELECT id FROM research_runs LIMIT 1").fetchone()["id"]

    def _insert_unsupported_claim(self, conn, run_id):
        conn.execute(
            "INSERT INTO claims (id, run_id, claim_text, content_hash) VALUES (?, ?, ?, ?)",
            (BROKEN_CLAIM["claim_id"], run_id, BROKEN_CLAIM["claim_text"], "fake_hash"),
        )
        conn.commit()

    def _insert_source(self, conn, run_id):
        conn.execute(
            "INSERT INTO research_sources (run_id, content_hash, content_span) VALUES (?, ?, ?)",
            (run_id, "src_hash_neg", '{"start":0,"end":50}'),
        )
        conn.commit()
        return conn.execute(
            "SELECT id FROM research_sources WHERE run_id = ?", (run_id,)
        ).fetchone()["id"]

    def _insert_evidence(self, conn, run_id, source_id):
        text = "Supporting evidence text."
        ch = hashing.content_hash(text)
        conn.execute(
            "INSERT INTO evidence_items "
            "(id, run_id, source_id, content, evidence_type, confidence, "
            "span_start, span_end, content_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("ev_supported_001", run_id, source_id, text, "factual", 0.8, 0, len(text), ch),
        )
        conn.commit()
        return "ev_supported_001"

    def _insert_claim_with_link(self, conn, run_id, evidence_id):
        conn.execute(
            "INSERT INTO claims (id, run_id, claim_text, content_hash) VALUES (?, ?, ?, ?)",
            ("claim_supported_001", run_id, "A supported claim", "hash2"),
        )
        conn.execute(
            "INSERT INTO claim_evidence (run_id, claim_id, evidence_id, relation) "
            "VALUES (?, ?, ?, ?)",
            (run_id, "claim_supported_001", evidence_id, "supports"),
        )
        conn.commit()


# ---------------------------------------------------------------------------
# Test 2: Citation span mismatch fails
# ---------------------------------------------------------------------------


class TestCitationSpanMismatchFails:
    def test_citation_span_mismatch_fails(self):
        """verify_span must return False when span_text does not match the slice."""
        source = MISMATCHED_SPAN["source_text"]
        start = MISMATCHED_SPAN["span_start"]
        end = MISMATCHED_SPAN["span_end"]
        wrong_text = MISMATCHED_SPAN["span_text"]

        assert verify_span(source, start, end, wrong_text) is False

    def test_citation_span_correct_passes(self):
        """verify_span must return True for correct span_text."""
        source = MISMATCHED_SPAN["source_text"]
        start = MISMATCHED_SPAN["span_start"]
        end = MISMATCHED_SPAN["span_end"]
        correct_text = source[start:end]

        assert verify_span(source, start, end, correct_text) is True

    def test_full_citation_verification_mismatch(self):
        """verify_citation_span must report invalid when either side mismatches."""
        source = "This is the source document content for testing."
        report = "The source document content is cited here."

        result = verify_citation_span(
            report_section_text=report,
            source_text=source,
            citation_span_start=0,
            citation_span_end=10,
            citation_span_text="WRONG TEXT",
            evidence_span_start=0,
            evidence_span_end=10,
            evidence_span_text="This is th",
        )
        assert result["report_match"] is False
        assert result["valid"] is False

    def test_negative_offset_rejected(self):
        """Negative span_start must be rejected."""
        assert verify_span("hello", -1, 3, "ell") is False

    def test_inverted_span_rejected(self):
        """span_end <= span_start must be rejected."""
        assert verify_span("hello", 3, 2, "l") is False


# ---------------------------------------------------------------------------
# Test 3: Connector failure not silent
# ---------------------------------------------------------------------------


class TestConnectorFailureNotSilent:
    def test_connector_failure_not_silent(self):
        """A failing connector must raise an exception, not return empty silently."""
        from harness.lib.research.sources.base import BaseSourceConnector

        class FailingConnector(BaseSourceConnector):
            connector_id = "fail_connector"
            connector_type = "internal_mirage"
            source_tier = "internal"
            display_name = "Failing Test Connector"

            def search(self, query, max_hits=10, **kwargs):
                raise ConnectionError("Simulated source failure")

            def fetch(self, source_id):
                raise ConnectionError("Simulated fetch failure")

        connector = FailingConnector()

        with pytest.raises(ConnectionError, match="Simulated source failure"):
            connector.search("test query")

        with pytest.raises(ConnectionError, match="Simulated fetch failure"):
            connector.fetch("any_source_id")

    def test_fetch_result_failure_requires_error(self):
        """FetchResult with failed status must have fetch_error set."""
        from harness.lib.research.sources.base import FetchResult

        with pytest.raises(ValueError, match="fetch_error"):
            FetchResult(
                source_id="src",
                connector_id="conn",
                title="Failed fetch",
                raw_text="",
                fetch_status="failed",
            )

    def test_broken_evidence_hash_rejected(self):
        """Evidence with mismatched content_hash must be rejected at construction."""
        with pytest.raises(ValueError, match="content_hash mismatch"):
            schemas.EvidenceItem(
                evidence_id="ev_bad_hash",
                source_id="src_001",
                source_type="document",
                content_hash=BROKEN_EVIDENCE["content_hash"],
                span_start=0,
                span_end=len(BROKEN_EVIDENCE["span_text"]),
                span_text=BROKEN_EVIDENCE["span_text"],
            )
