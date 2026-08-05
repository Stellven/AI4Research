from __future__ import annotations

import pytest

from harness.lib.research_orchestration.resilience import (
    CONTRACT_INVALID,
    RATE_LIMIT,
    TRANSIENT_FAILURE,
    RetryController,
    classify_runtime_failure,
    retry_delay_seconds,
)


def test_429_retry_after_seconds_is_honored_without_real_sleep() -> None:
    sleeps: list[float] = []
    calls = 0

    def operation() -> dict:
        nonlocal calls
        calls += 1
        if calls == 1:
            return {"status_code": 429, "headers": {"Retry-After": "7"}, "error": "too many requests"}
        return {"status": "completed"}

    controller = RetryController(sleeper=sleeps.append, clock=lambda: 10.0)
    result = controller.run(
        operation,
        {"max_attempts": 2, "retry_on": [RATE_LIMIT], "base_seconds": 1, "cap_seconds": 60},
    )

    assert result["status"] == "completed"
    assert sleeps == [7.0]
    assert [row["classification"] for row in controller.attempt_metadata] == [RATE_LIMIT, "success"]


def test_repeated_429_stops_at_max_attempts_without_off_by_one() -> None:
    calls = 0

    def operation() -> dict:
        nonlocal calls
        calls += 1
        return {"status_code": 429, "headers": {"Retry-After": "1"}, "error": "quota exhausted"}

    controller = RetryController(sleeper=lambda _delay: None, clock=lambda: 0.0)
    result = controller.run(operation, {"max_attempts": 3, "retry_on": [RATE_LIMIT]})

    assert calls == 3
    assert result["status_code"] == 429
    assert controller.attempt_metadata[-1]["will_retry"] is False


def test_transient_exception_recovers_and_metadata_is_secret_safe() -> None:
    calls = 0

    def operation() -> dict:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise TimeoutError("timed out while calling provider with request body sk-secret-value")
        return {"ok": True}

    controller = RetryController(sleeper=lambda _delay: None, clock=lambda: 0.0)
    assert controller.run(operation, {"max_attempts": 2, "retry_on": [TRANSIENT_FAILURE]}) == {"ok": True}

    assert controller.attempt_metadata[0]["classification"] == TRANSIENT_FAILURE
    assert "sk-secret-value" not in str(controller.attempt_metadata)
    assert "request body" not in str(controller.attempt_metadata)


def test_contract_invalid_is_not_retried_even_when_policy_mentions_it() -> None:
    calls = 0

    def operation() -> dict:
        nonlocal calls
        calls += 1
        return {"status": "contract_invalid", "error": "schema validation failed"}

    controller = RetryController(sleeper=lambda _delay: None, clock=lambda: 0.0)
    result = controller.run(operation, {"max_attempts": 4, "retry_on": [CONTRACT_INVALID, RATE_LIMIT]})

    assert calls == 1
    assert result["status"] == "contract_invalid"
    assert controller.attempt_metadata[0]["will_retry"] is False


def test_retry_delay_uses_cap_and_injectable_jitter() -> None:
    assert retry_delay_seconds(TRANSIENT_FAILURE, 5, base_seconds=2, cap_seconds=10, jitter_source=lambda: 0) == 10
    assert retry_delay_seconds(TRANSIENT_FAILURE, 2, base_seconds=10, cap_seconds=100, jitter_source=lambda: 0.5) == 21.0


def test_plain_rate_limit_planning_text_is_not_classified_as_rate_limit() -> None:
    text = "risk: single evaluator; rate limit parameter value deferred to later"
    assert classify_runtime_failure({"status": "failed", "error": text}) != RATE_LIMIT


def test_max_attempts_must_be_positive() -> None:
    with pytest.raises(ValueError, match="max_attempts"):
        RetryController().run(lambda: {"ok": True}, {"max_attempts": 0})
