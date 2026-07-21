"""Tests for job_scheduler module — B2 acceptance."""
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "migrations"))

from youtube.job_scheduler import (
    dequeue_ready_jobs, handle_job_failure, apply_job_update,
    mark_job_terminal, compute_backoff_delay, JobUpdate,
)
from youtube_005_transcript_jobs import up as m005


def _insert_job(conn, job_id="job-test-001", video_id="v1", job_type="asr",
                priority="P0", status="pending", attempt_count=0,
                max_attempts=3, next_retry_at=None, error_code=None):
    conn.execute(
        """INSERT INTO youtube_transcript_jobs
           (job_id, video_id, job_type, priority, status, attempt_count,
            max_attempts, next_retry_at, error_code)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (job_id, video_id, job_type, priority, status, attempt_count,
         max_attempts, next_retry_at, error_code),
    )
    conn.commit()


@pytest.fixture
def db_conn():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA journal_mode=WAL")
    m005(conn)
    yield conn
    conn.close()


class TestDequeueReadyJobs:
    def test_dequeues_pending(self, db_conn):
        _insert_job(db_conn)
        jobs = dequeue_ready_jobs(db_conn)
        assert len(jobs) == 1
        assert jobs[0].job_id == "job-test-001"

    def test_respects_priority_filter(self, db_conn):
        _insert_job(db_conn, job_id="j1", priority="P0")
        _insert_job(db_conn, job_id="j2", priority="P3")
        jobs = dequeue_ready_jobs(db_conn, priority_filter=["P0"])
        assert len(jobs) == 1
        assert jobs[0].priority == "P0"

    def test_skips_future_retry(self, db_conn):
        _insert_job(db_conn, job_id="j-future", status="failed",
                     next_retry_at="2099-01-01T00:00:00Z", attempt_count=1)
        jobs = dequeue_ready_jobs(db_conn)
        assert len(jobs) == 0

    def test_includes_ready_retry(self, db_conn):
        _insert_job(db_conn, job_id="j-ready", status="failed",
                     next_retry_at="2020-01-01T00:00:00Z", attempt_count=1)
        jobs = dequeue_ready_jobs(db_conn)
        assert len(jobs) == 1

    def test_limit(self, db_conn):
        for i in range(10):
            _insert_job(db_conn, job_id=f"j-{i}")
        jobs = dequeue_ready_jobs(db_conn, limit=3)
        assert len(jobs) == 3

    def test_skips_terminal_jobs(self, db_conn):
        _insert_job(db_conn, job_id="j-succeeded", status="succeeded")
        _insert_job(db_conn, job_id="j-pending", status="pending")
        jobs = dequeue_ready_jobs(db_conn)
        assert len(jobs) == 1
        assert jobs[0].job_id == "j-pending"


class TestHandleJobFailure:
    def test_bot_check_backoff(self):
        update = handle_job_failure(
            conn=None, job_id="j1", error_code="bot_check", attempt_count=0,
        )
        assert update.new_status == "failed"
        assert update.next_retry_at is not None
        assert update.attempt_count == 1

    def test_no_caption_immediate(self):
        update = handle_job_failure(
            conn=None, job_id="j1", error_code="no_caption", attempt_count=0,
        )
        assert update.next_retry_at is None

    def test_asr_low_quality_has_delay(self):
        update = handle_job_failure(
            conn=None, job_id="j1", error_code="asr_low_quality", attempt_count=0,
        )
        assert update.next_retry_at is not None
        assert update.attempt_count == 1

    def test_max_attempts_terminal(self):
        update = handle_job_failure(
            conn=None, job_id="j1", error_code="bot_check",
            attempt_count=2, max_attempts=3,
        )
        assert update.error_code == "max_attempts"

    def test_invalid_error_code(self):
        with pytest.raises(ValueError, match="Invalid error_code"):
            handle_job_failure(
                conn=None, job_id="j1", error_code="bad_code", attempt_count=0,
            )


class TestComputeBackoff:
    def test_bot_check_increases(self):
        d0 = compute_backoff_delay("bot_check", 0)
        d1 = compute_backoff_delay("bot_check", 1)
        assert d1 > d0

    def test_no_caption_zero(self):
        assert compute_backoff_delay("no_caption", 0) == 0

    def test_max_attempts_zero(self):
        assert compute_backoff_delay("max_attempts", 0) == 0


class TestMarkTerminal:
    def test_metadata_only(self, db_conn):
        _insert_job(db_conn)
        mark_job_terminal(db_conn, "job-test-001", "metadata_only")
        row = db_conn.execute(
            "SELECT status, finished_at FROM youtube_transcript_jobs WHERE job_id = ?",
            ("job-test-001",),
        ).fetchone()
        assert row[0] == "metadata_only"
        assert row[1] is not None

    def test_quarantined(self, db_conn):
        _insert_job(db_conn)
        mark_job_terminal(db_conn, "job-test-001", "quarantined")
        row = db_conn.execute(
            "SELECT status FROM youtube_transcript_jobs WHERE job_id = ?",
            ("job-test-001",),
        ).fetchone()
        assert row[0] == "quarantined"

    def test_invalid_status(self, db_conn):
        _insert_job(db_conn)
        with pytest.raises(ValueError, match="Invalid terminal status"):
            mark_job_terminal(db_conn, "job-test-001", "running")


class TestApplyUpdate:
    def test_applies_update(self, db_conn):
        _insert_job(db_conn)
        update = JobUpdate(
            job_id="job-test-001", new_status="failed",
            next_retry_at=None, error_code="timeout", attempt_count=1,
        )
        apply_job_update(db_conn, update)
        row = db_conn.execute(
            "SELECT status, error_code, attempt_count FROM youtube_transcript_jobs WHERE job_id = ?",
            ("job-test-001",),
        ).fetchone()
        assert row[0] == "failed"
        assert row[1] == "timeout"
        assert row[2] == 1
