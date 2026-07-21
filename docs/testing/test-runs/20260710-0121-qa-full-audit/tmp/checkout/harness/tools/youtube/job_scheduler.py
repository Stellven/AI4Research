"""Job scheduling and retry state machine module (R6).

Implements next_retry_at polling + 5 error_code backoff state machine.
Error codes: bot_check / no_caption / asr_low_quality / timeout / max_attempts.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import sqlite3


@dataclass
class Job:
    job_id: str
    video_id: str
    job_type: str
    status: str
    priority: str
    error_code: Optional[str]
    attempt_count: int
    next_retry_at: Optional[str]
    max_attempts: int = 3


@dataclass
class JobUpdate:
    job_id: str
    new_status: str
    next_retry_at: Optional[str]
    error_code: Optional[str]
    attempt_count: int


# 5 error codes per R6
VALID_ERROR_CODES = frozenset({
    "bot_check", "no_caption", "asr_low_quality", "timeout", "max_attempts",
})

# Backoff delays per error code and attempt number (seconds)
_BACKOFF_SCHEDULE: dict[str, list[int]] = {
    "bot_check": [60, 300, 900],
    "no_caption": [0, 0, 0],
    "asr_low_quality": [30, 120, 600],
    "timeout": [120, 600, 1800],
    "max_attempts": [],
}

# Priority ordering for dequeue
_PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}

# Terminal statuses
TERMINAL_STATUSES = frozenset({"succeeded", "cancelled", "metadata_only", "quarantined"})


def dequeue_ready_jobs(
    conn: sqlite3.Connection,
    limit: int = 50,
    priority_filter: Optional[list[str]] = None,
) -> list[Job]:
    """Select jobs ready for execution.

    Ready = status='pending' or (status='failed' AND next_retry_at <= now),
    not in terminal state, attempts < max_attempts.
    """
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%fZ")

    query = """
        SELECT job_id, video_id, job_type, status, priority,
               error_code, attempt_count, next_retry_at, max_attempts
        FROM youtube_transcript_jobs
        WHERE status IN ('pending', 'failed')
          AND (next_retry_at IS NULL OR next_retry_at <= ?)
          AND attempt_count < max_attempts
    """
    params: list = [now_utc]

    if priority_filter:
        placeholders = ",".join("?" * len(priority_filter))
        query += f" AND priority IN ({placeholders})"
        params.extend(priority_filter)

    query += " ORDER BY CASE priority"
    for p, order in _PRIORITY_ORDER.items():
        query += f" WHEN '{p}' THEN {order}"
    query += " END ASC, created_at ASC LIMIT ?"
    params.append(limit)

    rows = conn.execute(query, params).fetchall()

    return [
        Job(
            job_id=r[0], video_id=r[1], job_type=r[2],
            status=r[3], priority=r[4], error_code=r[5],
            attempt_count=r[6], next_retry_at=r[7], max_attempts=r[8],
        )
        for r in rows
    ]


def handle_job_failure(
    conn: sqlite3.Connection,
    job_id: str,
    error_code: str,
    attempt_count: int,
    max_attempts: int = 3,
) -> JobUpdate:
    """Process job failure and compute next retry/backoff.

    Per R6: 5 error_code backoff state machine.
    Returns JobUpdate with new status, next_retry_at, and error_code.
    """
    if error_code not in VALID_ERROR_CODES:
        raise ValueError(f"Invalid error_code: {error_code}")

    new_attempt = attempt_count + 1

    # max_attempts reached → terminal
    if new_attempt >= max_attempts:
        return JobUpdate(
            job_id=job_id,
            new_status="failed",
            next_retry_at=None,
            error_code="max_attempts",
            attempt_count=new_attempt,
        )

    # no_caption → immediate retry with metadata_only fallback
    if error_code == "no_caption" and new_attempt >= max_attempts:
        return JobUpdate(
            job_id=job_id,
            new_status="metadata_only",
            next_retry_at=None,
            error_code=error_code,
            attempt_count=new_attempt,
        )

    # Calculate backoff delay
    schedule = _BACKOFF_SCHEDULE.get(error_code, [60, 300, 900])
    delay_idx = min(attempt_count, len(schedule) - 1) if schedule else 0
    delay_sec = schedule[delay_idx] if schedule else 0

    if delay_sec == 0:
        next_retry = None  # immediate retry
    else:
        next_retry = (
            datetime.now(timezone.utc) + timedelta(seconds=delay_sec)
        ).strftime("%Y-%m-%dT%H:%M:%fZ")

    return JobUpdate(
        job_id=job_id,
        new_status="failed",
        next_retry_at=next_retry,
        error_code=error_code,
        attempt_count=new_attempt,
    )


def apply_job_update(conn: sqlite3.Connection, update: JobUpdate) -> None:
    """Write JobUpdate to database."""
    conn.execute(
        """UPDATE youtube_transcript_jobs
           SET status = ?, next_retry_at = ?, error_code = ?, attempt_count = ?,
               finished_at = CASE WHEN ? IN ('succeeded', 'cancelled', 'metadata_only', 'quarantined')
                             THEN strftime('%Y-%m-%dT%H:%M:%fZ', 'now') ELSE finished_at END
           WHERE job_id = ?""",
        (
            update.new_status, update.next_retry_at,
            update.error_code, update.attempt_count,
            update.new_status, update.job_id,
        ),
    )
    conn.commit()


def mark_job_terminal(
    conn: sqlite3.Connection,
    job_id: str,
    terminal_status: str,
) -> None:
    """Mark a job as terminal (metadata_only or quarantined)."""
    if terminal_status not in ("metadata_only", "quarantined"):
        raise ValueError(f"Invalid terminal status: {terminal_status}")

    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%fZ")
    conn.execute(
        """UPDATE youtube_transcript_jobs
           SET status = ?, next_retry_at = NULL,
               finished_at = ?
           WHERE job_id = ?""",
        (terminal_status, now_utc, job_id),
    )
    conn.commit()


def compute_backoff_delay(error_code: str, attempt_count: int) -> int:
    """Return backoff delay in seconds for given error and attempt. Pure function."""
    schedule = _BACKOFF_SCHEDULE.get(error_code, [60, 300, 900])
    if not schedule:
        return 0
    idx = min(attempt_count, len(schedule) - 1)
    return schedule[idx]
