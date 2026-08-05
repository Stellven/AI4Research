"""Runtime failure classification and retry control for research nodes."""

from __future__ import annotations

import asyncio
import email.utils
import random
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


TRANSIENT_FAILURE = "transient_failure"
RATE_LIMIT = "rate_limit"
PROVIDER_UNAVAILABLE = "provider_unavailable"
AUTHORIZATION_REQUIRED = "authorization_required"
PLATFORM_UNAVAILABLE = "platform_unavailable"
CONTRACT_INVALID = "contract_invalid"
OPERATOR_FAILED = "operator_failed"
CANCELLED = "cancelled"

RETRYABLE_CLASSIFICATIONS = frozenset(
    {TRANSIENT_FAILURE, RATE_LIMIT, PROVIDER_UNAVAILABLE}
)

_RATE_LIMIT_RE = re.compile(
    r"\b(429|too many requests|rate[- ]?limit(?:ed| exceeded| reached)|quota (?:exhausted|exceeded|reached)|usage limit)\b",
    re.IGNORECASE,
)
_AUTH_RE = re.compile(
    r"\b(401|403|unauthori[sz]ed|forbidden|auth(?:orization)? (?:required|expired|failed)|api key|invalid token|permission denied)\b",
    re.IGNORECASE,
)
_PROVIDER_RE = re.compile(
    r"\b(502|503|504|service unavailable|provider unavailable|upstream unavailable|bad gateway|gateway timeout)\b",
    re.IGNORECASE,
)
_PLATFORM_RE = re.compile(
    r"\b(command not found|no such file or directory|missing executable|tmux missing|bwrap missing|wsl unavailable|platform unavailable)\b",
    re.IGNORECASE,
)
_CONTRACT_RE = re.compile(
    r"\b(contract invalid|schema validation|validationerror|invalid contract|jsonschema|malformed request)\b",
    re.IGNORECASE,
)
_TRANSIENT_RE = re.compile(
    r"\b(timeout|timed out|temporar(?:y|ily)|connection reset|connection aborted|network unreachable|econnreset|try again)\b",
    re.IGNORECASE,
)


class RetryExhausted(RuntimeError):
    """Raised when an exception-producing operation exhausts retry attempts."""


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 1
    retry_on: tuple[str, ...] = (TRANSIENT_FAILURE, RATE_LIMIT, PROVIDER_UNAVAILABLE)
    base_seconds: float = 1.0
    cap_seconds: float = 60.0


@dataclass
class RetryController:
    """Run a callable under a contract-bounded retry policy."""

    sleeper: Callable[[float], Any] = time.sleep
    clock: Callable[[], float] = time.monotonic
    wall_clock: Callable[[], float | datetime] = time.time
    classifier: Callable[[Any], str] | None = None
    attempt_metadata: list[dict[str, Any]] = field(default_factory=list)

    def run(
        self,
        operation: Callable[[], Any],
        policy: Mapping[str, Any] | RetryPolicy,
        *,
        on_attempt: Callable[[dict[str, Any]], Any] | None = None,
    ) -> Any:
        normalized = _normalize_policy(policy)
        retry_on = set(normalized.retry_on) & set(RETRYABLE_CLASSIFICATIONS)
        if normalized.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")

        self.attempt_metadata = []
        last_exception: Exception | None = None
        classifier = self.classifier or classify_runtime_failure

        for attempt in range(1, normalized.max_attempts + 1):
            started_at = self.clock()
            try:
                result = operation()
            except Exception as exc:
                classification = classifier(exc)
                last_exception = exc
                retry_after = _retry_after_seconds(exc, now=self.wall_clock())
                will_retry = (
                    classification in retry_on
                    and attempt < normalized.max_attempts
                    and classification not in {AUTHORIZATION_REQUIRED, CONTRACT_INVALID, CANCELLED}
                )
                delay = (
                    retry_delay_seconds(
                        classification,
                        attempt,
                        retry_after_seconds=retry_after,
                        base_seconds=normalized.base_seconds,
                        cap_seconds=normalized.cap_seconds,
                        jitter_source=_zero_jitter,
                    )
                    if will_retry
                    else 0.0
                )
                metadata = _attempt_record(
                    attempt=attempt,
                    classification=classification,
                    elapsed_seconds=self.clock() - started_at,
                    will_retry=will_retry,
                    delay_seconds=delay,
                    exception=exc,
                )
                self._record_attempt(metadata, on_attempt)
                if not will_retry:
                    raise
                self.sleeper(delay)
                continue

            classification = classifier(result)
            if classification == "":
                metadata = _attempt_record(
                    attempt=attempt,
                    classification="success",
                    elapsed_seconds=self.clock() - started_at,
                    will_retry=False,
                    delay_seconds=0.0,
                )
                self._record_attempt(metadata, on_attempt)
                return result

            retry_after = _retry_after_seconds(result, now=self.wall_clock())
            will_retry = classification in retry_on and attempt < normalized.max_attempts
            delay = (
                retry_delay_seconds(
                    classification,
                    attempt,
                    retry_after_seconds=retry_after,
                    base_seconds=normalized.base_seconds,
                    cap_seconds=normalized.cap_seconds,
                    jitter_source=_zero_jitter,
                )
                if will_retry
                else 0.0
            )
            metadata = _attempt_record(
                attempt=attempt,
                classification=classification,
                elapsed_seconds=self.clock() - started_at,
                will_retry=will_retry,
                delay_seconds=delay,
            )
            self._record_attempt(metadata, on_attempt)
            if not will_retry:
                return result
            self.sleeper(delay)

        if last_exception is not None:
            raise RetryExhausted(str(last_exception)) from last_exception
        raise RetryExhausted("retry attempts exhausted")

    def _record_attempt(
        self,
        metadata: dict[str, Any],
        on_attempt: Callable[[dict[str, Any]], Any] | None,
    ) -> None:
        self.attempt_metadata.append(metadata)
        if on_attempt is not None:
            on_attempt(dict(metadata))


