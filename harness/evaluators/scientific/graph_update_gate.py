#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evaluators.scientific.common import finish, has_any_evidence_ids, outputs, require_non_empty_list, run_cli, validate_schema

SCHEMA = "research_graph_update.v1"
ALLOWED_OPERATIONS = {"add", "remove", "confirm", "propose", "no_op"}


def evaluate(payload: dict[str, Any], path: str | Path | None = None):
    reasons, warnings = validate_schema(payload, SCHEMA)
    edges = require_non_empty_list(outputs(payload).get("edges"), "outputs.edges", reasons)
    for index, edge in enumerate(edges):
        if not isinstance(edge, dict):
            reasons.append(f"edges[{index}] must be an object")
            continue
        for field in ("source", "target", "relation"):
            if not str(edge.get(field) or "").strip():
                reasons.append(f"edges[{index}].{field} must be present")
        operation = str(edge.get("operation") or "")
        if operation not in ALLOWED_OPERATIONS:
            reasons.append(f"edges[{index}].operation is not supported: {operation}")
        if not has_any_evidence_ids(edge.get("evidence_ids")):
            reasons.append(f"edges[{index}].evidence_ids must contain at least one id")
        if operation == "remove" and not edge.get("approval_ref"):
            reasons.append(f"edges[{index}] remove operation requires approval_ref")
    return finish(payload, reasons, warnings, path=path)


if __name__ == "__main__":
    raise SystemExit(run_cli(evaluate, SCHEMA))
