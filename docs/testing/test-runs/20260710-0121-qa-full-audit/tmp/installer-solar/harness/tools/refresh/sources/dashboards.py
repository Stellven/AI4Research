"""Dashboards source — checks whether port 8765 is listening.

Per design decision D5 (OQ5 deferred): the /refresh endpoint does not exist.
If port is not listening → skipped.
If port is listening but /refresh absent → degraded.
"""

from __future__ import annotations

import socket
import time

_HOST = "127.0.0.1"
_PORT = 8765
_CONNECT_TIMEOUT = 1.0


def fetch(deep: bool, deadline: float) -> dict:
    t0 = time.monotonic()
    remaining = max(0.2, deadline - t0)

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(min(remaining, _CONNECT_TIMEOUT))
        rc = sock.connect_ex((_HOST, _PORT))
        sock.close()

        if rc != 0:
            return {
                "name": "dashboards",
                "status": "skipped",
                "duration_ms": int((time.monotonic() - t0) * 1000),
                "note": f"port {_PORT} not listening",
            }
        return {
            "name": "dashboards",
            "status": "degraded",
            "duration_ms": int((time.monotonic() - t0) * 1000),
            "note": f"port {_PORT} listening but /refresh endpoint not implemented (OQ5 deferred)",
        }
    except socket.timeout:
        return {
            "name": "dashboards",
            "status": "skipped",
            "duration_ms": int((time.monotonic() - t0) * 1000),
            "note": f"timeout: port {_PORT} connect probe exceeded {_CONNECT_TIMEOUT}s",
        }
    except OSError:
        return {
            "name": "dashboards",
            "status": "skipped",
            "duration_ms": int((time.monotonic() - t0) * 1000),
            "note": f"port {_PORT} not listening",
        }
    except Exception as exc:
        return {
            "name": "dashboards",
            "status": "error",
            "duration_ms": int((time.monotonic() - t0) * 1000),
            "note": str(exc)[:200],
        }
