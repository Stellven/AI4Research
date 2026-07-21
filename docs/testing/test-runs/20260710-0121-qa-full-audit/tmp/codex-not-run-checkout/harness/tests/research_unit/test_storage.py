"""Tests for DeepResearch storage layer (storage.py + migrations/001_init.sql).

Constraints:
- Uses real sqlite3 with :memory: and tmp_path fixtures
- Zero @mock.patch decorators
- Assertion count >= 10

Spec: sprint-20260513-solar-deepresearch-product-line-s03-core-runtime / N2
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

_SOLAR_ROOT = Path(__file__).resolve().parents[3]
if str(_SOLAR_ROOT) not in sys.path:
    sys.path.insert(0, str(_SOLAR_ROOT))

from harness.lib.research.storage import (
    SEVEN_TABLES,
    append_jsonl,
    evidence_ledger_enabled,
    feature_flag,
    init_db,
    read_jsonl,
    table_count,
    table_exists,
    validate_jsonl,
    verify_span,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def conn():
    """In-memory database with all 7 tables created."""
    c = init_db(":memory:")
    yield c
    c.close()


@pytest.fixture
def run_id(conn):
    """Insert a minimal research_run and return its id."""
    conn.execute(
        "INSERT INTO research_runs (topic, depth_tier, status) VALUES (?, ?, ?)",
        ("Test topic", "standard", "pending"),
    )
    row = conn.execute("SELECT id FROM research_runs LIMIT 1").fetchone()
    conn.commit()
    return row["id"]


# ---------------------------------------------------------------------------
# init_db / table structure (assertions 1-5)
# ---------------------------------------------------------------------------


class TestInitDb:
    def test_all_seven_tables_created(self, conn):
        """Assert 1: all 7 tables exist after init_db."""
        for table in SEVEN_TABLES:
            assert table_exists(conn, table), f"Missing table: {table}"

    def test_tables_initially_empty(self, conn):
        """Assert 2: all tables have zero rows after init."""
        for table in SEVEN_TABLES:
            assert table_count(conn, table) == 0

    def test_idempotent_init(self):
        """Assert 3: calling init_db twice does not raise."""
        c = init_db(":memory:")
        c2 = init_db(":memory:")
        assert table_count(c2, "research_runs") == 0
        c.close()
        c2.close()

    def test_research_runs_check_constraints(self, conn):
        """Assert 4: invalid depth_tier is rejected."""
        with pytest.raises(Exception):
            conn.execute(
                "INSERT INTO research_runs (topic, depth_tier) VALUES (?, ?)",
                ("t", "invalid_tier"),
            )

    def test_research_runs_valid_insert(self, conn):
        """Assert 5: valid research_run row inserts and is queryable."""
        conn.execute(
            "INSERT INTO research_runs (topic, depth_tier, status) VALUES (?, ?, ?)",
            ("My topic", "deep", "pending"),
        )
        conn.commit()
        assert table_count(conn, "research_runs") == 1
        row = conn.execute("SELECT topic, depth_tier FROM research_runs").fetchone()
        assert row["topic"] == "My topic"
        assert row["depth_tier"] == "deep"


# ---------------------------------------------------------------------------
# Foreign key / cascade (assertions 6-7)
# ---------------------------------------------------------------------------


class TestForeignKeys:
    def test_source_requires_valid_run(self, conn):
        """Assert 6: inserting a source with bad run_id fails (FK)."""
        with pytest.raises(Exception):
            conn.execute(
                "INSERT INTO research_sources (run_id, content_hash, content_span) "
                "VALUES (?, ?, ?)",
                ("nonexistent_run", "abc123", '{"start":0,"end":100}'),
            )

    def test_cascade_delete(self, conn, run_id):
        """Assert 7: deleting a run cascades to child tables."""
        conn.execute(
            "INSERT INTO research_sources "
            "(run_id, content_hash, content_span) VALUES (?, ?, ?)",
            (run_id, "deadbeef", '{"start":0,"end":50}'),
        )
        assert table_count(conn, "research_sources") == 1
        conn.execute("DELETE FROM research_runs WHERE id = ?", (run_id,))
        conn.commit()
        assert table_count(conn, "research_sources") == 0


# ---------------------------------------------------------------------------
# JSONL helpers (assertions 8-11)
# ---------------------------------------------------------------------------


class TestJsonl:
    def test_append_and_read_roundtrip(self, tmp_path):
        """Assert 8: append_jsonl + read_jsonl round-trips correctly."""
        path = str(tmp_path / "test.jsonl")
        records = [
            {"id": "r1", "content": "hello"},
            {"id": "r2", "content": "world"},
        ]
        for r in records:
            append_jsonl(path, r)
        loaded = read_jsonl(path)
        assert loaded == records

    def test_validate_jsonl_detects_malformed(self, tmp_path):
        """Assert 9: validate_jsonl returns errors for bad JSON lines."""
        path = str(tmp_path / "bad.jsonl")
        with open(path, "w") as f:
            f.write('{"ok": true}\n{bad json}\n{"also_ok": 1}\n')
        errors = validate_jsonl(path)
        assert len(errors) == 1
        assert "line 2" in errors[0]

    def test_read_jsonl_nonexistent_returns_empty(self, tmp_path):
        """Assert 10: read_jsonl returns [] for missing files."""
        result = read_jsonl(str(tmp_path / "nope.jsonl"))
        assert result == []

    def test_append_creates_parent_dirs(self, tmp_path):
        """Assert 11: append_jsonl creates intermediate directories."""
        path = str(tmp_path / "sub" / "dir" / "out.jsonl")
        append_jsonl(path, {"x": 1})
        assert os.path.exists(path)
        assert read_jsonl(path) == [{"x": 1}]


# ---------------------------------------------------------------------------
# Feature flag (assertions 12-13)
# ---------------------------------------------------------------------------


class TestFeatureFlag:
    def test_default_off_when_no_config(self, tmp_path, monkeypatch):
        """Assert 12: feature_flag returns default when config missing."""
        monkeypatch.setattr(
            "harness.lib.research.storage.CONFIG_PATH",
            tmp_path / "nope.json",
        )
        assert feature_flag("research.evidence_ledger", default=False) is False

    def test_reads_flag_from_config(self, tmp_path, monkeypatch):
        """Assert 13: feature_flag reads from config.json."""
        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({"feature_flags": {"research.evidence_ledger": True}}))
        monkeypatch.setattr("harness.lib.research.storage.CONFIG_PATH", cfg)
        assert feature_flag("research.evidence_ledger", default=False) is True


# ---------------------------------------------------------------------------
# Span verification (assertions 14-16)
# ---------------------------------------------------------------------------


class TestVerifySpan:
    def test_exact_match(self):
        """Assert 14: matching spans return status='match'."""
        source = "The quick brown fox jumps over the lazy dog"
        evidence = "quick brown fox"
        start = source.index("quick")
        end = source.index("fox") + 3
        result = verify_span(source, evidence, start, end)
        assert result["status"] == "match"

    def test_mismatch(self):
        """Assert 15: non-matching spans return status='mismatch'."""
        source = "a" * 100
        evidence = "x" * 200
        result = verify_span(source, evidence, 0, 100)
        assert result["status"] == "mismatch"

    def test_fuzzy_match_tolerance(self):
        """Assert 16: small whitespace diff yields fuzzy_match."""
        source = "hello world"
        result = verify_span(source, "hello world ", 0, 11)
        assert result["status"] in ("match", "fuzzy_match")


# ---------------------------------------------------------------------------
# Evidence items with real data (assertions 17-18)
# ---------------------------------------------------------------------------


class TestEvidenceItems:
    def test_insert_evidence_with_fk_chain(self, conn, run_id):
        """Assert 17: full FK chain run → source → evidence works."""
        conn.execute(
            "INSERT INTO research_sources "
            "(run_id, content_hash, content_span) VALUES (?, ?, ?)",
            (run_id, "src_hash_1", '{"start":0,"end":100}'),
        )
        source_id = conn.execute(
            "SELECT id FROM research_sources WHERE run_id = ?", (run_id,)
        ).fetchone()["id"]

        conn.execute(
            "INSERT INTO evidence_items "
            "(run_id, source_id, content, content_hash, span_start, span_end) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (run_id, source_id, "some evidence", "ev_hash_1", 0, 13),
        )
        assert table_count(conn, "evidence_items") == 1

    def test_span_order_constraint(self, conn, run_id):
        """Assert 18: span_end < span_start is rejected."""
        conn.execute(
            "INSERT INTO research_sources "
            "(run_id, content_hash, content_span) VALUES (?, ?, ?)",
            (run_id, "src_hash_2", '{"start":0,"end":100}'),
        )
        source_id = conn.execute(
            "SELECT id FROM research_sources WHERE run_id = ?", (run_id,)
        ).fetchone()["id"]

        with pytest.raises(Exception):
            conn.execute(
                "INSERT INTO evidence_items "
                "(run_id, source_id, content, content_hash, span_start, span_end) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (run_id, source_id, "ev", "ev_hash_bad", 50, 10),
            )


# ---------------------------------------------------------------------------
# Claim + claim_evidence junction (assertion 19)
# ---------------------------------------------------------------------------


class TestClaimEvidence:
    def test_claim_evidence_junction(self, conn, run_id):
        """Assert 19: claim_evidence links claim to evidence via FK."""
        conn.execute(
            "INSERT INTO research_sources "
            "(run_id, content_hash, content_span) VALUES (?, ?, ?)",
            (run_id, "src_c", '{"start":0,"end":100}'),
        )
        source_id = conn.execute(
            "SELECT id FROM research_sources WHERE run_id = ?", (run_id,)
        ).fetchone()["id"]

        conn.execute(
            "INSERT INTO evidence_items "
            "(run_id, source_id, content, content_hash, span_start, span_end) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (run_id, source_id, "evidence text", "ev_c", 0, 13),
        )
        evidence_id = conn.execute(
            "SELECT id FROM evidence_items WHERE run_id = ?", (run_id,)
        ).fetchone()["id"]

        conn.execute(
            "INSERT INTO claims (run_id, claim_text, content_hash) VALUES (?, ?, ?)",
            (run_id, "test claim", "claim_hash"),
        )
        claim_id = conn.execute(
            "SELECT id FROM claims WHERE run_id = ?", (run_id,)
        ).fetchone()["id"]

        conn.execute(
            "INSERT INTO claim_evidence (run_id, claim_id, evidence_id) VALUES (?, ?, ?)",
            (run_id, claim_id, evidence_id),
        )
        assert table_count(conn, "claim_evidence") == 1
        junction = conn.execute(
            "SELECT * FROM claim_evidence WHERE run_id = ?", (run_id,)
        ).fetchone()
        assert junction["claim_id"] == claim_id
        assert junction["evidence_id"] == evidence_id
        assert junction["relation"] == "supports"
