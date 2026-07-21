#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evaluators.scientific.common import finish, has_any_evidence_ids, outputs, require_non_empty_list, run_cli, validate_schema

SCHEMA = "research_method.v1"


def evaluate(payload: dict[str, Any], path: str | Path | None = None):
    reasons, warnings = validate_schema(payload, SCHEMA)
    methods = require_non_empty_list(outputs(payload).get("methods"), "outputs.methods", reasons)
    for index, method in enumerate(methods):
        if not isinstance(method, dict):
            reasons.append(f"methods[{index}] must be an object")
            continue
        require_non_empty_list(method.get("procedure"), f"methods[{index}].procedure", reasons)
        require_non_empty_list(method.get("source_papers"), f"methods[{index}].source_papers", reasons)
        if not has_any_evidence_ids(method.get("evidence_ids")):
            reasons.append(f"methods[{index}].evidence_ids must contain at least one id")
    return finish(payload, reasons, warnings, path=path)


if __name__ == "__main__":
    raise SystemExit(run_cli(evaluate, SCHEMA))
