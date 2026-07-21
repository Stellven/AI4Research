"""Premium ASR trigger, budget reservation, and fallback helpers."""
from __future__ import annotations

import datetime as dt
import math
import os
import sqlite3
import uuid
from dataclasses import dataclass
from typing import Any, Callable


PRICE_PER_MINUTE_USD = 0.006
DAILY_BUDGET_USD = 20.0
PREMIUM_PRIORITY = "P0"
PREMIUM_ENTITY_RECALL_THRESHOLD = 0.70
PREMIUM_API_KEY_ENV = "SOLAR_YOUTUBE_PREMIUM_OPENAI_KEY"
PREMIUM_FALLBACK_REASON = "openai_5xx_exhausted"


@dataclass
class PremiumCall:
    call_id: str
    transcript_id: str
    provider: str
    model: str
    cost_usd: float
    status: str


@dataclass
class PremiumExecutionResult:
    status: str
    backend: str
    call_id: str | None
    attempts: int
    fallback_reason: str | None = None
    provider_response: dict[str, Any] | None = None
    quality_score_delta: float | None = None


class PremiumSecretMissingError(RuntimeError):
    """Raised when the OpenAI premium ASR secret is unavailable."""


class PremiumRetryExhaustedError(RuntimeError):
    """Raised when the provider failed after all retry attempts."""


def estimate_cost_usd(audio_minutes: float) -> float:
    billable_minutes = math.ceil(max(audio_minutes, 0.0))
    return round(billable_minutes * PRICE_PER_MINUTE_USD, 4)


def should_trigger_premium(
    *,
    priority: str,
    entity_recall: float,
    threshold: float = PREMIUM_ENTITY_RECALL_THRESHOLD,
) -> bool:
    return str(priority).upper() == PREMIUM_PRIORITY and float(entity_recall) >= float(threshold)


def load_premium_api_key(env: dict[str, str] | None = None) -> str | None:
    source = env if env is not None else os.environ
    value = source.get(PREMIUM_API_KEY_ENV, "")
    return value.strip() or None


def reserve_budget(
    conn: sqlite3.Connection,
    *,
    transcript_id: str,
    audio_minutes: float,
    provider: str = "openai",
    model: str = "gpt-4o-transcribe",
    day: str | None = None,
) -> PremiumCall:
    cost_usd = estimate_cost_usd(audio_minutes)
    budget_day = day or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    current = conn.execute(
        """SELECT COALESCE(SUM(cost_usd), 0.0) FROM youtube_premium_asr_calls
           WHERE budget_day = ? AND status IN ('reserved', 'completed')""",
        (budget_day,),
    ).fetchone()[0]
    if float(current) + cost_usd > DAILY_BUDGET_USD:
        raise ValueError("premium_budget_exceeded")
    call_id = f"pac-{uuid.uuid4().hex[:12]}"
    conn.execute(
        """INSERT INTO youtube_premium_asr_calls
           (call_id, transcript_id, provider, model, cost_usd, budget_day, status)
           VALUES (?, ?, ?, ?, ?, ?, 'reserved')""",
        (call_id, transcript_id, provider, model, cost_usd, budget_day),
    )
    conn.commit()
    return PremiumCall(call_id=call_id, transcript_id=transcript_id, provider=provider, model=model, cost_usd=cost_usd, status="reserved")


def mark_call_completed(conn: sqlite3.Connection, call_id: str) -> None:
    conn.execute(
        "UPDATE youtube_premium_asr_calls SET status = 'completed' WHERE call_id = ?",
        (call_id,),
    )
    conn.commit()


def mark_call_failed(conn: sqlite3.Connection, call_id: str) -> None:
    conn.execute(
        "UPDATE youtube_premium_asr_calls SET status = 'failed' WHERE call_id = ?",
        (call_id,),
    )
    conn.commit()


def fallback_backend(*, api_available: bool, quota_ok: bool) -> str:
    return "premium" if api_available and quota_ok else "faster_whisper_large_v3"


def execute_premium_asr(
    conn: sqlite3.Connection,
    *,
    transcript_id: str,
    audio_minutes: float,
    transcribe_fn: Callable[..., dict[str, Any]],
    priority: str,
    entity_recall: float,
    baseline_quality_score: float,
    premium_quality_score: float,
    day: str | None = None,
    api_key: str | None = None,
    provider: str = "openai",
    model: str = "gpt-4o-transcribe",
    max_retries: int = 3,
    retryable_status_codes: tuple[int, ...] = (429, 500, 502, 503, 504),
) -> PremiumExecutionResult:
    if not should_trigger_premium(priority=priority, entity_recall=entity_recall):
        return PremiumExecutionResult(
            status="not_triggered",
            backend="faster_whisper_large_v3",
            call_id=None,
            attempts=0,
            fallback_reason="trigger_not_met",
        )

    secret = api_key or load_premium_api_key()
    if not secret:
        raise PremiumSecretMissingError(PREMIUM_API_KEY_ENV)

    call = reserve_budget(
        conn,
        transcript_id=transcript_id,
        audio_minutes=audio_minutes,
        provider=provider,
        model=model,
        day=day,
    )
    attempts = 0
    last_exc: Exception | None = None
    while attempts < max_retries:
        attempts += 1
        try:
            payload = transcribe_fn(
                api_key=secret,
                transcript_id=transcript_id,
                audio_minutes=audio_minutes,
                provider=provider,
                model=model,
                attempt=attempts,
            )
            mark_call_completed(conn, call.call_id)
            return PremiumExecutionResult(
                status="completed",
                backend="premium",
                call_id=call.call_id,
                attempts=attempts,
                provider_response=payload,
                quality_score_delta=round(float(premium_quality_score) - float(baseline_quality_score), 4),
            )
        except Exception as exc:  # pragma: no cover - branch covered by tests with fake exceptions
            last_exc = exc
            status_code = getattr(exc, "status_code", None)
            if status_code not in retryable_status_codes:
                mark_call_failed(conn, call.call_id)
                raise
    mark_call_failed(conn, call.call_id)
    raise PremiumRetryExhaustedError(str(last_exc or PREMIUM_FALLBACK_REASON))
