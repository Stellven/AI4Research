"""Unit tests for social_browser_backend_x schema, dedup, and migration."""
from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from .schema import PostRecord, ensure_schema, ensure_schema_safe, VALID_BACKENDS
from .dedup_keys_table import (
    DedupKeyRecord,
    ensure_dedup_keys_table,
    lookup_dedup_key,
    upsert_dedup_key,
)

_MIGRATION_SQL = (
    Path(__file__).parent / "migrations" / "001_add_browser_backend_columns.sql"
).read_text()


def _make_social_posts(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS social_posts (
            post_id       TEXT PRIMARY KEY,
            author_handle TEXT NOT NULL,
            text          TEXT NOT NULL DEFAULT '',
            created_at    TEXT,
            post_url      TEXT NOT NULL DEFAULT '',
            reply_count   INTEGER NOT NULL DEFAULT 0,
            repost_count  INTEGER NOT NULL DEFAULT 0,
            like_count    INTEGER NOT NULL DEFAULT 0,
            view_count    INTEGER,
            urls          TEXT NOT NULL DEFAULT '',
            fetched_at    TEXT NOT NULL
        )
    """)


class TestPostRecordRoundTrip(unittest.TestCase):
    """Test PostRecord dataclass round-trip serialization."""

    def test_full_round_trip(self):
        rec = PostRecord(
            post_id="abc123",
            author_handle="testuser",
            text="Hello world",
            created_at="2026-05-29T00:00:00Z",
            post_url="https://x.com/testuser/status/abc123",
            reply_count=5,
            repost_count=10,
            like_count=100,
            view_count=5000,
            urls="https://example.com",
            dom_hash="sha256deadbeef",
            screenshot_path="/tmp/shot.png",
            collection_backend="browser_agent",
        )
        row = rec.to_row()
        restored = PostRecord.from_row(row)
        self.assertEqual(rec, restored)

    def test_minimal_round_trip(self):
        rec = PostRecord(
            post_id="min",
            author_handle="u",
            text="t",
            created_at=None,
            post_url="",
        )
        row = rec.to_row()
        restored = PostRecord.from_row(row)
        self.assertEqual(rec, restored)

    def test_from_row_ignores_extra_columns(self):
        row = {
            "post_id": "x",
            "author_handle": "u",
            "text": "t",
            "created_at": None,
            "post_url": "",
            "extra_col": "should be ignored",
            "another_extra": 42,
        }
        rec = PostRecord.from_row(row)
        self.assertEqual(rec.post_id, "x")
        self.assertFalse(hasattr(rec, "extra_col"))

    def test_validate_backend_valid(self):
        for backend in VALID_BACKENDS:
            rec = PostRecord(
                post_id="t", author_handle="u", text="t",
                created_at=None, post_url="", collection_backend=backend,
            )
            rec.validate_backend()

    def test_validate_backend_invalid(self):
        rec = PostRecord(
            post_id="t", author_handle="u", text="t",
            created_at=None, post_url="", collection_backend="invalid_backend",
        )
        with self.assertRaises(ValueError):
            rec.validate_backend()


class TestDDLIdempotent(unittest.TestCase):
    """Test that DDL functions are idempotent."""

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        _make_social_posts(self.conn)
        ensure_dedup_keys_table(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_ensure_schema_twice(self):
        ensure_schema_safe(self.conn)
        ensure_schema_safe(self.conn)
        cur = self.conn.execute("PRAGMA table_info(social_posts)")
        cols = {row[1] for row in cur.fetchall()}
        self.assertIn("dom_hash", cols)
        self.assertIn("screenshot_path", cols)
        self.assertIn("collection_backend", cols)
        self.assertIn("dedup_key", cols)

    def test_dedup_keys_table_twice(self):
        ensure_dedup_keys_table(self.conn)
        ensure_dedup_keys_table(self.conn)
        cur = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name='social_post_dedup_keys'"
        )
        self.assertIsNotNone(cur.fetchone())


class TestMigrationSafety(unittest.TestCase):
    """Test that migration is safe for existing legacy rows."""

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        _make_social_posts(self.conn)
        ensure_dedup_keys_table(self.conn)
        # Insert a legacy row (simulating X API data before migration)
        self.conn.execute(
            "INSERT INTO social_posts "
            "(post_id, author_handle, text, created_at, post_url, fetched_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("legacy_1", "legacy_user", "old post", "2026-01-01", "https://x.com/old", "2026-01-01"),
        )

    def tearDown(self):
        self.conn.close()

    def test_legacy_row_survives_migration(self):
        ensure_schema_safe(self.conn)
        row = self.conn.execute(
            "SELECT post_id, author_handle, text, dom_hash, "
            "screenshot_path, collection_backend, dedup_key "
            "FROM social_posts WHERE post_id = 'legacy_1'"
        ).fetchone()
        self.assertEqual(row[0], "legacy_1")
        self.assertEqual(row[1], "legacy_user")
        self.assertEqual(row[2], "old post")
        self.assertIsNone(row[3])  # dom_hash
        self.assertIsNone(row[4])  # screenshot_path
        self.assertEqual(row[5], "unknown")  # collection_backend default
        self.assertIsNone(row[6])  # dedup_key

    def test_migration_sql_file_is_parseable(self):
        conn = sqlite3.connect(":memory:")
        _make_social_posts(conn)
        ensure_dedup_keys_table(conn)
        for stmt in _MIGRATION_SQL.split(";"):
            stmt = stmt.strip()
            if stmt and not stmt.startswith("--"):
                try:
                    conn.execute(stmt)
                except sqlite3.OperationalError as e:
                    if "duplicate column" not in str(e).lower():
                        raise

    def test_new_row_with_backend(self):
        ensure_schema_safe(self.conn)
        self.conn.execute(
            "INSERT INTO social_posts "
            "(post_id, author_handle, text, created_at, post_url, "
            " fetched_at, collection_backend, dom_hash) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("new_1", "new_user", "new post", "2026-05-29",
             "https://x.com/new", "2026-05-29", "browser_agent", "abc123"),
        )
        row = self.conn.execute(
            "SELECT collection_backend, dom_hash FROM social_posts WHERE post_id = 'new_1'"
        ).fetchone()
        self.assertEqual(row[0], "browser_agent")
        self.assertEqual(row[1], "abc123")


class TestDedupKeysCRUD(unittest.TestCase):
    """Test dedup key CRUD operations."""

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        ensure_dedup_keys_table(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_insert_and_lookup(self):
        rec = upsert_dedup_key(self.conn, "canonical_url_1", 42)
        self.assertEqual(rec.key, "canonical_url_1")
        self.assertEqual(rec.post_pk, 42)
        found = lookup_dedup_key(self.conn, "canonical_url_1")
        self.assertIsNotNone(found)
        self.assertEqual(found.post_pk, 42)

    def test_upsert_updates_last_seen(self):
        upsert_dedup_key(self.conn, "key1", 1)
        rec1 = lookup_dedup_key(self.conn, "key1")
        upsert_dedup_key(self.conn, "key1", 2)
        rec2 = lookup_dedup_key(self.conn, "key1")
        self.assertEqual(rec2.post_pk, 2)
        self.assertEqual(rec1.first_seen_at, rec2.first_seen_at)
        self.assertNotEqual(rec1.last_seen_at, rec2.last_seen_at)

    def test_lookup_missing(self):
        self.assertIsNone(lookup_dedup_key(self.conn, "nonexistent"))


if __name__ == "__main__":
    unittest.main()
