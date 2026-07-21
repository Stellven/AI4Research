"""Read-only status projection for the existing Monitor bridge / status surface.

Projects a run's append-only event log into the field shape the existing
status/monitor surface already understands (job/async_state/attempt/blocker/
next_poll_at). Pure read — never writes harness core state, so existing
wake/dispatch/status behavior is unchanged (C3 acceptance).
"""

from __future__ import annotations

from typing import Any

from ..core.controller import GeminiDRController
from ..schemas.persistence import EventLog


def project_status(run_ref: str, event_log: EventLog) -> dict[str, Any]:
    snap = GeminiDRController.rebuild(run_ref, event_log)
    handle = snap.handle
    blocker = None
    if handle is not None and handle.async_state.value in ("waiting_human", "reauth_required"):
        blocker = f"waiting_human:{handle.async_state.value}"
    return {
        "run_ref": run_ref,
        "controller_state": snap.state.value,
        "async_state": handle.async_state.value if handle else None,
        "attempt": snap.attempt,
        "next_poll_at": handle.next_poll_at if handle else None,
        "blocker": blocker,
        "terminal": snap.state.value in ("done", "fail"),
        "result_status": snap.result.status.value if snap.result else None,
    }
