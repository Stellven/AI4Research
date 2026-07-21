"""Sprints source — scans sprint status files for count and newest mtime."""

from __future__ import annotations

import os
import time

HARNESS_DIR = os.environ.get("HARNESS_DIR", os.path.expanduser("~/.solar/harness"))
SPRINTS_DIR = os.path.join(HARNESS_DIR, "sprints")


def fetch(deep: bool, deadline: float) -> dict:
    t0 = time.monotonic()

    try:
        if not os.path.isdir(SPRINTS_DIR):
            return {
                "name": "sprints",
                "status": "degraded",
                "duration_ms": int((time.monotonic() - t0) * 1000),
                "note": f"sprints dir not found: {SPRINTS_DIR}",
            }

        count = 0
        newest_mtime = 0.0
        with os.scandir(SPRINTS_DIR) as it:
            for entry in it:
                if entry.name.endswith(".status.json") and entry.is_file(follow_symlinks=False):
                    count += 1
                    mtime = entry.stat().st_mtime
                    if mtime > newest_mtime:
                        newest_mtime = mtime

        age_s = int(time.time() - newest_mtime) if newest_mtime else -1
        note = f"{count} sprint status files"
        if newest_mtime:
            note += f"; newest {age_s}s ago"

        return {
            "name": "sprints",
            "status": "ok",
            "duration_ms": int((time.monotonic() - t0) * 1000),
            "note": note,
        }
    except PermissionError as exc:
        return {
            "name": "sprints",
            "status": "degraded",
            "duration_ms": int((time.monotonic() - t0) * 1000),
            "note": f"permission denied: {exc}",
        }
    except Exception as exc:
        return {
            "name": "sprints",
            "status": "error",
            "duration_ms": int((time.monotonic() - t0) * 1000),
            "note": str(exc)[:200],
        }
