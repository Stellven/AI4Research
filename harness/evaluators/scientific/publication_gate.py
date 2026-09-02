#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import io
import json
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


def _resolved_file(raw_path: str, evidence_path: str | Path | None) -> Path | None:
    path = Path(raw_path).expanduser()
    if path.is_absolute():
        return path if path.is_file() else None
    evidence_dir = Path(evidence_path).resolve().parent if evidence_path else HARNESS_DIR
    for candidate in (evidence_dir / path, ARTIFACT_HARNESS_DIR / path, HARNESS_DIR / path):
        if candidate.is_file():
            return candidate
    return None


def _stable_json_sha256(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _json_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {key for child in value.values() for key in _json_keys(child)}
    if isinstance(value, list):
        return {key for child in value for key in _json_keys(child)}
    return set()


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
    files_by_manifest_path: dict[str, dict[str, Any]] = {}
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
        manifest_path = str(item.get("manifest_relative_path") or "").strip()
        if manifest_path:
            if manifest_path in files_by_manifest_path:
                reasons.append(f"duplicate manifest_relative_path: {manifest_path}")
            files_by_manifest_path[manifest_path] = item
        resolved = _resolved_file(raw_path, path) if raw_path else None
        expected_hash = str(item.get("sha256") or "").lower()
        if resolved and expected_hash:
            actual_hash = hashlib.sha256(resolved.read_bytes()).hexdigest()
            if actual_hash != expected_hash:
                reasons.append(f"files[{index}].sha256 does not match file content")
    manifest = bundle.get("delivery_manifest")
    if isinstance(manifest, dict):
        manifest_hash = str(bundle.get("delivery_manifest_sha256") or "").lower()
        if manifest_hash != _stable_json_sha256(manifest):
            reasons.append("outputs.bundle.delivery_manifest_sha256 does not match delivery_manifest")
        rows = [item for item in manifest.get("files") or [] if isinstance(item, dict)]
        expected_paths = [str(item.get("relative_path") or "") for item in rows]
        if set(expected_paths) != set(files_by_manifest_path) or len(expected_paths) != len(files_by_manifest_path):
            reasons.append("outputs.bundle.files does not exactly match delivery_manifest.files")
        for index, row in enumerate(rows):
            relative_path = str(row.get("relative_path") or "")
            item = files_by_manifest_path.get(relative_path)
            if not item:
                continue
            resolved = _resolved_file(str(item.get("path") or ""), path)
            if not resolved:
                continue
            text = resolved.read_text(encoding="utf-8")
            if not text.strip():
                reasons.append(f"delivery_manifest.files[{index}] is empty")
                continue
            required_fields = [str(value) for value in row.get("required_fields") or []]
            media_type = str(row.get("media_type") or "")
            if media_type == "text/csv":
                try:
                    header = next(csv.reader(io.StringIO(text)))
                except (csv.Error, StopIteration):
                    reasons.append(f"delivery_manifest.files[{index}] is not valid CSV")
                    continue
                missing = [field for field in required_fields if field not in header]
                if missing:
                    reasons.append(f"delivery_manifest.files[{index}] is missing CSV columns: {missing}")
            elif media_type == "application/json":
                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError:
                    reasons.append(f"delivery_manifest.files[{index}] is not valid JSON")
                    continue
                missing = [field for field in required_fields if field not in _json_keys(parsed)]
                if missing:
                    reasons.append(f"delivery_manifest.files[{index}] is missing JSON fields: {missing}")
    elif bundle.get("delivery_manifest_sha256"):
        reasons.append("outputs.bundle.delivery_manifest is required when delivery_manifest_sha256 is present")
    if not limitations(payload):
        reasons.append("publication bundles require top-level limitations")
    check_artifact_paths(payload, path, reasons)
    return finish(payload, reasons, warnings, path=path)


if __name__ == "__main__":
    raise SystemExit(run_cli(evaluate, SCHEMA))
