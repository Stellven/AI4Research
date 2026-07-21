"""SQLite + FTS5 index for Solar Experience Memory."""
import json
import logging
import os
import sqlite3
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

HARNESS_DIR = os.path.expanduser("~/.solar/harness")
DB_PATH = os.path.join(HARNESS_DIR, "experience", "experience.db")
SCHEMA_PATH = os.path.join(HARNESS_DIR, "experience", "index.db.schema.sql")


def _get_conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db() -> None:
    """Initialize the database schema if not present."""
    conn = _get_conn()
    try:
        if os.path.exists(SCHEMA_PATH):
            with open(SCHEMA_PATH) as f:
                schema_sql = f.read()
            conn.executescript(schema_sql)
        else:
            # Inline schema fallback
            conn.executescript(_INLINE_SCHEMA)
        conn.commit()
    finally:
        conn.close()


def upsert_entry(entry: Dict[str, Any]) -> None:
    """Insert or update an experience entry in the index."""
    conn = _get_conn()
    try:
        conn.execute("""
            INSERT INTO experience_entries
                (entry_id, trigger_sig, state_sig, pattern_class, tags, outcome,
                 advisory, repair_recipe, source_sids, hit_count, last_seen, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(entry_id) DO UPDATE SET
                hit_count=excluded.hit_count,
                last_seen=excluded.last_seen,
                advisory=excluded.advisory,
                repair_recipe=excluded.repair_recipe,
                source_sids=excluded.source_sids
        """, (
            entry["entry_id"],
            entry["trigger_sig"],
            entry.get("state_sig"),
            entry["pattern_class"],
            json.dumps(entry.get("tags", [])),
            entry["outcome"],
            entry.get("advisory", ""),
            entry.get("repair_recipe", ""),
            json.dumps(entry.get("source_sids", [])),
            entry.get("hit_count", 0),
            entry.get("last_seen"),
            entry["created_at"],
        ))
        conn.commit()
    finally:
        conn.close()


def query_by_trigger(trigger_sig: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Query entries by trigger signature."""
    conn = _get_conn()
    try:
        rows = conn.execute("""
            SELECT * FROM experience_entries
            WHERE trigger_sig = ?
            ORDER BY hit_count DESC, last_seen DESC
            LIMIT ?
        """, (trigger_sig, limit)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def query_fts(query_text: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Full-text search across entries."""
    conn = _get_conn()
    try:
        rows = conn.execute("""
            SELECT e.* FROM experience_entries e
            JOIN experience_fts f ON e.rowid = f.rowid
            WHERE experience_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """, (query_text, limit)).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError as exc:
        logger.warning("FTS query failed (%s), falling back to LIKE", exc)
        rows = conn.execute("""
            SELECT * FROM experience_entries
            WHERE advisory LIKE ? OR repair_recipe LIKE ? OR tags LIKE ?
            ORDER BY hit_count DESC LIMIT ?
        """, (f"%{query_text}%", f"%{query_text}%", f"%{query_text}%", limit)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def query_by_pattern(pattern_class: str, limit: int = 10) -> List[Dict[str, Any]]:
    conn = _get_conn()
    try:
        rows = conn.execute("""
            SELECT * FROM experience_entries
            WHERE pattern_class = ?
            ORDER BY hit_count DESC, last_seen DESC
            LIMIT ?
        """, (pattern_class, limit)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def stats() -> Dict[str, Any]:
    """Return aggregate stats for all entries."""
    conn = _get_conn()
    try:
        total = conn.execute("SELECT COUNT(*) FROM experience_entries").fetchone()[0]
        by_pattern = {}
        for row in conn.execute(
            "SELECT pattern_class, COUNT(*) as cnt FROM experience_entries GROUP BY pattern_class"
        ).fetchall():
            by_pattern[row[0]] = row[1]
        by_outcome = {}
        for row in conn.execute(
            "SELECT outcome, COUNT(*) as cnt FROM experience_entries GROUP BY outcome"
        ).fetchall():
            by_outcome[row[0]] = row[1]
        return {
            "total_entries": total,
            "by_pattern": by_pattern,
            "by_outcome": by_outcome,
        }
    finally:
        conn.close()


_INLINE_SCHEMA = """
CREATE TABLE IF NOT EXISTS experience_entries (
    entry_id TEXT PRIMARY KEY,
    trigger_sig TEXT NOT NULL,
    state_sig TEXT,
    pattern_class TEXT NOT NULL,
    tags TEXT,
    outcome TEXT NOT NULL,
    advisory TEXT,
    repair_recipe TEXT,
    source_sids TEXT,
    hit_count INTEGER DEFAULT 0,
    last_seen TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_trigger_sig ON experience_entries(trigger_sig);
CREATE INDEX IF NOT EXISTS idx_pattern_class ON experience_entries(pattern_class);
CREATE INDEX IF NOT EXISTS idx_outcome ON experience_entries(outcome);
CREATE VIRTUAL TABLE IF NOT EXISTS experience_fts USING fts5(
    entry_id UNINDEXED,
    pattern_class,
    tags,
    advisory,
    repair_recipe,
    content='experience_entries',
    content_rowid='rowid'
);
CREATE TABLE IF NOT EXISTS experience_meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
INSERT OR IGNORE INTO experience_meta(key, value) VALUES ('schema_version', '1.0.0');
INSERT OR IGNORE INTO experience_meta(key, value) VALUES ('created_at', datetime('now'));
"""
