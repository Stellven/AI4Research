"""Status source — probes coordinator liveness via coord-status --json."""

from __future__ import annotations

import json
import os
import subprocess
import time

HARNESS_DIR = os.environ.get("HARNESS_DIR", os.path.expanduser("~/.solar/harness"))
_BIN = os.path.join(os.path.dirname(HARNESS_DIR), "bin", "solar-harness")
_TIMEOUT = 1.5


def fetch(deep: bool, deadline: float) -> dict:
    t0 = time.monotonic()
    remaining = max(0.2, deadline - t0)

    try:
        proc = subprocess.run(
            [_BIN, "coord-status"],
            capture_output=True, text=True,
            timeout=min(remaining, _TIMEOUT),
        )
        if proc.returncode != 0:
            return {
                "name": "status",
                "status": "degraded",
                "duration_ms": int((time.monotonic() - t0) * 1000),
                "note": f"coord-status exit {proc.returncode}: {proc.stderr.strip()[:100]}",
            }
        data = json.loads(proc.stdout.strip())
        running = data.get("running", False)
        stale = data.get("stale_lock", False)
        ok = running and not stale
        return {
            "name": "status",
            "status": "ok" if ok else "degraded",
            "duration_ms": int((time.monotonic() - t0) * 1000),
            "note": "" if ok else f"coordinator not running (stale_lock={stale})",
        }
    except subprocess.TimeoutExpired:
        return {
            "name": "status",
            "status": "degraded",
            "duration_ms": int((time.monotonic() - t0) * 1000),
            "note": "timeout: coord-status exceeded 1.5s",
        }
    except (json.JSONDecodeError, FileNotFoundError) as exc:
        return {
            "name": "status",
            "status": "degraded",
            "duration_ms": int((time.monotonic() - t0) * 1000),
            "note": str(exc)[:200],
        }
    except Exception as exc:
        return {
            "name": "status",
            "status": "error",
            "duration_ms": int((time.monotonic() - t0) * 1000),
            "note": str(exc)[:200],
        }
