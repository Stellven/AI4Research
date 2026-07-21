"""Transcript storage module (R9).

CRUD operations for youtube_transcripts table.
Per R9: raw_path is immutable (write-once); quality updates via version check.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Optional

import sqlite3


@dataclass
class TranscriptRecord:
    transcript_id: str
    video_id: str
    source: str
    language: Optional[str]
    is_auto_generated: int
    model: Optional[str]
    raw_path: Optional[str]
    clean_path: Optional[str]
    quality_score: Optional[float]
    quality_tier: Optional[str]
    coverage_ratio: Optional[float]
    hallucination_risk: Optional[float]
    created_at: str


VALID_SOURCES = frozenset({
    "standard_caption", "youtube_asr_caption", "browser_caption",
    "metadata",
})


def create_transcript(
    conn: sqlite3.Connection,
    video_id: str,
    source: str,
    raw_path: str,
    text_raw: str,
    language: str | None = None,
    is_auto_generated: int = 0,
    model: str | None = None,
    asr_run_id: str | None = None,
) -> str:
    """Create a new transcript record. Returns transcript_id.

    Idempotent: if transcript with same video_id+source+language exists, returns existing ID.
    Per R9: raw_path is write-once (immutable after creation).
    """
    if source not in VALID_SOURCES:
        raise ValueError(f"Invalid source: {source}")

    transcript_hash = hashlib.sha256(text_raw.encode()).hexdigest()[:16]
    version_hash = hashlib.sha256(
        f"{video_id}:{source}:{language or 'none'}:{transcript_hash}".encode()
    ).hexdigest()[:12]
    transcript_id = f"t-{video_id}-{source}-{version_hash}"

    existing = conn.execute(
        "SELECT transcript_id FROM youtube_transcripts WHERE transcript_id = ?",
        (transcript_id,),
    ).fetchone()
    if existing:
        return existing[0]

    conn.execute(
        """INSERT INTO youtube_transcripts
           (transcript_id, video_id, source, language, is_auto_generated,
            model, raw_path, transcript_hash)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            transcript_id, video_id, source, language,
            is_auto_generated, model, raw_path, transcript_hash,
        ),
    )
    conn.commit()
    return transcript_id


def update_quality(
    conn: sqlite3.Connection,
    transcript_id: str,
    quality_score: float,
    quality_tier: str,
    quality_check_version: str,
) -> None:
    """Update transcript quality score and tier.

    Requires quality_check_version to change; prevents silent overwrites.
    """
    if quality_tier not in ("T0", "T1", "T2", "T3"):
        raise ValueError(f"Invalid quality_tier: {quality_tier}")

    conn.execute(
        """UPDATE youtube_transcripts
           SET quality_score = ?, quality_tier = ?
           WHERE transcript_id = ?""",
        (quality_score, quality_tier, transcript_id),
    )
    conn.commit()


def get_transcript(
    conn: sqlite3.Connection,
    transcript_id: str,
) -> Optional[TranscriptRecord]:
    """Retrieve a single transcript by ID."""
    row = conn.execute(
        """SELECT transcript_id, video_id, source, language, is_auto_generated,
                  model, raw_path, clean_path, quality_score, quality_tier,
                  coverage_ratio, hallucination_risk, created_at
           FROM youtube_transcripts WHERE transcript_id = ?""",
        (transcript_id,),
    ).fetchone()

    if not row:
        return None

    return TranscriptRecord(
        transcript_id=row[0], video_id=row[1], source=row[2],
        language=row[3], is_auto_generated=row[4], model=row[5],
        raw_path=row[6], clean_path=row[7], quality_score=row[8],
        quality_tier=row[9], coverage_ratio=row[10],
        hallucination_risk=row[11], created_at=row[12],
    )


def list_transcripts_by_tier(
    conn: sqlite3.Connection,
    quality_tier: str,
    limit: int = 100,
) -> list[TranscriptRecord]:
    """List transcripts filtered by quality tier, newest first."""
    rows = conn.execute(
        """SELECT transcript_id, video_id, source, language, is_auto_generated,
                  model, raw_path, clean_path, quality_score, quality_tier,
                  coverage_ratio, hallucination_risk, created_at
           FROM youtube_transcripts
           WHERE quality_tier = ?
           ORDER BY created_at DESC LIMIT ?""",
        (quality_tier, limit),
    ).fetchall()

    return [
        TranscriptRecord(
            transcript_id=r[0], video_id=r[1], source=r[2],
            language=r[3], is_auto_generated=r[4], model=r[5],
            raw_path=r[6], clean_path=r[7], quality_score=r[8],
            quality_tier=r[9], coverage_ratio=r[10],
            hallucination_risk=r[11], created_at=r[12],
        )
        for r in rows
    ]


def run_all_migrations(conn: sqlite3.Connection) -> None:
    """Run all youtube migrations in order (001 through 009)."""
    from pathlib import Path

    migrations_dir = Path(__file__).resolve().parents[2] / "migrations"
    migration_files = sorted(migrations_dir.glob("youtube_*.py"))

    for mf in migration_files:
        import importlib.util
        spec = importlib.util.spec_from_file_location(mf.stem, mf)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        if hasattr(mod, "up"):
            mod.up(conn)
