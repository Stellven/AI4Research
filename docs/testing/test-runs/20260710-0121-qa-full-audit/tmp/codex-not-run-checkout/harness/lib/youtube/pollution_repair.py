"""Pollution repair: audit and repair contaminated transcript records.

Supports both the legacy transcript-storage schema used by the B2 fixture
(`clean_path`/`raw_path`/`segments_json_path`) and the newer production schema
(`transcript_clean`/`transcript_raw`).
"""
from __future__ import annotations

from dataclasses import dataclass

import sqlite3


@dataclass
class PollutionReport:
    total_scanned: int
    polluted_count: int
    pollution_types: dict[str, int]
    sample_ids: list[str]


@dataclass
class RepairReport:
    total_repaired: int
    repair_actions: dict[str, int]
    dry_run: bool


def _columns(conn: sqlite3.Connection) -> set[str]:
    return {str(row[1]) for row in conn.execute("PRAGMA table_info(youtube_transcripts)").fetchall()}


def _schema_mode(conn: sqlite3.Connection) -> str:
    cols = _columns(conn)
    if "clean_path" in cols:
        return "legacy_paths"
    if "transcript_clean" in cols:
        return "inline_text"
    raise sqlite3.OperationalError("youtube_transcripts missing both clean_path and transcript_clean columns")


def _audit_rows(conn: sqlite3.Connection) -> list[tuple]:
    mode = _schema_mode(conn)
    if mode == "legacy_paths":
        return conn.execute(
            """SELECT transcript_id, video_id, clean_path, raw_path, segments_json_path
               FROM youtube_transcripts
               WHERE transcript_status = 'missing' AND clean_path IS NOT NULL
               ORDER BY video_id""",
        ).fetchall()
    return conn.execute(
        """SELECT video_id, video_id, transcript_clean, transcript_raw, NULL
           FROM youtube_transcripts
           WHERE transcript_status = 'missing'
             AND transcript_clean IS NOT NULL
             AND trim(transcript_clean) != ''
           ORDER BY video_id""",
    ).fetchall()


def audit_pollution(
    conn: sqlite3.Connection,
    dry_run: bool = True,
) -> PollutionReport:
    """Scan for polluted transcript records.

    Pollution means a transcript is still marked `missing` even though clean
    transcript material is already present.
    """
    pollution_types: dict[str, int] = {}
    rows = _audit_rows(conn)

    # Categorize pollution types
    for r in rows:
        has_raw = r[3] is not None
        has_segments = r[4] is not None
        if has_raw and has_segments:
            pollution_types["full_pipeline_stuck"] = pollution_types.get("full_pipeline_stuck", 0) + 1
        elif has_raw:
            pollution_types["has_raw_no_segments"] = pollution_types.get("has_raw_no_segments", 0) + 1
        else:
            pollution_types["clean_only"] = pollution_types.get("clean_only", 0) + 1

    sample_ids = [r[0] for r in rows[:10]]

    return PollutionReport(
        total_scanned=len(rows),
        polluted_count=len(rows),
        pollution_types=pollution_types,
        sample_ids=sample_ids,
    )


def repair_pollution(
    conn: sqlite3.Connection,
    dry_run: bool = True,
) -> RepairReport:
    """Repair polluted records in a single transaction (per OQC-1 atomicity).

    For each polluted record we normalize the status to `success`, because the
    clean transcript payload is already present and the bad state is the stale
    `missing` marker itself.
    """
    repair_actions: dict[str, int] = {}
    mode = _schema_mode(conn)
    rows = _audit_rows(conn)

    if not dry_run:
        repair_actions["success"] = len(rows)
        if mode == "legacy_paths":
            conn.execute(
                """UPDATE youtube_transcripts
                   SET transcript_status = 'success'
                   WHERE transcript_status = 'missing' AND clean_path IS NOT NULL""",
            )
        else:
            conn.execute(
                """UPDATE youtube_transcripts
                   SET transcript_status = 'success'
                   WHERE transcript_status = 'missing'
                     AND transcript_clean IS NOT NULL
                     AND trim(transcript_clean) != ''""",
            )
        conn.commit()
    else:
        repair_actions["dry_run_success"] = len(rows)

    return RepairReport(
        total_repaired=len(rows),
        repair_actions=repair_actions,
        dry_run=dry_run,
    )


def load_pollution_fixture(conn: sqlite3.Connection, sql_path: str) -> int:
    """Load a pollution seed SQL fixture into the database."""
    with open(sql_path) as f:
        sql = f.read()
    conn.executescript(sql)
    conn.commit()

    return verify_repair(conn)


def verify_repair(conn: sqlite3.Connection) -> int:
    """Count remaining polluted records after repair. Should return 0."""
    mode = _schema_mode(conn)
    if mode == "legacy_paths":
        return conn.execute(
            """SELECT COUNT(*) FROM youtube_transcripts
               WHERE transcript_status = 'missing' AND clean_path IS NOT NULL""",
        ).fetchone()[0]
    return conn.execute(
        """SELECT COUNT(*) FROM youtube_transcripts
           WHERE transcript_status = 'missing'
             AND transcript_clean IS NOT NULL
             AND trim(transcript_clean) != ''""",
    ).fetchone()[0]
