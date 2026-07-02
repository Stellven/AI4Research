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
    require_non_empty_string,
    run_cli,
    validate_schema,
)

SCHEMA = "autosci_runtime_evidence.v1"


def _path_exists(raw_path: str, evidence_path: str | Path | None) -> bool:
    path = Path(raw_path).expanduser()
    if path.is_absolute():
        return path.exists()
    evidence_dir = Path(evidence_path).resolve().parent if evidence_path else HARNESS_DIR
    return any(candidate.exists() for candidate in (evidence_dir / path, ARTIFACT_HARNESS_DIR / path, HARNESS_DIR / path))


def _completed(reasons: list[str], runtime: dict[str, Any]) -> bool:
    status = str(runtime.get("status") or "")
    if status != "completed":
        return False
    if runtime.get("exit_code") != 0:
        reasons.append("completed runtime evidence must have exit_code=0")
    return True


def _gate_source_fetch(runtime: dict[str, Any], reasons: list[str]) -> None:
    candidates = require_non_empty_list(runtime.get("candidates"), "outputs.runtime.candidates", reasons)
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            reasons.append(f"candidates[{index}] must be an object")
            continue
        if not candidate.get("title"):
            reasons.append(f"candidates[{index}].title must be present")
        if not candidate.get("ranking_rationale"):
            reasons.append(f"candidates[{index}].ranking_rationale must be present")


def _gate_experiment(runtime: dict[str, Any], reasons: list[str]) -> None:
    require_non_empty_list(runtime.get("metrics"), "outputs.runtime.metrics", reasons)
    require_non_empty_string(runtime.get("outcome"), "outputs.runtime.outcome", reasons)
    if runtime.get("result_collected") is not True:
        reasons.append("completed experiment runtime evidence must set result_collected=true")


def _gate_poster(runtime: dict[str, Any], reasons: list[str]) -> None:
    if runtime.get("browser_rendered") is not True:
        reasons.append("completed poster runtime evidence must set browser_rendered=true")
    if runtime.get("png_exported") is not True:
        reasons.append("completed poster runtime evidence must set png_exported=true")
    overflow = str(runtime.get("overflow_probe") or "").strip().lower()
    if overflow not in {"ok", "pass", "passed", "none", "no_overflow"}:
        reasons.append("completed poster runtime evidence must pass overflow_probe")


def _gate_compile(runtime: dict[str, Any], reasons: list[str], path: str | Path | None) -> None:
    pdf_path = str(runtime.get("pdf_path") or "").strip()
    if runtime.get("pdf_generated") is not True and not pdf_path:
        reasons.append("completed compile runtime evidence must set pdf_generated=true or provide pdf_path")
    if pdf_path and not _path_exists(pdf_path, path):
        reasons.append(f"outputs.runtime.pdf_path does not exist: {pdf_path}")


def _gate_email(runtime: dict[str, Any], reasons: list[str]) -> None:
    if runtime.get("delivered") is not True:
        reasons.append("completed email runtime evidence must set delivered=true")
    require_non_empty_string(runtime.get("provider"), "outputs.runtime.provider", reasons)


def evaluate(payload: dict[str, Any], path: str | Path | None = None):
    reasons, warnings = validate_schema(payload, SCHEMA)
    runtime = outputs(payload).get("runtime")
    if not isinstance(runtime, dict):
        reasons.append("outputs.runtime must be an object")
        return finish(payload, reasons, warnings, path=path)

    action = require_non_empty_string(runtime.get("action"), "outputs.runtime.action", reasons)
    require_non_empty_string(runtime.get("command_run"), "outputs.runtime.command_run", reasons)
    if not has_any_evidence_ids(runtime.get("evidence_ids")):
        reasons.append("outputs.runtime.evidence_ids must contain at least one id")
    checks = require_non_empty_list(runtime.get("checks"), "outputs.runtime.checks", reasons)
    for index, check in enumerate(checks):
        if not isinstance(check, dict):
            reasons.append(f"checks[{index}] must be an object")
            continue
        if check.get("status") == "error" and payload.get("status") == "completed":
            reasons.append(f"completed runtime evidence cannot include error check: {check.get('check')}")

    approval_ref = str(runtime.get("approval_ref") or payload.get("inputs", {}).get("approval_ref") or "").strip()
    if not approval_ref or approval_ref.upper() == "N/A":
        reasons.append("runtime evidence must include approval_ref in outputs.runtime or inputs")

    if _completed(reasons, runtime):
        if action in {"daily_arxiv_prepare_finalize", "init_sources", "discover_literature"}:
            _gate_source_fetch(runtime, reasons)
        elif action in {"run_experiment", "run_pilot_experiment"}:
            _gate_experiment(runtime, reasons)
        elif action == "build_poster":
            _gate_poster(runtime, reasons)
        elif action == "compile_paper":
            _gate_compile(runtime, reasons, path)
        elif action == "send_email":
            _gate_email(runtime, reasons)
        else:
            warnings.append(f"no action-specific completed runtime checks are defined for {action}")
        check_artifact_paths(payload, path, reasons)
    elif payload.get("status") == "inconclusive" and not limitations(payload):
        reasons.append("inconclusive runtime evidence must explain limitations")

    return finish(payload, reasons, warnings, path=path)


if __name__ == "__main__":
    raise SystemExit(run_cli(evaluate, SCHEMA))
