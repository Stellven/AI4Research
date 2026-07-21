"""Tests for research/evidence/ledger.py: evidence write/read, claim-evidence links,
unsupported claim detection.

Acceptance:
- write_evidence persists EvidenceItem and reads it back correctly
- read_evidence returns None for missing ID
- list_by_source returns items ordered by span_start
- check_unsupported_claims detects claims without evidence
- Content hash integrity is enforced at write time
- Span range is enforced at write time
"""

from __future__ import annotations

import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parent.parent.parent.parent / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

import pytest

from research.hashing import content_hash
from research.storage import init_db
from research.evidence.ledger import (
    check_unsupported_claims,
    list_by_source,
    read_evidence,
    write_evidence,
)
from research.schemas import EvidenceItem


def _make_evidence(
    evidence_id: str = "ev_test_001",
    source_id: str = "doc_src_001",
    span_text: str = "evidence span text",
    span_start: int = 0,
    span_end: int | None = None,
    source_type: str = "document",
    **kwargs,
) -> EvidenceItem:
    if span_end is None:
        span_end = span_start + len(span_text)
    return EvidenceItem(
        evidence_id=evidence_id,
        source_id=source_id,
        source_type=source_type,
        content_hash=content_hash(span_text),
        span_start=span_start,
        span_end=span_end,
        span_text=span_text,
        **kwargs,
    )


class TestWriteEvidence:
    def test_round_trip(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        conn = init_db(db_path)
        conn.execute("INSERT INTO research_runs (topic) VALUES ('test')")
        run_id = conn.execute("SELECT id FROM research_runs").fetchone()["id"]
        conn.execute(
            "INSERT INTO research_sources (run_id, content_hash, content_span) VALUES (?, 'h', 't')",
            (run_id,),
        )
        source_id = conn.execute("SELECT id FROM research_sources").fetchone()["id"]
        conn.commit()

        item = _make_evidence(source_id=source_id, span_text="hello world")
        write_evidence(conn, item, run_id)

        read_back = read_evidence(conn, item.evidence_id)
        assert read_back is not None
        assert read_back.span_text == "hello world"
        assert read_back.source_id == source_id
        conn.close()

    def test_rejects_hash_mismatch(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        conn = init_db(db_path)
        conn.execute("INSERT INTO research_runs (topic) VALUES ('test')")
        run_id = conn.execute("SELECT id FROM research_runs").fetchone()["id"]
        conn.commit()

        # Create a valid item, then mutate content_hash to simulate tampering.
        # write_evidence recomputes hash and catches the mismatch.
        item = _make_evidence(span_text="hello world")
        item.content_hash = "z" * 64  # corrupt after construction
        with pytest.raises(ValueError, match="content_hash mismatch"):
            write_evidence(conn, item, run_id)
        conn.close()

    def test_rejects_span_range_mismatch(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        conn = init_db(db_path)
        conn.execute("INSERT INTO research_runs (topic) VALUES ('test')")
        run_id = conn.execute("SELECT id FROM research_runs").fetchone()["id"]
        conn.commit()

        text = "hello world"
        item = _make_evidence(span_text=text, span_start=0, span_end=999)
        with pytest.raises(ValueError, match="span range"):
            write_evidence(conn, item, run_id)
        conn.close()


class TestReadEvidence:
    def test_returns_none_for_missing(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        conn = init_db(db_path)
        assert read_evidence(conn, "nonexistent_id") is None
        conn.close()


class TestListBySource:
    def test_ordered_by_span_start(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        conn = init_db(db_path)
        conn.execute("INSERT INTO research_runs (topic) VALUES ('test')")
        run_id = conn.execute("SELECT id FROM research_runs").fetchone()["id"]
        conn.execute(
            "INSERT INTO research_sources (run_id, content_hash, content_span) VALUES (?, 'h', 't')",
            (run_id,),
        )
        source_id = conn.execute("SELECT id FROM research_sources").fetchone()["id"]
        conn.commit()

        item2 = _make_evidence(evidence_id="ev_b", source_id=source_id,
                                span_text="second", span_start=10, span_end=16)
        item1 = _make_evidence(evidence_id="ev_a", source_id=source_id,
                                span_text="first", span_start=0, span_end=5)
        write_evidence(conn, item1, run_id)
        write_evidence(conn, item2, run_id)

        items = list_by_source(conn, source_id)
        assert len(items) == 2
        assert items[0].evidence_id == "ev_a"
        assert items[1].evidence_id == "ev_b"
        conn.close()

    def test_empty_for_no_evidence(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        conn = init_db(db_path)
        assert list_by_source(conn, "no_such_source") == []
        conn.close()


class TestCheckUnsupportedClaims:
    def _setup(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        conn = init_db(db_path)
        conn.execute("INSERT INTO research_runs (topic) VALUES ('test')")
        run_id = conn.execute("SELECT id FROM research_runs").fetchone()["id"]
        return conn, run_id

    def test_no_claims_returns_zero(self, tmp_path):
        conn, run_id = self._setup(tmp_path)
        result = check_unsupported_claims(conn, run_id)
        assert result["total_claims"] == 0
        assert result["unsupported_rate"] == 0.0
        assert result["exceeds_threshold"] is False
        conn.close()

    def test_all_supported(self, tmp_path):
        conn, run_id = self._setup(tmp_path)
        conn.execute(
            "INSERT INTO research_sources (run_id, content_hash, content_span) VALUES (?, 'h', 't')",
            (run_id,),
        )
        source_id = conn.execute("SELECT id FROM research_sources").fetchone()["id"]
        conn.execute(
            "INSERT INTO evidence_items (run_id, source_id, content, content_hash) VALUES (?, ?, 'test', 'h')",
            (run_id, source_id),
        )
        ev_id = conn.execute("SELECT id FROM evidence_items").fetchone()["id"]
        conn.execute(
            "INSERT INTO claims (run_id, claim_text, content_hash) VALUES (?, 'claim1', 'h1')",
            (run_id,),
        )
        claim_id = conn.execute("SELECT id FROM claims").fetchone()["id"]
        conn.execute(
            "INSERT INTO claim_evidence (run_id, claim_id, evidence_id) VALUES (?, ?, ?)",
            (run_id, claim_id, ev_id),
        )
        conn.commit()

        result = check_unsupported_claims(conn, run_id)
        assert result["total_claims"] == 1
        assert result["unsupported_count"] == 0
        assert result["unsupported_rate"] == 0.0
        conn.close()

    def test_unsupported_detected(self, tmp_path):
        conn, run_id = self._setup(tmp_path)
        conn.execute(
            "INSERT INTO claims (run_id, claim_text, content_hash) VALUES (?, 'orphan claim', 'h2')",
            (run_id,),
        )
        conn.commit()

        result = check_unsupported_claims(conn, run_id)
        assert result["total_claims"] == 1
        assert result["unsupported_count"] == 1
        assert result["unsupported_rate"] == 1.0
        assert result["exceeds_threshold"] is True
        conn.close()

    def test_threshold_calculation(self, tmp_path):
        conn, run_id = self._setup(tmp_path)
        for i in range(10):
            conn.execute(
                "INSERT INTO claims (run_id, claim_text, content_hash) VALUES (?, ?, ?)",
                (run_id, f"claim_{i}", f"h{i}"),
            )
        conn.commit()

        result = check_unsupported_claims(conn, run_id, threshold=0.05)
        assert result["total_claims"] == 10
        assert result["unsupported_count"] == 10
        assert result["unsupported_rate"] == 1.0
        conn.close()
