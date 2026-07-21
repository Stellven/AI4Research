import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "migrations"))

from youtube.premium_escape import (
    PREMIUM_API_KEY_ENV,
    PREMIUM_FALLBACK_REASON,
    PremiumRetryExhaustedError,
    PremiumSecretMissingError,
    estimate_cost_usd,
    execute_premium_asr,
    fallback_backend,
    load_premium_api_key,
    mark_call_completed,
    reserve_budget,
    should_trigger_premium,
)
from youtube_010_premium_asr_calls import up as m010


def test_estimate_cost_usd():
    assert estimate_cost_usd(10) == 0.06
    assert estimate_cost_usd(1.2) == 0.012


def test_reserve_budget_and_complete():
    conn = sqlite3.connect(":memory:")
    m010(conn)
    call = reserve_budget(conn, transcript_id="t1", audio_minutes=30, day="2026-05-28")
    assert call.status == "reserved"
    mark_call_completed(conn, call.call_id)
    row = conn.execute("SELECT status FROM youtube_premium_asr_calls WHERE call_id = ?", (call.call_id,)).fetchone()
    assert row[0] == "completed"


def test_budget_exceeded():
    conn = sqlite3.connect(":memory:")
    m010(conn)
    reserve_budget(conn, transcript_id="t1", audio_minutes=3000, day="2026-05-28")
    with pytest.raises(ValueError, match="premium_budget_exceeded"):
        reserve_budget(conn, transcript_id="t2", audio_minutes=400, day="2026-05-28")


def test_fallback_backend():
    assert fallback_backend(api_available=False, quota_ok=False) == "faster_whisper_large_v3"


def test_should_trigger_premium_contract():
    assert should_trigger_premium(priority="P0", entity_recall=0.70) is True
    assert should_trigger_premium(priority="P0", entity_recall=0.69) is False
    assert should_trigger_premium(priority="P1", entity_recall=0.95) is False


def test_load_premium_api_key_from_env(monkeypatch):
    monkeypatch.setenv(PREMIUM_API_KEY_ENV, " sk-test ")
    assert load_premium_api_key() == "sk-test"


def test_execute_premium_asr_requires_secret():
    conn = sqlite3.connect(":memory:")
    m010(conn)
    with pytest.raises(PremiumSecretMissingError):
        execute_premium_asr(
            conn,
            transcript_id="t1",
            audio_minutes=10,
            transcribe_fn=lambda **_: {"text": "ok"},
            priority="P0",
            entity_recall=0.9,
            baseline_quality_score=0.60,
            premium_quality_score=0.71,
            api_key=None,
        )


def test_execute_premium_asr_success_marks_completed():
    conn = sqlite3.connect(":memory:")
    m010(conn)

    result = execute_premium_asr(
        conn,
        transcript_id="t1",
        audio_minutes=11.2,
        transcribe_fn=lambda **kwargs: {"text": "ok", "attempt": kwargs["attempt"]},
        priority="P0",
        entity_recall=0.91,
        baseline_quality_score=0.62,
        premium_quality_score=0.71,
        api_key="sk-test",
        day="2026-05-28",
    )

    row = conn.execute(
        "SELECT status, cost_usd, provider, model FROM youtube_premium_asr_calls WHERE call_id = ?",
        (result.call_id,),
    ).fetchone()
    assert result.status == "completed"
    assert result.backend == "premium"
    assert result.attempts == 1
    assert result.quality_score_delta == 0.09
    assert row == ("completed", 0.072, "openai", "gpt-4o-transcribe")


def test_execute_premium_asr_retries_then_fails():
    class RetryableError(RuntimeError):
        status_code = 500

    conn = sqlite3.connect(":memory:")
    m010(conn)
    attempts = {"count": 0}

    def _transcribe(**_: object) -> dict[str, str]:
        attempts["count"] += 1
        raise RetryableError("api 5xx")

    with pytest.raises(PremiumRetryExhaustedError, match="api 5xx"):
        execute_premium_asr(
            conn,
            transcript_id="t1",
            audio_minutes=9.2,
            transcribe_fn=_transcribe,
            priority="P0",
            entity_recall=0.88,
            baseline_quality_score=0.51,
            premium_quality_score=0.70,
            api_key="sk-test",
            day="2026-05-28",
        )

    row = conn.execute(
        "SELECT status FROM youtube_premium_asr_calls WHERE transcript_id = ?",
        ("t1",),
    ).fetchone()
    assert attempts["count"] == 3
    assert row[0] == "failed"


def test_not_triggered_returns_fallback_reason_without_ledger_write():
    conn = sqlite3.connect(":memory:")
    m010(conn)

    result = execute_premium_asr(
        conn,
        transcript_id="t1",
        audio_minutes=5,
        transcribe_fn=lambda **_: {"text": "unused"},
        priority="P1",
        entity_recall=0.95,
        baseline_quality_score=0.60,
        premium_quality_score=0.80,
        api_key="sk-test",
    )

    count = conn.execute("SELECT COUNT(*) FROM youtube_premium_asr_calls").fetchone()[0]
    assert result.status == "not_triggered"
    assert result.backend == "faster_whisper_large_v3"
    assert result.fallback_reason == "trigger_not_met"
    assert result.call_id is None
    assert count == 0
