"""Convert AutoSci experiment results to `experiment_result.v1` evidence."""

from __future__ import annotations

from typing import Any

from .common import evidence_base


def convert(raw: dict[str, Any], envelope: dict[str, Any] | None = None) -> dict[str, Any]:
    envelope = envelope or {}
    inputs = envelope.get("inputs") if isinstance(envelope.get("inputs"), dict) else {}
    execution_mode = str(raw.get("execution_mode") or inputs.get("execution_mode") or envelope.get("mode") or "fixture")
    result = {
        "experiment_id": str(raw.get("experiment_id") or "exp-001"),
        "outcome": str(raw.get("outcome") or "supports"),
        "metrics": list(raw.get("metrics") or [{"name": "fixture_passed", "value": True}]),
        "evidence_ids": list(raw.get("evidence_ids") or ["evidence:autosci-fixture"]),
        "execution_mode": execution_mode,
        "command_run": str(raw.get("command_run") or "fixture-mode:no-external-command"),
        "logs": list(raw.get("logs") or ["Fixture experiment result collected without external command execution."]),
        "exit_code": raw.get("exit_code", 0),
    }
    return evidence_base(
        "experiment_result.v1",
        envelope,
        {"result": result},
        artifacts=list(raw.get("artifacts") or []),
        status=str(raw.get("status") or "completed"),
        limitations=list(raw.get("limitations") or ["Fixture result is deterministic and not a real benchmark run."]),
    )
