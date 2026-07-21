"""Premium ASR budget reservation and fallback helpers."""
from __future__ import annotations

import datetime as dt
import sqlite3
import uuid
from dataclasses import dataclass


PRICE_PER_MINUTE_USD = 0.006
DAILY_BUDGET_USD = 20.0


@dataclass
class PremiumCall:
    call_id: str
    transcript_id: str
    provider: str
    model: str
    cost_usd: float
    status: str


def estimate_cost_usd(audio_minutes: float) -> float:
    return round(max(audio_minutes, 0.0) * PRICE_PER_MINUTE_USD, 4)


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


def fallback_backend(*, api_available: bool, quota_ok: bool) -> str:
    return "premium" if api_available and quota_ok else "faster_whisper_large_v3"
