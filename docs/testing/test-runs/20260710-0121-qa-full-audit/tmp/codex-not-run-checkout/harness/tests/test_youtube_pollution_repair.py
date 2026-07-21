"""Tests for pollution_repair module — B2 acceptance."""
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "migrations"))

from youtube.pollution_repair import audit_pollution, repair_pollution, load_pollution_fixture, verify_repair
from youtube_002_transcripts import up as m002


@pytest.fixture
def db_with_migrations(tmp_path):
    conn = sqlite3.connect(str(tmp_path / "test.db"))
    conn.execute("PRAGMA journal_mode=WAL")
    m002(conn)
    yield conn
    conn.close()


@pytest.fixture
def db_with_inline_schema(tmp_path):
    conn = sqlite3.connect(str(tmp_path / "inline.db"))
    conn.execute(
        """
        CREATE TABLE youtube_transcripts (
            video_id TEXT PRIMARY KEY,
            transcript_raw TEXT NOT NULL DEFAULT '',
            transcript_clean TEXT NOT NULL DEFAULT '',
            transcript_status TEXT NOT NULL DEFAULT 'missing',
            language TEXT NOT NULL DEFAULT '',
            fetched_at TEXT,
            char_count INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    yield conn
    conn.close()


@pytest.fixture
def db_with_pollution(db_with_migrations):
    fixture_path = Path(__file__).resolve().parent / "fixtures" / "pollution_seed.sql"
    count = load_pollution_fixture(db_with_migrations, str(fixture_path))
    assert count == 165, f"Expected 165 polluted rows, got {count}"
    return db_with_migrations


class TestAuditPollution:
    def test_dry_run_returns_165(self, db_with_pollution):
        report = audit_pollution(db_with_pollution, dry_run=True)
        assert report.polluted_count == 165

    def test_dry_run_does_not_modify(self, db_with_pollution):
        before = audit_pollution(db_with_pollution, dry_run=True).polluted_count
        audit_pollution(db_with_pollution, dry_run=True)
        after = audit_pollution(db_with_pollution, dry_run=True).polluted_count
        assert before == after == 165

    def test_categorizes_pollution_types(self, db_with_pollution):
        report = audit_pollution(db_with_pollution, dry_run=True)
        assert len(report.pollution_types) >= 1
        assert report.total_scanned == 165

    def test_sample_ids_present(self, db_with_pollution):
        report = audit_pollution(db_with_pollution, dry_run=True)
        assert len(report.sample_ids) <= 10
        assert all(isinstance(sid, str) for sid in report.sample_ids)

    def test_no_pollution_on_clean_db(self, db_with_migrations):
        report = audit_pollution(db_with_migrations, dry_run=True)
        assert report.polluted_count == 0

    def test_inline_text_empty_string_not_counted_as_pollution(self, db_with_inline_schema):
        db_with_inline_schema.execute(
            """INSERT INTO youtube_transcripts
               (video_id, transcript_status, transcript_clean, transcript_raw, language)
               VALUES ('vid-empty', 'missing', '', '', 'en')"""
        )
        db_with_inline_schema.commit()
        report = audit_pollution(db_with_inline_schema, dry_run=True)
        assert report.polluted_count == 0

    def test_inline_text_non_empty_missing_row_counted_as_pollution(self, db_with_inline_schema):
        db_with_inline_schema.execute(
            """INSERT INTO youtube_transcripts
               (video_id, transcript_status, transcript_clean, transcript_raw, language)
               VALUES ('vid-dirty', 'missing', 'stale text', '', 'en')"""
        )
        db_with_inline_schema.commit()
        report = audit_pollution(db_with_inline_schema, dry_run=True)
        assert report.polluted_count == 1


class TestRepairPollution:
    def test_dry_run_repair(self, db_with_pollution):
        report = repair_pollution(db_with_pollution, dry_run=True)
        assert report.total_repaired == 165
        assert verify_repair(db_with_pollution) == 165

    def test_actual_repair(self, db_with_pollution):
        report = repair_pollution(db_with_pollution, dry_run=False)
        assert report.total_repaired == 165
        assert verify_repair(db_with_pollution) == 0

    def test_atomicity_single_transaction(self, db_with_pollution):
        """Per OQC-1: repair must be atomic in a single transaction."""
        repair_pollution(db_with_pollution, dry_run=False)
        remaining = verify_repair(db_with_pollution)
        assert remaining == 0

    def test_inline_text_repair_only_flips_non_empty_rows(self, db_with_inline_schema):
        db_with_inline_schema.execute(
            """INSERT INTO youtube_transcripts
               (video_id, transcript_status, transcript_clean, transcript_raw, language)
               VALUES
               ('vid-empty', 'missing', '', '', 'en'),
               ('vid-dirty', 'missing', 'stale text', '', 'en')"""
        )
        db_with_inline_schema.commit()
        report = repair_pollution(db_with_inline_schema, dry_run=False)
        rows = db_with_inline_schema.execute(
            "SELECT video_id, transcript_status FROM youtube_transcripts ORDER BY video_id"
        ).fetchall()
        assert report.total_repaired == 1
        assert rows == [('vid-dirty', 'success'), ('vid-empty', 'missing')]
