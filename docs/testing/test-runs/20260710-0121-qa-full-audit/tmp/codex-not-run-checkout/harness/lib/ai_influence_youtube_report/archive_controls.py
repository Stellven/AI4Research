"""Dry-run archive/delivery controls."""

from __future__ import annotations

from typing import Any


def report_archive_queue_item(report_id: str, archive_dir: str, *, dry_run: bool = True) -> dict[str, Any]:
    return {
        "schema_version": "report_archive_queue_item.v1",
        "report_id": report_id,
        "archive_dir": archive_dir,
        "mode": "dry-run" if dry_run else "ready",
        "status": "queued",
    }


def chatgpt_project_archive_request(session_url: str, *, project: str = "杂项") -> dict[str, Any]:
    return {
        "schema_version": "chatgpt_project_archive_request.v1",
        "session_url": session_url,
        "project": project,
        "status": "stub_only",
    }
