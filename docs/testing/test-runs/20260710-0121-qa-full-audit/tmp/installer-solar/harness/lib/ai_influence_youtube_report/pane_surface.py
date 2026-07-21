"""Pane-facing progress and evidence summaries."""

from __future__ import annotations

from typing import Any


def build_pane_surface(run: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "youtube_report_pane_surface.v1",
        "active_phase": run.get("state", "unknown"),
        "blocking_issue": run.get("blocked_reason", ""),
        "artifact_summary": run.get("artifacts", []),
        "timeline": run.get("step_log", []),
        "handoff": run.get("handoff", {}),
        "eval_sidecars": run.get("eval_sidecars", []),
    }


def handoff_registration_status(handoff_path: str, eval_json_path: str | None = None) -> dict[str, Any]:
    return {
        "schema_version": "handoff_registration.v1",
        "handoff_path": handoff_path,
        "eval_json_path": eval_json_path or "",
        "registered": bool(handoff_path),
        "join_ready": bool(handoff_path and eval_json_path),
    }
