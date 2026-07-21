"""Dispatch gate hint — injects capability hint into dispatch context.

Fail-open: on any exception, returns the original context unchanged and
writes a warning to stderr.  The hint must never block dispatch.
"""

from __future__ import annotations

import json
import sys
from typing import Any


def inject_gate_hint(ctx: str, sid: str) -> str:
    """Inject a gate-readiness hint into a dispatch context string.

    Parameters
    ----------
    ctx:
        JSON-encoded dispatch context string.
    sid:
        Sprint ID to tag in the hint payload.

    Returns the context string with an added ``gate_hint`` field, or the
    original *ctx* unchanged if anything goes wrong.
    """
    try:
        data = json.loads(ctx)
    except Exception:
        print(
            f"[dispatch_gate_hint] WARN: failed to parse context for sid={sid}; returning original",
            file=sys.stderr,
        )
        return ctx

    try:
        hints: list[dict[str, Any]] = data.get("gate_hints", [])

        hint = {
            "source": "dispatch_gate_hint",
            "sprint_id": sid,
            "status": "gate_ready",
            "views_registered": 5,
        }

        # Avoid duplicate injection
        for existing in hints:
            if existing.get("sprint_id") == sid and existing.get("source") == "dispatch_gate_hint":
                return ctx

        hints.append(hint)
        data["gate_hints"] = hints
        return json.dumps(data, separators=(",", ":"))
    except Exception:
        print(
            f"[dispatch_gate_hint] WARN: failed to inject hint for sid={sid}; returning original",
            file=sys.stderr,
        )
        return ctx