def classify_runtime_failure(exception_or_result: Any) -> str:
    """Return a stable research-runtime classification, or ``""`` for success."""

    item = exception_or_result
    if isinstance(item, (KeyboardInterrupt, asyncio.CancelledError)):
        return CANCELLED
    if isinstance(item, PermissionError):
        return AUTHORIZATION_REQUIRED
    if isinstance(item, (FileNotFoundError, NotADirectoryError)):
        return PLATFORM_UNAVAILABLE
    if isinstance(item, (TimeoutError, ConnectionError, BrokenPipeError)):
        return TRANSIENT_FAILURE
    if isinstance(item, (ValueError, TypeError)):
        return CONTRACT_INVALID if _CONTRACT_RE.search(str(item)) else OPERATOR_FAILED

    status_code = _status_code(item)
    text = _diagnostic_text(item)
    status = _status_text(item)

    if status in {"cancelled", "canceled"}:
        return CANCELLED
    if status in {"completed", "success", "ok", "ready"}:
        return ""
    if status in {"contract_invalid", "schema_invalid", "invalid_contract"}:
        return CONTRACT_INVALID
    if status in {"authorization_required", "auth_expired", "unauthorized"}:
        return AUTHORIZATION_REQUIRED
    if status in {"platform_unavailable", "environment_blocked"}:
        return PLATFORM_UNAVAILABLE
    if status in {"provider_unavailable", "awaiting_external"}:
        return PROVIDER_UNAVAILABLE
    if status in {"rate_limit", "quota_exhausted", "quota_blocked"}:
        return RATE_LIMIT
    if status in {"failed", "operator_failed"}:
        if _RATE_LIMIT_RE.search(text):
            return RATE_LIMIT
        if _AUTH_RE.search(text):
            return AUTHORIZATION_REQUIRED
        if _PROVIDER_RE.search(text):
            return PROVIDER_UNAVAILABLE
        if _PLATFORM_RE.search(text):
            return PLATFORM_UNAVAILABLE
        if _CONTRACT_RE.search(text):
            return CONTRACT_INVALID
        return OPERATOR_FAILED

    if status_code == 429:
        return RATE_LIMIT
    if status_code in {401, 403}:
        return AUTHORIZATION_REQUIRED
    if status_code in {502, 503, 504}:
        return PROVIDER_UNAVAILABLE
    if status_code in {408, 500}:
        return TRANSIENT_FAILURE
    if status_code and status_code >= 400:
        return OPERATOR_FAILED

    if _RATE_LIMIT_RE.search(text):
        return RATE_LIMIT
    if _AUTH_RE.search(text):
        return AUTHORIZATION_REQUIRED
    if _PROVIDER_RE.search(text):
        return PROVIDER_UNAVAILABLE
    if _PLATFORM_RE.search(text):
        return PLATFORM_UNAVAILABLE
    if _CONTRACT_RE.search(text):
        return CONTRACT_INVALID
    if _TRANSIENT_RE.search(text):
        return TRANSIENT_FAILURE
    if isinstance(item, BaseException):
        return OPERATOR_FAILED
    return ""


