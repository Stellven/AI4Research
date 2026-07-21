"""B1 tests — migration youtube_001_subtitle_tracks: DDL idempotency + 4-tuple UNIQUE (D2)."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "migrations"))
import youtube_001_subtitle_tracks as migration


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    yield c
    c.close()


def test_migration_id_constant():
    assert migration.MIGRATION_ID == "youtube_001_subtitle_tracks"


def test_up_creates_table(conn):
    migration.up(conn)
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='youtube_subtitle_tracks'"
    ).fetchall()
    assert len(rows) == 1


def test_up_creates_migrations_table(conn):
    migration.up(conn)
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='youtube_intelligence_migrations'"
    ).fetchall()
    assert len(rows) == 1


def test_migrations_table_records_migration_id(conn):
    migration.up(conn)
    rows = conn.execute(
        "SELECT migration_id FROM youtube_intelligence_migrations"
    ).fetchall()
    assert (migration.MIGRATION_ID,) in rows


def test_up_is_idempotent(conn):
    """Per D2: CREATE TABLE IF NOT EXISTS — repeated up() must not error."""
    migration.up(conn)
    migration.up(conn)  # second call must succeed
    rows = conn.execute(
        "SELECT COUNT(*) FROM youtube_intelligence_migrations WHERE migration_id = ?",
        (migration.MIGRATION_ID,),
    ).fetchone()
    assert rows[0] == 1  # not duplicated


def test_four_tuple_unique_constraint(conn):
    """Per dispatch acceptance: UNIQUE(video_id, source_backend, language, track_kind)."""
    migration.up(conn)
    conn.execute(
        """INSERT INTO youtube_subtitle_tracks
           (track_id, video_id, source_backend, language, track_kind, discovered_at)
           VALUES ('t1', 'v1', 'yt_dlp', 'en', 'standard', '2026-05-27T00:00:00Z')"""
    )
    # Same 4-tuple with different track_id must fail
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """INSERT INTO youtube_subtitle_tracks
               (track_id, video_id, source_backend, language, track_kind, discovered_at)
               VALUES ('t2', 'v1', 'yt_dlp', 'en', 'standard', '2026-05-27T00:00:01Z')"""
        )


def test_different_track_kind_allowed(conn):
    """Same video+backend+language but different kind is allowed."""
    migration.up(conn)
    conn.execute(
        """INSERT INTO youtube_subtitle_tracks
           (track_id, video_id, source_backend, language, track_kind, discovered_at)
           VALUES ('t1', 'v1', 'yt_dlp', 'en', 'standard', '2026-05-27T00:00:00Z')"""
    )
    conn.execute(
        """INSERT INTO youtube_subtitle_tracks
           (track_id, video_id, source_backend, language, track_kind, discovered_at)
           VALUES ('t2', 'v1', 'yt_dlp', 'en', 'asr', '2026-05-27T00:00:01Z')"""
    )
    rows = conn.execute("SELECT COUNT(*) FROM youtube_subtitle_tracks").fetchone()
    assert rows[0] == 2


def test_source_backend_check_constraint(conn):
    migration.up(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """INSERT INTO youtube_subtitle_tracks
               (track_id, video_id, source_backend, language, track_kind, discovered_at)
               VALUES ('t', 'v', 'invalid_backend', 'en', 'standard', '2026-05-27T00:00:00Z')"""
        )


def test_track_kind_check_constraint(conn):
    migration.up(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """INSERT INTO youtube_subtitle_tracks
               (track_id, video_id, source_backend, language, track_kind, discovered_at)
               VALUES ('t', 'v', 'yt_dlp', 'en', 'invalid_kind', '2026-05-27T00:00:00Z')"""
        )


def test_confidence_range_check(conn):
    migration.up(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """INSERT INTO youtube_subtitle_tracks
               (track_id, video_id, source_backend, language, track_kind, discovered_at, confidence)
               VALUES ('t', 'v', 'yt_dlp', 'en', 'standard', '2026-05-27T00:00:00Z', 1.5)"""
        )


def test_indices_created(conn):
    migration.up(conn)
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='youtube_subtitle_tracks'"
    ).fetchall()
    idx_names = {r[0] for r in rows}
    assert "idx_subtitle_tracks_video" in idx_names
    assert "idx_subtitle_tracks_video_kind" in idx_names


def test_down_drops_table(conn):
    migration.up(conn)
    migration.down(conn)
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='youtube_subtitle_tracks'"
    ).fetchall()
    assert len(rows) == 0
