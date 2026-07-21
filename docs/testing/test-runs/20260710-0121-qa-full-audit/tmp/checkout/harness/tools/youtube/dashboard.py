"""Dashboard aggregation for YouTube transcript runtime state."""
from __future__ import annotations

import sqlite3
from typing import Any


def _count(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> int:
    return int(conn.execute(sql, params).fetchone()[0])


def aggregate(conn: sqlite3.Connection) -> dict[str, Any]:
    return {
        "subtitle_tracks_count": _count(conn, "SELECT COUNT(*) FROM youtube_subtitle_tracks"),
        "accepted_by_source_tier_breakdown": {
            "T0": _count(conn, "SELECT COUNT(*) FROM youtube_transcripts WHERE quality_tier = 'T0'"),
            "T1": _count(conn, "SELECT COUNT(*) FROM youtube_transcripts WHERE quality_tier = 'T1'"),
            "T2": _count(conn, "SELECT COUNT(*) FROM youtube_transcripts WHERE quality_tier = 'T2'"),
            "T3": _count(conn, "SELECT COUNT(*) FROM youtube_transcripts WHERE quality_tier = 'T3'"),
        },
        "pending_by_priority": {
            tier: _count(conn, "SELECT COUNT(*) FROM youtube_transcript_jobs WHERE status IN ('pending','failed') AND priority = ?", (tier,))
            for tier in ("P0", "P1", "P2", "P3")
        },
        "failed_by_error_code": {
            code: _count(conn, "SELECT COUNT(*) FROM youtube_transcript_jobs WHERE error_code = ?", (code,))
            for code in ("bot_check", "no_caption", "asr_low_quality", "timeout", "max_attempts")
        },
        "model_success_rate": _model_success_rate(conn),
        "quality_score_distribution": {
            "gte_0_85": _count(conn, "SELECT COUNT(*) FROM youtube_transcripts WHERE quality_score >= 0.85"),
            "gte_0_70": _count(conn, "SELECT COUNT(*) FROM youtube_transcripts WHERE quality_score >= 0.70"),
            "lt_0_50": _count(conn, "SELECT COUNT(*) FROM youtube_transcripts WHERE quality_score < 0.50"),
        },
        "metadata_only_count": _count(conn, "SELECT COUNT(*) FROM youtube_transcript_jobs WHERE status = 'metadata_only'"),
        "report_eligible_count": _count(conn, "SELECT COUNT(*) FROM youtube_transcripts WHERE quality_tier IN ('T0','T1','T2')"),
        "premium_cost_today": float(
            conn.execute("SELECT COALESCE(SUM(cost_usd), 0.0) FROM youtube_premium_asr_calls WHERE status IN ('reserved','completed')").fetchone()[0]
        ),
    }


def _model_success_rate(conn: sqlite3.Connection) -> float:
    total = _count(conn, "SELECT COUNT(*) FROM youtube_asr_runs")
    if total == 0:
        return 0.0
    passed = _count(conn, "SELECT COUNT(*) FROM youtube_asr_runs WHERE quality_score IS NOT NULL AND quality_score >= 0.50")
    return round(passed / total, 4)
