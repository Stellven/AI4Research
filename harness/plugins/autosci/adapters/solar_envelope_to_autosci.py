"""Normalize Solar operator envelopes for the AutoSci backend bridge.

The scheduler speaks in artifact contracts and routes.  The AutoSci bridge
predates that contract and historically expected ``output_dir`` plus
action-specific values under ``inputs``.  This module is the compatibility
boundary: scheduler-owned destinations must win over the bridge's legacy
defaults, while old fixture envelopes remain supported.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class EnvelopeContractError(ValueError):
    """The scheduler envelope cannot be represented safely by the bridge."""


_OBJECTIVE_AS_TOPIC_ACTIONS = {
    "discover_literature",
    "evaluate_ideas",
    "generate_ideas",
}


def load_envelope(path: str | Path, *, action: str | None = None) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return normalize_envelope(data, action=action)


def _route_map(envelope: dict[str, Any], direction: str) -> dict[str, str]:
    routes = envelope.get("artifact_routes")
    if not isinstance(routes, dict):
        return {}
    raw = routes.get(direction)
    if not isinstance(raw, dict):
        return {}
    return {
        str(artifact_type): str(path).strip()
        for artifact_type, path in raw.items()
        if str(artifact_type).strip() and str(path).strip()
    }


def _normalized_path_text(value: Any) -> str:
    return str(value or "").strip().replace("\\", "/").rstrip("/")


def _scheduler_output_dir(envelope: dict[str, Any]) -> str:
    produces = _route_map(envelope, "produces")
    if not produces:
        return ""
    destinations = list(dict.fromkeys(produces.values()))
    if len(destinations) != 1:
        raise EnvelopeContractError(
            "AutoSci bridge requires one scheduler output directory; "
            f"received {len(destinations)} distinct artifact routes"
        )
    destination = destinations[0]
    write_scope = [
        str(item).strip()
        for item in (envelope.get("write_scope") or [])
        if str(item).strip()
    ]
    if write_scope and not any(
        _normalized_path_text(destination) == _normalized_path_text(item)
        for item in write_scope
    ):
        raise EnvelopeContractError(
            "scheduler artifact route is outside the operator write_scope"
        )
    return destination


def normalize_envelope(
    envelope: dict[str, Any],
    *,
    action: str | None = None,
) -> dict[str, Any]:
    normalized = dict(envelope)
    normalized.setdefault("task_id", "task-autosci-fixture")
    normalized.setdefault("sprint_id", "sprint-autosci-fixture")
    normalized.setdefault("node_id", "node-autosci-fixture")

    scheduler_output_dir = _scheduler_output_dir(normalized)
    configured_output_dir = str(normalized.get("output_dir") or "").strip()
    if scheduler_output_dir:
        if configured_output_dir and (
            _normalized_path_text(configured_output_dir)
            != _normalized_path_text(scheduler_output_dir)
        ):
            raise EnvelopeContractError(
                "legacy output_dir conflicts with scheduler artifact_routes.produces"
            )
        normalized["output_dir"] = scheduler_output_dir

    raw_inputs = normalized.get("inputs")
    if raw_inputs is not None and not isinstance(raw_inputs, dict):
        raise EnvelopeContractError("inputs must be an object")
    inputs = dict(raw_inputs or {})
    retrieval = normalized.get("retrieval_contract")
    if action == "discover_literature" and retrieval is not None:
        if not isinstance(retrieval, dict):
            raise EnvelopeContractError("retrieval_contract must be an object")
        # Scheduler already verified the immutable projection before dispatch.
        # Never let an action-specific prose field override its contract.
        inputs["retrieval_contract"] = retrieval
        inputs["topic"] = retrieval["subject"]
        inputs["query"] = retrieval["search_queries"][0]
    objective = str(normalized.get("objective") or "").strip()
    if objective:
        inputs.setdefault("request", objective)
        if action in _OBJECTIVE_AS_TOPIC_ACTIONS:
            inputs.setdefault("topic", objective)

    consumes = _route_map(normalized, "consumes")
    if consumes:
        # Preserve the complete typed routing table for actions that need to
        # resolve dependency artifacts.  Never guess an action-specific file
        # from a directory here; that would weaken the frozen contract.
        inputs.setdefault("artifact_routes", consumes)
    normalized["inputs"] = inputs

    scheduler_contract = bool(normalized.get("artifact_routes") or normalized.get("work_dir"))
    normalized.setdefault("mode", "solar_native" if scheduler_contract else "fixture")
    return normalized
