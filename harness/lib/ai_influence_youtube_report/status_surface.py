"""Reader-safe status/dashboard payloads."""

from __future__ import annotations

from collections import Counter
from typing import Any


FORBIDDEN = {"video_id", "V00x", "raw_refs", "pipeline_fields"}


def build_status_surface(run: dict[str, Any]) -> dict[str, Any]:
    gate = run.get("gate_decisions", [])
    groups = run.get("groups", [])
    payload = {
        "schema_version": "youtube_report_status_surface.v1",
        "run_id": run.get("run_id"),
        "state": run.get("state"),
        "gate_counts": dict(Counter(item.get("grade") for item in gate)),
        "group_counts": dict(Counter(item.get("group_type") for item in groups)),
        "browser_agent": run.get("browser_agent", {}),
        "validator": run.get("validator", {}),
        "archive": run.get("archive", {}),
        "blocked_reason": run.get("blocked_reason", ""),
        "blocked_reasons": run.get("blocked_reasons", []),
        "capability_usage": run.get("capability_usage", []),
        "artifacts": run.get("artifacts", []),
        "chapter_state": run.get("chapter_state", {}),
        "chapter_verifications": run.get("chapter_verifications", []),
        "repair_summaries": run.get("repair_summaries", []),
        "quality": run.get("quality", {}),
        "sidecar_refs": run.get("sidecar_refs", []),
    }
    _assert_no_forbidden(payload)
    return payload


def _assert_no_forbidden(value: Any) -> None:
    if isinstance(value, dict):
        leaked = FORBIDDEN & set(value)
        if leaked:
            raise ValueError(f"status surface leaks internal fields: {sorted(leaked)}")
        for item in value.values():
            _assert_no_forbidden(item)
    elif isinstance(value, list):
        for item in value:
            _assert_no_forbidden(item)
