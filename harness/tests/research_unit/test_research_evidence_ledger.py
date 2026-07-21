"""Tests for evidence/ledger.py: write_evidence, read_evidence, list_by_source.

Acceptance:
- write_evidence + read_evidence round-trip
- list_by_source returns items for the correct source
- Negative: unsupported claims are detected and rejected
- All tests use real SQLite (:memory:), zero @mock.patch
"""

from __future__ import annotations

import sys
from pathlib import Path

# Place harness/lib on sys.path (same pattern as existing tests)
_LIB_DIR = Path(__file__).resolve().parent.parent.parent / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

import pytest  # noqa: E402

from research import hashing, ids, schemas, storage  # noqa: E402
from research.evidence.ledger import (  # noqa: E402
    check_unsupported_claims,
    list_by_source,
    read_evidence,
    write_evidence,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _init_db():
    """Create an in-memory DB with all 7 tables and return the connection."""
    return storage.init_db(":memory:")


def _seed_run(conn, run_id="run_test_001"):
    conn.execute(
        "INSERT INTO research_runs (id, topic, depth_tier, status) VALUES (?, ?, ?, ?)",
        (run_id, "Test topic", "standard", "running"),
    )
    conn.commit()
    return run_id


def _seed_source(conn, source_id="src_abc", run_id="run_test_001"):
    source_text = f"source text for {source_id}"
    conn.execute(
        "INSERT INTO research_sources (id, run_id, title, content_hash, content_span) "
        "VALUES (?, ?, ?, ?, ?)",
        (source_id, run_id, "Test Source", hashing.content_hash(source_text), f"0-{len(source_text)}"),
    )
    conn.commit()
    return source_id


def _make_evidence(
    source_id="src_abc",
    span_text="Hello world evidence text",
    span_offset=0,
):
    ch = hashing.content_hash(span_text)
    end = span_offset + len(span_text)
    eid = ids.evidence_id(source_id, span_offset, end, ch)
    return schemas.EvidenceItem(
        evidence_id=eid,
        source_id=source_id,
        source_type="document",
        content_hash=ch,
        span_start=span_offset,
        span_end=end,
        span_text=span_text,
        section_path="ch01/sec01",
        evidence_type="direct_quote",
        relevance_score=0.85,
        support_direction="supporting",
    )


# ---------------------------------------------------------------------------
# Tests: write_evidence + read_evidence round-trip
# ---------------------------------------------------------------------------

class TestWriteReadEvidence:
    def test_write_and_read_roundtrip(self):
        conn = _init_db()
        run_id = _seed_run(conn)
        _seed_source(conn, run_id=run_id)
        item = _make_evidence()

        write_evidence(conn, item, run_id=run_id)

        result = read_evidence(conn, item.evidence_id)
        assert result is not None
        assert result.evidence_id == item.evidence_id
        assert result.source_id == item.source_id
        assert result.span_text == item.span_text
        assert result.content_hash == item.content_hash
        assert result.span_start == item.span_start
        assert result.span_end == item.span_end
        assert result.evidence_type == item.evidence_type
        assert abs(result.relevance_score - item.relevance_score) < 1e-6
        assert result.support_direction == item.support_direction
        assert result.section_path == item.section_path

    def test_read_nonexistent_returns_none(self):
        conn = _init_db()
        result = read_evidence(conn, "ev_doesnotexist")
        assert result is None

    def test_write_preserves_content_hash_integrity(self):
        conn = _init_db()
        run_id = _seed_run(conn)
        _seed_source(conn, run_id=run_id)
        item = _make_evidence()
        write_evidence(conn, item, run_id=run_id)

        result = read_evidence(conn, item.evidence_id)
        assert hashing.verify_content_hash(result.span_text, result.content_hash)

    def test_write_rejects_hash_mismatch(self):
        conn = _init_db()
        run_id = _seed_run(conn)
        _seed_source(conn, run_id=run_id)

        item = _make_evidence()
        bad_item = _make_evidence()
        object.__setattr__(bad_item, "content_hash", "0" * 64)
        with pytest.raises(ValueError, match="content_hash mismatch"):
            write_evidence(conn, bad_item, run_id=run_id)

    def test_write_rejects_span_range_mismatch(self):
        conn = _init_db()
        run_id = _seed_run(conn)
        _seed_source(conn, run_id=run_id)

        ch = hashing.content_hash("short")
        item = schemas.EvidenceItem(
            evidence_id="ev_bad_span",
            source_id="src_abc",
            source_type="document",
            content_hash=ch,
            span_start=0,
            span_end=100,
            span_text="short",
        )
        with pytest.raises(ValueError, match="span range"):
            write_evidence(conn, item, run_id=run_id)


# ---------------------------------------------------------------------------
# Tests: list_by_source
# ---------------------------------------------------------------------------

class TestListBySource:
    def test_list_returns_items_for_correct_source(self):
        conn = _init_db()
        run_id = _seed_run(conn)
        _seed_source(conn, source_id="src_a", run_id=run_id)
        _seed_source(conn, source_id="src_b", run_id=run_id)

        item_a = _make_evidence(source_id="src_a", span_text="from source A")
        item_a2 = _make_evidence(source_id="src_a", span_text="also from A", span_offset=14)
        item_b = _make_evidence(source_id="src_b", span_text="from source B")

        write_evidence(conn, item_a, run_id=run_id)
        write_evidence(conn, item_a2, run_id=run_id)
        write_evidence(conn, item_b, run_id=run_id)

        result_a = list_by_source(conn, "src_a")
        assert len(result_a) == 2
        assert all(r.source_id == "src_a" for r in result_a)

        result_b = list_by_source(conn, "src_b")
        assert len(result_b) == 1
        assert result_b[0].source_id == "src_b"

    def test_list_empty_for_unknown_source(self):
        conn = _init_db()
        result = list_by_source(conn, "src_nonexistent")
        assert result == []

    def test_list_ordered_by_span_start(self):
        conn = _init_db()
        run_id = _seed_run(conn)
        _seed_source(conn, source_id="src_ordered", run_id=run_id)

        # Write items out of order
        item_late = _make_evidence(source_id="src_ordered", span_text="later text", span_offset=20)
        item_early = _make_evidence(source_id="src_ordered", span_text="early text", span_offset=0)

        write_evidence(conn, item_late, run_id=run_id)
        write_evidence(conn, item_early, run_id=run_id)

        result = list_by_source(conn, "src_ordered")
        assert len(result) == 2
        assert result[0].span_start < result[1].span_start


# ---------------------------------------------------------------------------
# Tests: unsupported claims (negative control)
# ---------------------------------------------------------------------------

class TestUnsupportedClaims:
    def test_unsupported_claim_rejected(self):
        """Negative test: claims without evidence links are detected."""
        conn = _init_db()
        run_id = _seed_run(conn)
        _seed_source(conn, run_id=run_id)

        # Insert a claim with no evidence link
        conn.execute(
            "INSERT INTO claims (id, run_id, claim_text, content_hash) "
            "VALUES (?, ?, ?, ?)",
            ("claim_no_ev", run_id, "Unsupported claim", hashing.content_hash("Unsupported claim")),
        )
        conn.commit()

        result = check_unsupported_claims(conn, run_id, threshold=0.05)
        assert result["exceeds_threshold"] is True
        assert result["unsupported_count"] == 1
        assert "claim_no_ev" in result["unsupported_claim_ids"]
        assert result["unsupported_rate"] == 1.0

    def test_supported_claim_passes(self):
        conn = _init_db()
        run_id = _seed_run(conn)
        _seed_source(conn, run_id=run_id)

        item = _make_evidence()
        write_evidence(conn, item, run_id=run_id)

        conn.execute(
            "INSERT INTO claims (id, run_id, claim_text, content_hash) "
            "VALUES (?, ?, ?, ?)",
            ("claim_ok", run_id, "Supported claim", hashing.content_hash("Supported claim")),
        )
        conn.execute(
            "INSERT INTO claim_evidence (id, run_id, claim_id, evidence_id) "
            "VALUES (?, ?, ?, ?)",
            ("ce_link", run_id, "claim_ok", item.evidence_id),
        )
        conn.commit()

        result = check_unsupported_claims(conn, run_id, threshold=0.05)
        assert result["exceeds_threshold"] is False
        assert result["unsupported_count"] == 0

    def test_no_claims_returns_pass(self):
        conn = _init_db()
        run_id = _seed_run(conn)
        result = check_unsupported_claims(conn, run_id)
        assert result["exceeds_threshold"] is False
        assert result["total_claims"] == 0
