#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evaluators.scientific.common import (
    ARTIFACT_HARNESS_DIR,
    HARNESS_DIR,
    check_artifact_paths,
    finish,
    has_any_evidence_ids,
    limitations,
    outputs,
    require_non_empty_list,
    run_cli,
    validate_schema,
)

SCHEMA = "publication_bundle.v1"


def _file_exists(raw_path: str, evidence_path: str | Path | None) -> bool:
    path = Path(raw_path).expanduser()
    if path.is_absolute():
        return path.exists()
    evidence_dir = Path(evidence_path).resolve().parent if evidence_path else HARNESS_DIR
    return any(candidate.exists() for candidate in (evidence_dir / path, ARTIFACT_HARNESS_DIR / path, HARNESS_DIR / path))


def evaluate(payload: dict[str, Any], path: str | Path | None = None):
    reasons, warnings = validate_schema(payload, SCHEMA)
    bundle = outputs(payload).get("bundle")
    if not isinstance(bundle, dict):
        reasons.append("outputs.bundle must be an object")
        return finish(payload, reasons, warnings, path=path)
    source_report_id = str(bundle.get("source_report_id") or "")
    evidence_ids = bundle.get("evidence_ids")
    if not has_any_evidence_ids(evidence_ids):
        reasons.append("outputs.bundle.evidence_ids must contain at least one id")
        evidence_ids = []
    if source_report_id and isinstance(evidence_ids, list) and source_report_id not in evidence_ids:
        reasons.append("outputs.bundle.evidence_ids must include source_report_id")
    files = require_non_empty_list(bundle.get("files"), "outputs.bundle.files", reasons)
    for index, item in enumerate(files):
        if not isinstance(item, dict):
            reasons.append(f"files[{index}] must be an object")
            continue
        artifact_type = str(item.get("type") or "").strip()
        raw_path = str(item.get("path") or "").strip()
        if not artifact_type:
            reasons.append(f"files[{index}].type must be present")
        if not raw_path:
            reasons.append(f"files[{index}].path must be present")
        elif not _file_exists(raw_path, path):
            reasons.append(f"files[{index}].path does not exist: {raw_path}")
    if not limitations(payload):
        reasons.append("publication bundles require top-level limitations")
    check_artifact_paths(payload, path, reasons)
    return finish(payload, reasons, warnings, path=path)


if __name__ == "__main__":
    raise SystemExit(run_cli(evaluate, SCHEMA))