def retry_delay_seconds(
    classification: str,
    attempt: int,
    *,
    retry_after_seconds: float | int | str | None = None,
    base_seconds: float = 1.0,
    cap_seconds: float = 60.0,
    jitter_source: Callable[[], float] | None = None,
) -> float:
    """Compute capped exponential backoff with optional deterministic jitter."""

    if attempt < 1:
        raise ValueError("attempt must be >= 1")
    if base_seconds < 0:
        raise ValueError("base_seconds must be >= 0")
    if cap_seconds < 0:
        raise ValueError("cap_seconds must be >= 0")

    retry_after = _coerce_retry_after_seconds(retry_after_seconds)
    if classification == RATE_LIMIT and retry_after is not None:
        delay = retry_after
    else:
        delay = float(base_seconds) * (2 ** (attempt - 1))

    delay = min(float(cap_seconds), max(0.0, float(delay)))
    if jitter_source is not None and delay > 0:
        jitter_value = max(0.0, min(1.0, float(jitter_source())))
        delay = min(float(cap_seconds), delay + jitter_value * min(delay * 0.1, float(base_seconds)))
    return round(delay, 6)


def _normalize_policy(policy: Mapping[str, Any] | RetryPolicy) -> RetryPolicy:
    if isinstance(policy, RetryPolicy):
        return policy
    if not isinstance(policy, Mapping):
        raise ValueError("policy must be a mapping or RetryPolicy")
    return RetryPolicy(
        max_attempts=int(policy.get("max_attempts", 1)),
        retry_on=tuple(str(item) for item in policy.get("retry_on", ())),
        base_seconds=float(policy.get("base_seconds", 1.0)),
        cap_seconds=float(policy.get("cap_seconds", 60.0)),
    )


def _attempt_record(
    *,
    attempt: int,
    classification: str,
    elapsed_seconds: float,
    will_retry: bool,
    delay_seconds: float,
    exception: Exception | None = None,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "attempt": attempt,
        "classification": classification,
        "elapsed_seconds": round(max(0.0, float(elapsed_seconds)), 6),
        "will_retry": bool(will_retry),
        "delay_seconds": round(max(0.0, float(delay_seconds)), 6),
    }
    if exception is not None:
        record["exception_type"] = type(exception).__name__
    return record


def _status_code(item: Any) -> int | None:
    value = _value_from(item, "status_code", "http_status", "code")
    try:
        code = int(value)
    except Exception:
        return None
    return code if code > 0 else None


def _status_text(item: Any) -> str:
    value = _value_from(item, "classification", "failure_classification", "status", "state", "reason")
    return str(value or "").strip().lower()


def _diagnostic_text(item: Any) -> str:
    parts: list[str] = []
    if isinstance(item, BaseException):
        parts.append(str(item))
    if isinstance(item, Mapping):
        for key in ("error", "message", "stderr", "stdout", "output", "log_tail", "reason"):
            value = item.get(key)
            if value is not None:
                parts.append(str(value))
    else:
        for key in ("error", "message", "stderr", "stdout", "text", "reason"):
            value = getattr(item, key, None)
            if value is not None:
                parts.append(str(value))
    return "\n".join(parts)


def _value_from(item: Any, *keys: str) -> Any:
    if isinstance(item, Mapping):
        for key in keys:
            if key in item:
                return item[key]
    for key in keys:
        if hasattr(item, key):
            return getattr(item, key)
    return None


def _retry_after_seconds(
    item: Any, *, now: float | datetime | None = None
) -> float | None:
    if isinstance(item, Mapping):
        headers = item.get("headers")
        value = item.get("retry_after_seconds") or item.get("retry_after")
    else:
        headers = getattr(item, "headers", None)
        value = getattr(item, "retry_after_seconds", None) or getattr(item, "retry_after", None)

    if value is None and isinstance(headers, Mapping):
        value = headers.get("Retry-After") or headers.get("retry-after")
    return _coerce_retry_after_seconds(value, now=now)


def _coerce_retry_after_seconds(
    value: float | int | str | None, *, now: float | datetime | None = None
) -> float | None:
    if value is None:
        return None
    try:
        seconds = float(value)
        return max(0.0, seconds)
    except Exception:
        pass
    if isinstance(value, str):
        try:
            parsed = email.utils.parsedate_to_datetime(value)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            current = _as_utc_datetime(now)
            return max(
                0.0,
                (parsed.astimezone(timezone.utc) - current).total_seconds(),
            )
        except Exception:
            return None
    return None


def _as_utc_datetime(value: float | datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return datetime.fromtimestamp(float(value), tz=timezone.utc)


def _zero_jitter() -> float:
    return 0.0


def random_jitter() -> float:
    """Default jitter source for callers that want non-deterministic spreading."""

    return random.random()
