"""Tests for transcript_storage module — B2 acceptance."""
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "migrations"))

from youtube.transcript_storage import (
    create_transcript, update_quality, get_transcript,
    list_transcripts_by_tier,
)
from youtube_002_transcripts import up as m002


@pytest.fixture
def db_conn():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA journal_mode=WAL")
    m002(conn)
    yield conn
    conn.close()


class TestCreateTranscript:
    def test_creates_and_returns_id(self, db_conn):
        tid = create_transcript(
            db_conn, video_id="abc123", source="standard_caption",
            raw_path="/data/abc.raw", text_raw="Hello world",
        )
        assert tid.startswith("t-abc123-standard_caption-")

    def test_idempotent_same_input(self, db_conn):
        tid1 = create_transcript(
            db_conn, video_id="abc123", source="standard_caption",
            raw_path="/data/abc.raw", text_raw="Hello world",
        )
        tid2 = create_transcript(
            db_conn, video_id="abc123", source="standard_caption",
            raw_path="/data/abc.raw", text_raw="Hello world",
        )
        assert tid1 == tid2

    def test_rejects_invalid_source(self, db_conn):
        with pytest.raises(ValueError, match="Invalid source"):
            create_transcript(
                db_conn, video_id="x", source="invalid_source",
                raw_path="/x.raw", text_raw="x",
            )

    def test_different_sources_different_ids(self, db_conn):
        tid1 = create_transcript(
            db_conn, video_id="v1", source="standard_caption",
            raw_path="/v1.raw", text_raw="hello",
        )
        tid2 = create_transcript(
            db_conn, video_id="v1", source="browser_caption",
            raw_path="/v1.raw", text_raw="hello",
        )
        assert tid1 != tid2


class TestGetTranscript:
    def test_returns_record(self, db_conn):
        tid = create_transcript(
            db_conn, video_id="v1", source="browser_caption",
            raw_path="/v1.raw", text_raw="test text",
        )
        rec = get_transcript(db_conn, tid)
        assert rec is not None
        assert rec.video_id == "v1"
        assert rec.source == "browser_caption"

    def test_returns_none_for_missing(self, db_conn):
        assert get_transcript(db_conn, "nonexistent") is None


class TestUpdateQuality:
    def test_updates_quality(self, db_conn):
        tid = create_transcript(
            db_conn, video_id="v2", source="browser_caption",
            raw_path="/v2.raw", text_raw="quality test",
        )
        update_quality(db_conn, tid, 0.92, "T0", "v1")
        rec = get_transcript(db_conn, tid)
        assert rec.quality_score == 0.92
        assert rec.quality_tier == "T0"

    def test_rejects_invalid_tier(self, db_conn):
        tid = create_transcript(
            db_conn, video_id="v3", source="standard_caption",
            raw_path="/v3.raw", text_raw="tier test",
        )
        with pytest.raises(ValueError, match="Invalid quality_tier"):
            update_quality(db_conn, tid, 0.5, "T99", "v1")

    def test_all_valid_tiers(self, db_conn):
        for tier in ["T0", "T1", "T2", "T3"]:
            tid = create_transcript(
                db_conn, video_id=f"v_{tier}", source="standard_caption",
                raw_path=f"/v_{tier}.raw", text_raw=f"test {tier}",
            )
            update_quality(db_conn, tid, 0.5, tier, "v1")
            rec = get_transcript(db_conn, tid)
            assert rec.quality_tier == tier


class TestListByTier:
    def test_filters_by_tier(self, db_conn):
        tid = create_transcript(
            db_conn, video_id="v4", source="browser_caption",
            raw_path="/v4.raw", text_raw="tier filter",
        )
        update_quality(db_conn, tid, 0.75, "T1", "v1")
        results = list_transcripts_by_tier(db_conn, "T1")
        assert len(results) >= 1
        assert all(r.quality_tier == "T1" for r in results)

    def test_empty_for_unpopulated_tier(self, db_conn):
        results = list_transcripts_by_tier(db_conn, "T0")
        assert results == []
