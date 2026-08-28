#!/usr/bin/env python3
"""Classify graph-dispatch command results without changing graph state.

The dispatcher intentionally exits non-zero while an evaluator is waiting for
the Builder's durable operator result.  That is a readiness condition, not an
execution failure.  This module gives the coordinator a structured way to tell
that one case apart from real dispatch errors.
"""

from __future__ import annotations

import json
import sys
from typing import Any


EVALUATOR_WAIT_REASONS = frozenset({"builder_operator_result_pending"})


def classify_evaluator_dispatch_output(raw: str) -> dict[str, Any] | None:
    """Return a normalized waiting payload, or ``None`` for every other result."""
    try:
        payload = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    dispatched = payload.get("dispatched")
    terminalized = payload.get("terminalized")
    skipped = payload.get("skipped")
    if dispatched not in (None, []) or terminalized not in (None, []):
        return None
    if not isinstance(skipped, list) or not skipped:
        return None
    if not all(
        isinstance(item, dict)
        and str(item.get("reason") or "") in EVALUATOR_WAIT_REASONS
        and item.get("complete") is not True
        for item in skipped
    ):
        return None
    nodes = [str(item.get("node") or "") for item in skipped if str(item.get("node") or "")]
    return {
        "reason": "builder_operator_result_pending",
        "node": nodes[0] if len(nodes) == 1 else "",
        "nodes": nodes,
        "waiting_count": len(skipped),
    }


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args != ["evaluator-wait"]:
        return 2
    result = classify_evaluator_dispatch_output(sys.stdin.read())
    if result is None:
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
