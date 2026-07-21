"""Autopilot source — checks autopilot-state.json mtime.

Does NOT invalidate the autopilot cache (design decision D2: noop).
Degraded if state file missing or findings are >5 minutes stale.
"""

from __future__ import annotations

import os
import time

HARNESS_DIR = os.environ.get("HARNESS_DIR", os.path.expanduser("~/.solar/harness"))
_STATE_FILE = os.path.join(HARNESS_DIR, "state", "autopilot-state.json")
_STALE_THRESHOLD_S = 300  # 5 minutes


def fetch(deep: bool, deadline: float) -> dict:
    t0 = time.monotonic()

    try:
        if not os.path.isfile(_STATE_FILE):
            return {
                "name": "autopilot",
                "status": "degraded",
                "duration_ms": int((time.monotonic() - t0) * 1000),
                "note": "autopilot-state.json not found",
            }

        mtime = os.path.getmtime(_STATE_FILE)
        age_s = time.time() - mtime

        if age_s > _STALE_THRESHOLD_S:
            return {
                "name": "autopilot",
                "status": "degraded",
                "duration_ms": int((time.monotonic() - t0) * 1000),
                "note": f"findings stale: {int(age_s)}s ago (threshold {_STALE_THRESHOLD_S}s)",
            }

        return {
            "name": "autopilot",
            "status": "ok",
            "duration_ms": int((time.monotonic() - t0) * 1000),
            "note": f"findings mtime ok ({int(age_s)}s ago)",
        }
    except Exception as exc:
        return {
            "name": "autopilot",
            "status": "error",
            "duration_ms": int((time.monotonic() - t0) * 1000),
            "note": str(exc)[:200],
        }
