"""Shared helpers for AutoSci-to-Solar evidence conversion."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def envelope_value(envelope: dict[str, Any] | None, key: str, default: str) -> str:
    if not envelope:
        return default
    value = envelope.get(key)
    return str(value) if value else default


def evidence_base(
    schema: str,
    envelope: dict[str, Any] | None,
    outputs: dict[str, Any],
    *,
    artifacts: list[dict[str, Any]] | None = None,
    status: str = "completed",
    limitations: list[str] | None = None,
    operator_id: str = "autosci-bridge",
) -> dict[str, Any]:
    envelope = envelope or {}
    return {
        "schema": schema,
        "task_id": envelope_value(envelope, "task_id", "task-autosci-fixture"),
        "sprint_id": envelope_value(envelope, "sprint_id", "sprint-autosci-fixture"),
        "node_id": envelope_value(envelope, "node_id", f"node-{schema.replace('.', '-')}"),
        "status": status,
        "inputs": dict(envelope.get("inputs") or {}),
        "outputs": outputs,
        "artifacts": artifacts or [],
        "provenance": {
            "operator_id": operator_id,
            "implementation_package": "plugins/autosci",
            "timestamp": now_iso(),
        },
        "limitations": limitations or ["fixture-mode adapter output; not a production AutoSci run"],
    }
