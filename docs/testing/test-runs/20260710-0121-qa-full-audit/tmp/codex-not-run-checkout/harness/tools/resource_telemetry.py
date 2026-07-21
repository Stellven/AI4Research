#!/usr/bin/env python3
"""Fail-open runtime resource usage telemetry for Solar data plane.

This module records actual Solar-Harness default-path usage into
sys_resource_usage. It must never block dispatch/context paths: telemetry
failure is diagnostic, not user-visible execution failure.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from solar_db import open_solar_db


def _now_ms(started: float | None) -> int | None:
    if started is None:
        return None
    return int(max(0, (time.monotonic() - started) * 1000))


def _short(text: str | None, limit: int = 500) -> str:
    if not text:
        return ""
    text = " ".join(str(text).split())
    return text[:limit]


def _resource_id(resource_type: str, name: str, version: str = "1.0") -> str:
    return f"{resource_type}:{name}:{version}"


def record_usage(
    resource_type: str,
    name: str,
    *,
    intent: str,
    input_summary: str = "",
    success: bool = True,
    output_summary: str = "",
    error: str = "",
    latency_ms: int | None = None,
    started_at: float | None = None,
    description: str = "",
    keywords: list[str] | None = None,
    config: dict[str, Any] | None = None,
) -> bool:
    """Ensure a sys_resources row exists and append one sys_resource_usage row.

    Returns True when telemetry was recorded. Returns False on any error.
    """
    rid = _resource_id(resource_type, name)
    if latency_ms is None:
        latency_ms = _now_ms(started_at)
    try:
        conn = open_solar_db()
        conn.execute(
            """
            INSERT OR IGNORE INTO sys_resources
              (resource_id, resource_type, name, version, status, description, config,
               layer, executor, keywords, availability, source, last_verified)
            VALUES (?, ?, ?, '1.0', 'active', ?, ?, 'harness', 'python', ?, 'available', 'solar-harness', CURRENT_TIMESTAMP)
            """,
            (
                rid,
                resource_type,
                name,
                description,
                json.dumps(config or {}, ensure_ascii=False),
                json.dumps(keywords or [], ensure_ascii=False),
            ),
        )
        conn.execute(
            "UPDATE sys_resources SET last_verified=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP WHERE resource_id=?",
            (rid,),
        )
        conn.execute(
            """
            INSERT INTO sys_resource_usage
              (resource_id, intent, input_summary, success, latency_ms, output_summary, error)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                rid,
                intent,
                _short(input_summary),
                1 if success else 0,
                latency_ms,
                _short(output_summary),
                _short(error, 800),
            ),
        )
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def record_file_resource_usage(
    path: str | Path,
    *,
    intent: str,
    input_summary: str = "",
    success: bool = True,
    output_summary: str = "",
    error: str = "",
    latency_ms: int | None = None,
    started_at: float | None = None,
) -> bool:
    """Record usage of a file-backed resource without requiring prior registry setup."""
    p = Path(path)
    name = p.name or str(p)
    return record_usage(
        "tool",
        f"file:{name}",
        intent=intent,
        input_summary=input_summary or str(p),
        success=success,
        output_summary=output_summary,
        error=error,
        latency_ms=latency_ms,
        started_at=started_at,
        description=f"File resource used by Solar-Harness: {p}",
        keywords=["file", "solar-harness", "resource-usage"],
        config={"path": str(p)},
    )
