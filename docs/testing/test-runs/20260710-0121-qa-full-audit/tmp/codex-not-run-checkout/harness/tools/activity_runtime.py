"""Solar Harness — Activity Runtime.

Lifecycle helpers for the command_issued → activity_started →
activity_succeeded | activity_failed | activity_cancelled |
activity_retry_scheduled | activity_handoff arc.

Usage::

    rt = ActivityRuntime(sprint_id="sprint-xyz", session_id="sprint-xyz")

    act_id = "act-build-1"
    rt.command_issued(act_id, target="builder", payload={"round": 1})
    rt.activity_started(act_id, actor="builder")
    # ... work ...
    rt.activity_succeeded(act_id, actor="builder", payload={"files": ["x.py"]})
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from session_log import DuplicateEventError, SessionLog

HARNESS_DIR = os.path.expanduser("~/.solar/harness")


class ActivityRuntime:
    """Typed activity lifecycle helpers over a SessionLog."""

    def __init__(
        self,
        sprint_id: str,
        *,
        session_id: Optional[str] = None,
        harness_dir: Optional[str] = None,
    ) -> None:
        self.sprint_id = sprint_id
        self._session_id = session_id or sprint_id
        self._log = SessionLog(self._session_id, harness_dir=harness_dir)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _correlation(self) -> str:
        return str(uuid.uuid4())

    def _idem(self, act_id: str, phase: str) -> str:
        return f"{phase}:{self.sprint_id}:{act_id}"

    # ------------------------------------------------------------------
    # Lifecycle methods
    # ------------------------------------------------------------------

    def command_issued(
        self,
        activity_id: str,
        *,
        actor: str = "coordinator",
        target: str = "",
        round_num: int = 1,
        payload: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
    ) -> str:
        """Record that a command was dispatched for an activity."""
        idem = self._idem(activity_id, f"command:round{round_num}")
        p = dict(payload or {})
        p.setdefault("target", target)
        p.setdefault("round", round_num)
        try:
            return self._log.append(
                "command_issued",
                actor=actor,
                sprint_id=self.sprint_id,
                activity_id=activity_id,
                idempotency_key=idem,
                correlation_id=correlation_id,
                payload=p,
            )
        except DuplicateEventError:
            return ""

    def activity_started(
        self,
        activity_id: str,
        *,
        actor: str = "builder",
        causation_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> str:
        return self._log.append(
            "activity_started",
            actor=actor,
            sprint_id=self.sprint_id,
            activity_id=activity_id,
            causation_id=causation_id,
            correlation_id=correlation_id,
            payload=payload or {},
        )

    def activity_succeeded(
        self,
        activity_id: str,
        *,
        actor: str = "builder",
        causation_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> str:
        return self._log.append(
            "activity_succeeded",
            actor=actor,
            sprint_id=self.sprint_id,
            activity_id=activity_id,
            causation_id=causation_id,
            correlation_id=correlation_id,
            payload=payload or {},
        )

    def activity_failed(
        self,
        activity_id: str,
        *,
        actor: str = "builder",
        error: str = "",
        causation_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> str:
        p = dict(payload or {})
        if error:
            p.setdefault("error", error)
        return self._log.append(
            "activity_failed",
            actor=actor,
            sprint_id=self.sprint_id,
            activity_id=activity_id,
            causation_id=causation_id,
            correlation_id=correlation_id,
            payload=p,
        )

    def activity_cancelled(
        self,
        activity_id: str,
        *,
        actor: str = "coordinator",
        reason: str = "",
        causation_id: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> str:
        p = dict(payload or {})
        if reason:
            p.setdefault("reason", reason)
        return self._log.append(
            "activity_cancelled",
            actor=actor,
            sprint_id=self.sprint_id,
            activity_id=activity_id,
            causation_id=causation_id,
            payload=p,
        )

    def activity_retry_scheduled(
        self,
        activity_id: str,
        *,
        actor: str = "coordinator",
        retry_num: int = 1,
        delay_secs: int = 0,
        causation_id: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> str:
        p = dict(payload or {})
        p.setdefault("retry_num", retry_num)
        p.setdefault("delay_secs", delay_secs)
        return self._log.append(
            "activity_retry_scheduled",
            actor=actor,
            sprint_id=self.sprint_id,
            activity_id=activity_id,
            causation_id=causation_id,
            payload=p,
        )

    def activity_handoff(
        self,
        activity_id: str,
        *,
        actor: str = "builder",
        to_actor: str = "evaluator",
        round_num: int = 1,
        causation_id: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> str:
        p = dict(payload or {})
        p.setdefault("to_actor", to_actor)
        p.setdefault("round", round_num)
        return self._log.append(
            "activity_handoff",
            actor=actor,
            sprint_id=self.sprint_id,
            activity_id=activity_id,
            causation_id=causation_id,
            payload=p,
        )

    def state_transition(
        self,
        *,
        actor: str = "coordinator",
        from_status: str,
        to_status: str,
        round_num: int = 0,
        correlation_id: Optional[str] = None,
    ) -> str:
        return self._log.append(
            "state_transition",
            actor=actor,
            sprint_id=self.sprint_id,
            correlation_id=correlation_id,
            payload={"from": from_status, "to": to_status, "round": round_num},
        )

    def human_feedback(
        self,
        *,
        actor: str = "human",
        message: str,
        activity_id: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> str:
        p = dict(payload or {})
        p.setdefault("message", message)
        return self._log.append(
            "human_feedback",
            actor=actor,
            sprint_id=self.sprint_id,
            activity_id=activity_id,
            payload=p,
        )


def _now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
