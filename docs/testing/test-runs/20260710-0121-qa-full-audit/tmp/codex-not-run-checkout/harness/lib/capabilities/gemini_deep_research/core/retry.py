"""Retry policy + machine-checkable success criteria (S02 A3).

Defaults are A3 design suggestions; final numbers await human/planner sign-off
(NB6). Parameterised so the values are configurable, not hardcoded business data.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..schemas.models import AsyncState, DRResult, ResultStatus

# A3 success threshold: minimum classified references for success.
MIN_REFS = 3


class Disposition(str, Enum):
    OK = "ok"                      # done -> proceed to collect
    RETRY = "retry"                # transient -> consume attempt, back off
    WAITING_HUMAN = "waiting_human"  # does NOT consume an attempt (A3)
    FATAL = "fatal"                # terminal failure


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    per_attempt_timeout_min: int = 30
    backoff_base_s: int = 30
    backoff_cap_s: int = 300

    def backoff_seconds(self, attempt: int) -> int:
        if attempt < 1:
            attempt = 1
        return min(self.backoff_cap_s, self.backoff_base_s * (2 ** (attempt - 1)))

    def classify(self, async_state: AsyncState) -> Disposition:
        if async_state == AsyncState.DONE:
            return Disposition.OK
        if async_state in (AsyncState.WAITING_HUMAN, AsyncState.REAUTH_REQUIRED):
            return Disposition.WAITING_HUMAN
        if async_state in (AsyncState.FAILED, AsyncState.TIMEOUT):
            return Disposition.RETRY
        # submitted/planning/running -> not terminal, keep monitoring
        return Disposition.RETRY

    def attempts_exhausted(self, attempt: int) -> bool:
        return attempt >= self.max_attempts


@dataclass(frozen=True)
class SuccessCheck:
    ok: bool
    reason: str | None = None


def evaluate_success(handle_state: AsyncState, result: DRResult, min_refs: int = MIN_REFS) -> SuccessCheck:
    """A3 machine-judged success: structural completeness + reference floor.

    Subjective report quality is explicitly NOT a criterion (NB5).
    """
    if handle_state != AsyncState.DONE:
        return SuccessCheck(False, f"async_state={handle_state.value} != done")
    if not (result.report_text and result.report_text.strip()):
        return SuccessCheck(False, "report_text empty")
    if len(result.references) < min_refs:
        return SuccessCheck(False, f"references {len(result.references)} < MIN_REFS {min_refs}")
    categories = {r.category.strip() for r in result.references if r.category and r.category.strip()}
    if len(categories) < 1:
        return SuccessCheck(False, "no category block present")
    for r in result.references:
        try:
            r.validate()
        except Exception as e:  # noqa: BLE001 - surface as structured reason
            return SuccessCheck(False, f"reference invalid: {e}")
    if result.status != ResultStatus.SUCCEEDED:
        return SuccessCheck(False, f"result.status={result.status.value} != succeeded")
    return SuccessCheck(True, None)
