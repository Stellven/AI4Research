#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evaluators.scientific.common import (
    check_artifact_paths,
    finish,
    has_any_evidence_ids,
    limitations,
    outputs,
    require_non_empty_list,
    run_cli,
    validate_schema,
)

SCHEMA = "scientific_report.v1"


def _artifact_paths(payload: dict[str, Any]) -> set[str]:
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        return set()
    return {
        str(artifact.get("path"))
        for artifact in artifacts
        if isinstance(artifact, dict) and artifact.get("path")
    }


def _check_linked_media(items: Any, name: str, artifact_paths: set[str], reasons: list[str]) -> None:
    if items is None:
        return
    if not isinstance(items, list):
        reasons.append(f"{name} must be a list when present")
        return
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            reasons.append(f"{name}[{index}] must be an object")
            continue
        if not has_any_evidence_ids(item.get("evidence_ids")):
            reasons.append(f"{name}[{index}].evidence_ids must contain at least one id")
        artifact_path = str(item.get("artifact_path") or item.get("path") or "").strip()
        if not artifact_path:
            reasons.append(f"{name}[{index}].artifact_path must be present")
        elif artifact_path not in artifact_paths:
            reasons.append(f"{name}[{index}].artifact_path must match a top-level artifact")


def evaluate(payload: dict[str, Any], path: str | Path | None = None):
    reasons, warnings = validate_schema(payload, SCHEMA)
    report = outputs(payload).get("report")
    if not isinstance(report, dict):
        reasons.append("outputs.report must be an object")
        return finish(payload, reasons, warnings, path=path)
    top_limitations = limitations(payload)
    artifact_paths = _artifact_paths(payload)
    if not has_any_evidence_ids(report.get("evidence_ids")):
        reasons.append("outputs.report.evidence_ids must contain at least one id")
    sections = require_non_empty_list(report.get("sections"), "outputs.report.sections", reasons)
    has_limitations_section = False
    has_unsupported_section = False
    for index, section in enumerate(sections):
        if not isinstance(section, dict):
            reasons.append(f"sections[{index}] must be an object")
            continue
        title = str(section.get("title") or section.get("section_id") or "").lower()
        has_limitations_section = has_limitations_section or "limitation" in title
        has_unsupported_section = has_unsupported_section or "unsupported" in title
        if not has_any_evidence_ids(section.get("evidence_ids")):
            reasons.append(f"sections[{index}].evidence_ids must contain at least one id")
        _check_linked_media(section.get("figures"), f"sections[{index}].figures", artifact_paths, reasons)
        _check_linked_media(section.get("tables"), f"sections[{index}].tables", artifact_paths, reasons)
    if not top_limitations:
        reasons.append("reports require top-level limitations")
    if not has_limitations_section:
        reasons.append("reports require a limitations section")
    if report.get("unsupported_claims") and not top_limitations:
        reasons.append("reports with unsupported_claims require top-level limitations")
    if report.get("unsupported_claims") and not has_unsupported_section:
        reasons.append("reports with unsupported_claims require an unsupported claims section")
    _check_linked_media(report.get("figures"), "outputs.report.figures", artifact_paths, reasons)
    _check_linked_media(report.get("tables"), "outputs.report.tables", artifact_paths, reasons)
    check_artifact_paths(payload, path, reasons)
    return finish(payload, reasons, warnings, path=path)


if __name__ == "__main__":
    raise SystemExit(run_cli(evaluate, SCHEMA))
