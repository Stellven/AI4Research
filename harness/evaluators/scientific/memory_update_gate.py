#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evaluators.scientific.common import finish, has_any_evidence_ids, outputs, require_non_empty_list, run_cli, validate_schema

SCHEMA = "research_memory_update.v1"


def evaluate(payload: dict[str, Any], path: str | Path | None = None):
    reasons, warnings = validate_schema(payload, SCHEMA)
    changes = require_non_empty_list(outputs(payload).get("changes"), "outputs.changes", reasons)
    for index, change in enumerate(changes):
        if not isinstance(change, dict):
            reasons.append(f"changes[{index}] must be an object")
            continue
        if not has_any_evidence_ids(change.get("evidence_ids")):
            reasons.append(f"changes[{index}].evidence_ids must contain at least one id")
        if change.get("operation") == "delete" and not change.get("approval_ref"):
            reasons.append(f"changes[{index}] delete operation requires approval_ref")
    return finish(payload, reasons, warnings, path=path)


if __name__ == "__main__":
    raise SystemExit(run_cli(evaluate, SCHEMA))
