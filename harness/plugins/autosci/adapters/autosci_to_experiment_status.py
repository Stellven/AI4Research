"""Convert AutoSci experiment monitor output to `experiment_status.v1` evidence."""

from __future__ import annotations

from typing import Any

from .common import evidence_base


def convert(raw: dict[str, Any], envelope: dict[str, Any] | None = None) -> dict[str, Any]:
    status_report = {
        "experiment_id": str(raw.get("experiment_id") or "exp-001"),
        "state": str(raw.get("state") or "unknown"),
        "observations": list(raw.get("observations") or ["No experiment status observations were supplied."]),
        "next_actions": list(raw.get("next_actions") or ["Collect experiment result evidence or mark the run blocked."]),
        "evidence_ids": list(raw.get("evidence_ids") or ["experiment-status:unknown"]),
    }
    return evidence_base(
        "experiment_status.v1",
        envelope,
        {"status_report": status_report},
        artifacts=list(raw.get("artifacts") or []),
        status=str(raw.get("status") or "completed"),
        limitations=list(raw.get("limitations") or ["Fixture status is bounded to supplied local evidence."]),
    )
