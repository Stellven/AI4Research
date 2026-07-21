#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evaluators.scientific.common import (
    finish,
    has_any_evidence_ids,
    outputs,
    require_non_empty_list,
    require_non_empty_string,
    run_cli,
    validate_schema,
)

SCHEMA = "code_evidence_map.v1"


def evaluate(payload: dict[str, Any], path: str | Path | None = None):
    reasons, warnings = validate_schema(payload, SCHEMA)
    mappings = require_non_empty_list(outputs(payload).get("mappings"), "outputs.mappings", reasons)
    for index, mapping in enumerate(mappings):
        if not isinstance(mapping, dict):
            reasons.append(f"mappings[{index}] must be an object")
            continue
        files = require_non_empty_list(mapping.get("files"), f"mappings[{index}].files", reasons)
        mapping_status = require_non_empty_string(
            mapping.get("mapping_status"),
            f"mappings[{index}].mapping_status",
            reasons,
        )
        relevance_label = require_non_empty_string(
            mapping.get("relevance_label"),
            f"mappings[{index}].relevance_label",
            reasons,
        )
        require_non_empty_string(mapping.get("relevance_reason"), f"mappings[{index}].relevance_reason", reasons)
        concrete_files = [
            str(item).strip()
            for item in files
            if isinstance(item, str) and str(item).strip().lower() not in {"n/a", "unknown", "unavailable"}
        ]
        if mapping_status == "mapped":
            if not concrete_files:
                reasons.append(f"mappings[{index}] mapped code evidence requires at least one concrete file path")
            if relevance_label == "unknown":
                reasons.append(f"mappings[{index}] mapped code evidence cannot have unknown relevance")
        if mapping_status == "unknown":
            if relevance_label != "unknown":
                reasons.append(f"mappings[{index}] unknown code evidence must use unknown relevance")
            require_non_empty_string(mapping.get("unknown_reason"), f"mappings[{index}].unknown_reason", reasons)
        if not has_any_evidence_ids(mapping.get("evidence_ids")):
            reasons.append(f"mappings[{index}].evidence_ids must contain at least one id")
    return finish(payload, reasons, warnings, path=path)


if __name__ == "__main__":
    raise SystemExit(run_cli(evaluate, SCHEMA))
