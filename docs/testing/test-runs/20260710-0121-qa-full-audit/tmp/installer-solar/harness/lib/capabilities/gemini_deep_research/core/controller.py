"""GeminiDRController — O1..O6 orchestration over the operator port.

Owns the outcome state machine, persists every step as an append-only event,
and supports full state reconstruction by replaying those events. Browser-side
actions are delegated to a BrowserOperatorPort (A1: controller never clicks).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from ..schemas.models import (
    AsyncState,
    DRPlan,
    DRResult,
    DRRunHandle,
    InvalidResearchRequest,
    OptimizedPrompt,
    ResearchRequest,
    ResultStatus,
)
from ..schemas.persistence import EventLog
from .ports import BrowserOperatorPort
from .retry import MIN_REFS, Disposition, RetryPolicy, evaluate_success
from .state_machine import (
    TERMINAL_STATES,
    ControllerState,
    assert_transition,
)

DEFAULT_TEMPLATE_ID = "li-professor-v1"


class OptimizeFailed(RuntimeError):
    pass


@dataclass
class RunSnapshot:
    """Reconstructed view of a run after event replay."""

    run_ref: str | None
    state: ControllerState
    attempt: int
    handle: DRRunHandle | None
    result: DRResult | None


def _now(clock: Callable[[], datetime] | None) -> datetime:
    return (clock or (lambda: datetime.now(timezone.utc)))()


class GeminiDRController:
    def __init__(
        self,
        operator: BrowserOperatorPort,
        event_log: EventLog | None = None,
        retry_policy: RetryPolicy | None = None,
        template_id: str = DEFAULT_TEMPLATE_ID,
        min_refs: int = MIN_REFS,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.operator = operator
        self.log = event_log or EventLog()
        self.retry = retry_policy or RetryPolicy()
        self.template_id = template_id
        self.min_refs = min_refs
        self._clock = clock

        self.run_ref: str | None = None
        self.state: ControllerState = ControllerState.INPUT
        self.attempt: int = 0
        self.handle: DRRunHandle | None = None
        self.result: DRResult | None = None

    # ---- event helpers -------------------------------------------------
    def _emit(self, event_type: str, payload: dict[str, Any] | None = None) -> None:
        if self.run_ref is None:
            return
        self.log.append(self.run_ref, event_type, payload or {})

    def _goto(self, dst: ControllerState, payload: dict[str, Any] | None = None) -> None:
        assert_transition(self.state, dst)
        self.state = dst
        body = {"state": dst.value}
        if payload:
            body.update(payload)
        self._emit("state_changed", body)

    # ---- O1: entrypoint ------------------------------------------------
    def submit_research(self, req: ResearchRequest) -> DRRunHandle:
        """O1 entrypoint -> drives O2..O4, returns a confirmed running handle.

        Both user-direct and upstream callers use this same function (A1).
        """
        req.validate()
        # O2 produces chat_session_ref which doubles as the run key until the
        # operator assigns a run_ref at submit time. Use request_id as the
        # stable event-stream key so the whole lifecycle is one log.
        self.run_ref = req.request_id
        self.state = ControllerState.INPUT
        self._emit("input_received", {"request": req.to_dict(), "state": self.state.value})

        prompt = self._optimize(req)
        plan = self._submit(prompt)
        handle = self._confirm(plan)
        return handle

    # ---- O2 ------------------------------------------------------------
    def _optimize(self, req: ResearchRequest) -> OptimizedPrompt:
        self._goto(ControllerState.OPTIMIZE)
        prompt = self.operator.optimize_prompt(req, self.template_id)
        try:
            prompt.validate()
        except InvalidResearchRequest as e:
            # No reference directive / empty -> O2 fails, do NOT enter O3.
            self._fail(f"optimize_failed: {e}")
            raise OptimizeFailed(str(e)) from e
        self._emit("optimized", {"prompt": prompt.to_dict()})
        return prompt

    # ---- O3 ------------------------------------------------------------
    def _submit(self, prompt: OptimizedPrompt) -> DRPlan:
        self._goto(ControllerState.SUBMIT)
        self.attempt += 1
        plan = self.operator.submit(prompt)
        # bind canonical run_ref from operator job id once known
        self._emit("submitted", {"plan": plan.to_dict(), "attempt": self.attempt, "job_ref": plan.run_ref})
        return plan

    # ---- O4 ------------------------------------------------------------
    def _confirm(self, plan: DRPlan) -> DRRunHandle:
        if not plan.plan_detected:
            self._fail("plan_not_detected")
            raise RuntimeError("research plan / confirm control not detected")
        self._goto(ControllerState.CONFIRM)
        handle = self.operator.confirm(plan)
        self.handle = handle
        self._emit("confirmed", {"handle": handle.to_dict()})
        return handle

    # ---- O5: poll ------------------------------------------------------
    def poll_once(self, handle: DRRunHandle) -> DRRunHandle:
        if self.state not in (ControllerState.CONFIRM, ControllerState.MONITOR):
            self._goto(ControllerState.MONITOR)
        else:
            self._goto(ControllerState.MONITOR)
        new_handle = self.operator.poll(handle)
        self.handle = new_handle
        self._emit("polled", {"handle": new_handle.to_dict(), "async_state": new_handle.async_state.value})
        return new_handle

    # ---- O5: monitor loop with retry ----------------------------------
    def monitor_to_terminal(self, handle: DRRunHandle, max_polls: int = 200) -> DRResult:
        polls = 0
        while polls < max_polls:
            polls += 1
            handle = self.poll_once(handle)
            disp = self.retry.classify(handle.async_state)

            if disp == Disposition.OK:
                return self._collect(handle)

            if disp == Disposition.WAITING_HUMAN:
                # does not consume attempt; surface blocker, stop autonomous loop
                self._emit("waiting_human", {"async_state": handle.async_state.value})
                return self._fail_result(handle, f"waiting_human:{handle.async_state.value}")

            # transient. Only re-attempt on true terminal-transient states.
            if handle.async_state in (AsyncState.FAILED, AsyncState.TIMEOUT):
                if self.retry.attempts_exhausted(self.attempt):
                    return self._fail_result(handle, f"attempts_exhausted:{handle.async_state.value}")
                self._schedule_retry(handle)
                # caller (or run()) resubmits; break out for re-attempt
                return self._fail_result(handle, f"retry_pending:{handle.async_state.value}")
            # else still running/planning -> keep polling
        return self._fail_result(handle, "max_polls_exceeded")

    def _schedule_retry(self, handle: DRRunHandle) -> None:
        self._goto(ControllerState.RETRY)
        delay = self.retry.backoff_seconds(self.attempt)
        next_at = (_now(self._clock) + timedelta(seconds=delay)).isoformat()
        self._emit("retry_scheduled", {"attempt": self.attempt, "backoff_s": delay, "next_poll_at": next_at})

    # ---- O5 terminal: collect -----------------------------------------
    def _collect(self, handle: DRRunHandle) -> DRResult:
        result = self.operator.collect(handle)
        check = evaluate_success(handle.async_state, result, self.min_refs)
        if check.ok:
            self._goto(ControllerState.DONE)
            result.validate()
            self.result = result
            self._emit("collected", {"result": result.to_dict()})
            self._emit("succeeded", {"run_ref": result.run_ref})
            return result
        # done-but-incomplete -> failed (A3), eligible for retry by caller
        incomplete = DRResult(
            run_ref=result.run_ref,
            status=ResultStatus.FAILED,
            evidence_refs=result.evidence_refs,
            failure_reason=f"incomplete_result: {check.reason}",
        )
        self.result = incomplete
        self._collect_failed(incomplete)
        return incomplete

    def _collect_failed(self, result: DRResult) -> None:
        if self.state != ControllerState.FAIL:
            self._goto(ControllerState.FAIL, {"reason": result.failure_reason})
        self._emit("failed", {"result": result.to_dict()})

    def _fail(self, reason: str) -> None:
        self._goto(ControllerState.FAIL, {"reason": reason})
        self._emit("failed", {"reason": reason})

    def _fail_result(self, handle: DRRunHandle, reason: str) -> DRResult:
        result = DRResult(
            run_ref=handle.run_ref,
            status=ResultStatus.TIMEOUT if "timeout" in reason or "max_polls" in reason else ResultStatus.FAILED,
            evidence_refs=[],
            failure_reason=reason,
        )
        self.result = result
        if self.state != ControllerState.FAIL:
            self._goto(ControllerState.FAIL, {"reason": reason})
        self._emit("failed", {"result": result.to_dict()})
        return result

    # ---- O1..O6 convenience driver ------------------------------------
    def run(self, req: ResearchRequest, max_polls: int = 200) -> DRResult:
        handle = self.submit_research(req)
        return self.monitor_to_terminal(handle, max_polls=max_polls)

    # ---- event-replay reconstruction (C2 acceptance) ------------------
    @classmethod
    def rebuild(cls, run_ref: str, event_log: EventLog) -> RunSnapshot:
        state = ControllerState.INPUT
        attempt = 0
        handle: DRRunHandle | None = None
        result: DRResult | None = None
        seen = False
        for ev in event_log.read(run_ref):
            seen = True
            p = ev.payload
            if "state" in p:
                state = ControllerState(p["state"])
            if ev.type == "submitted" and "attempt" in p:
                attempt = p["attempt"]
            if ev.type == "retry_scheduled" and "attempt" in p:
                attempt = p["attempt"]
            if "handle" in p:
                handle = DRRunHandle.from_dict(p["handle"])
            if ev.type in ("collected", "failed") and "result" in p:
                result = DRResult.from_dict(p["result"])
        if not seen:
            return RunSnapshot(run_ref=None, state=ControllerState.INPUT, attempt=0, handle=None, result=None)
        return RunSnapshot(run_ref=run_ref, state=state, attempt=attempt, handle=handle, result=result)

    def snapshot(self) -> RunSnapshot:
        return RunSnapshot(
            run_ref=self.run_ref,
            state=self.state,
            attempt=self.attempt,
            handle=self.handle,
            result=self.result,
        )

    def is_terminal(self) -> bool:
        return self.state in TERMINAL_STATES
