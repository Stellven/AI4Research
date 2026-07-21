"""KB source — probes knowledge base health via mirage doctor --json.

Checks: drive_status, required mount readiness, qmd binary health, solar_db.
RAGFlow is optional (design D4): absent RAGFlow → not counted as degraded.
"""

from __future__ import annotations

import json
import os
import subprocess
import time

HARNESS_DIR = os.environ.get("HARNESS_DIR", os.path.expanduser("~/.solar/harness"))
_BIN = os.path.join(os.path.dirname(HARNESS_DIR), "bin", "solar-harness")
_TIMEOUT = 2.0


def fetch(deep: bool, deadline: float) -> dict:
    t0 = time.monotonic()
    remaining = max(0.2, deadline - t0)

    try:
        proc = subprocess.run(
            [_BIN, "mirage", "doctor", "--json"],
            capture_output=True, text=True,
            timeout=min(remaining, _TIMEOUT),
        )
        if proc.returncode != 0:
            return {
                "name": "kb",
                "status": "degraded",
                "duration_ms": int((time.monotonic() - t0) * 1000),
                "note": f"mirage doctor exit {proc.returncode}",
            }

        data = json.loads(proc.stdout.strip())
        issues: list[str] = []

        drive_status = data.get("drive_status", "")
        if drive_status not in ("connected", "ok", ""):
            issues.append(f"drive_status={drive_status}")

        mounts = data.get("mounts", [])
        bad = [m for m in mounts if not m.get("ready", True) and not m.get("optional", False)]
        if bad:
            issues.append(f"{len(bad)} required mount(s) not ready")

        qmd_status = data.get("qmd", {}).get("status", "")
        if qmd_status and qmd_status not in ("ok", "healthy", "running"):
            issues.append(f"qmd={qmd_status}")

        if issues:
            return {
                "name": "kb",
                "status": "degraded",
                "duration_ms": int((time.monotonic() - t0) * 1000),
                "note": "; ".join(issues),
            }

        db_mb = data.get("solar_db", {}).get("size_mb")
        note = f"mirage ok"
        if db_mb is not None:
            note += f"; solar_db {db_mb:.0f}MB"
        return {
            "name": "kb",
            "status": "ok",
            "duration_ms": int((time.monotonic() - t0) * 1000),
            "note": note,
        }

    except subprocess.TimeoutExpired:
        return {
            "name": "kb",
            "status": "degraded",
            "duration_ms": int((time.monotonic() - t0) * 1000),
            "note": "timeout: mirage doctor exceeded 2s",
        }
    except json.JSONDecodeError as exc:
        return {
            "name": "kb",
            "status": "degraded",
            "duration_ms": int((time.monotonic() - t0) * 1000),
            "note": f"mirage doctor JSON parse error: {exc}",
        }
    except FileNotFoundError:
        return {
            "name": "kb",
            "status": "degraded",
            "duration_ms": int((time.monotonic() - t0) * 1000),
            "note": f"solar-harness binary not found: {_BIN}",
        }
    except Exception as exc:
        return {
            "name": "kb",
            "status": "error",
            "duration_ms": int((time.monotonic() - t0) * 1000),
            "note": str(exc)[:200],
        }
