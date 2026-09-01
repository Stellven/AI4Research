#!/usr/bin/env python3
"""Validate retained dataset/model/runner package metadata."""
from __future__ import annotations

from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evaluators.scientific.common import finish, outputs, run_cli, validate_schema


SCHEMA = "dataset_manifest.v1"
REQUIRED_ROLES = {"runner", "model_config", "model_weights", "dataset_tokens", "retained_source_text"}


def evaluate(payload: dict[str, Any], path: str | Path | None = None):
    reasons, warnings = validate_schema(payload, SCHEMA)
    manifest = outputs(payload).get("dataset_manifest")
    if not isinstance(manifest, dict):
        reasons.append("outputs.dataset_manifest must be an object")
        return finish(payload, reasons, warnings, path=path)
    assets = [item for item in manifest.get("assets") or [] if isinstance(item, dict)]
    roles = {str(item.get("role") or "") for item in assets}
    missing = sorted(REQUIRED_ROLES - roles)
    if missing:
        reasons.append("dataset manifest is missing asset roles: " + ", ".join(missing))
    execution = manifest.get("execution") if isinstance(manifest.get("execution"), dict) else {}
    hashes = execution.get("input_sha256s") if isinstance(execution.get("input_sha256s"), dict) else {}
    runner = next((item for item in assets if item.get("role") == "runner"), {})
    if execution.get("runner_sha256") != runner.get("sha256"):
        reasons.append("execution.runner_sha256 does not match the retained runner asset")
    for item in assets:
        if item.get("role") == "runner":
            continue
        if hashes.get(str(item.get("path") or "")) != item.get("sha256"):
            reasons.append(f"execution input hash does not match asset {item.get('role')}")
    dataset = manifest.get("dataset") if isinstance(manifest.get("dataset"), dict) else {}
    if int(dataset.get("case_count") or 0) < 3:
        reasons.append("dataset manifest must retain at least three measured cases")
    if len(set(dataset.get("seeds") or [])) < 3:
        reasons.append("dataset manifest must retain at least three distinct seeds")
    return finish(payload, reasons, warnings, path=path)


if __name__ == "__main__":
    raise SystemExit(run_cli(evaluate, SCHEMA))
