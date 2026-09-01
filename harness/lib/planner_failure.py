"""Derive one typed Elastic Planner failure from retained artifacts."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


FAILURE_SCHEMA = "solar.planner_failure.v1"
FAILURE_FILENAME = "planner_failure.json"

STAGE_BY_CALL_DIR = {
    "decision_call": "strategy",
    "plan_call": "plan",
    "fidelity_call": "fidelity",
    "direct_response_call": "direct_response",
    "direct_response_review_call": "direct_response_review",
    "capsule_selection_call": "capsule_selection",
    "capsule_fit_review_call": "capsule_fit",
    "composition_selection_call": "composition_selection",
    "composition_fit_review_call": "composition_fit",
}

_SEMANTIC_REJECTIONS = (
    ("planning_decision_validation.json", "strategy"),
    ("plan_validation.json", "plan_validation"),
    ("plan_fidelity.json", "fidelity"),
    ("direct_response_review.json", "direct_response_review"),
)
_EXECUTION_REJECTIONS = (
    ("capsule_selection_validation.json", "capsule_selection"),
    ("capsule_fit_review.json", "capsule_fit"),
    ("composition_selection_validation.json", "composition_selection"),
    ("composition_fit_review.json", "composition_fit"),
    ("capsule_binding_validation.json", "capsule_binding"),
    ("evaluation_plan_validation.json", "evaluation_plan"),
)

RETRY_SAFE_CODES = frozenset(
    {
        "provider_timeout",
        "provider_quota",
        "provider_error",
        "provider_output_missing",
        "provider_output_invalid",
        "malformed_provider_events",
        "planner_deadline_exhausted",
        "operator_timeout",
    }
)


def failure_path(output_root: Path) -> Path:
    return Path(output_root) / FAILURE_FILENAME


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    tmp = Path(raw)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def make_failure(
    *,
    stage: str,
    code: str,
    detail: str = "",
    node_id: str | None = None,
    receipt_ref: str | None = None,
    retry_safe: bool | None = None,
) -> dict[str, Any]:
    code = str(code or "failed").strip() or "failed"
    return {
        "schema_version": FAILURE_SCHEMA,
        "artifact_role": "control_plane_receipt",
        "stage": str(stage or "unknown").strip() or "unknown",
        "code": code,
        "detail": str(detail or "")[:2000],
        "node_id": str(node_id).strip() if node_id else None,
        "receipt_ref": str(receipt_ref) if receipt_ref else None,
        "retry_safe": bool(code in RETRY_SAFE_CODES) if retry_safe is None else bool(retry_safe),
        "before_execution": True,
    }


def _failed_receipts(output_root: Path) -> list[tuple[float, Path, dict[str, Any]]]:
    rows: list[tuple[float, Path, dict[str, Any]]] = []
    for path in Path(output_root).rglob("model_call_receipt.json"):
        receipt = _read_json(path)
        if not receipt or str(receipt.get("status") or "") != "failed":
            continue
        try:
            mtime = path.stat().st_mtime
        except OSError:
            mtime = 0.0
        rows.append((mtime, path, receipt))
    rows.sort(key=lambda item: item[0])
    return rows


def _stage_for_call_dir(path: Path) -> str:
    name = path.parent.name
    if name in STAGE_BY_CALL_DIR:
        return STAGE_BY_CALL_DIR[name]
    grand = path.parent.parent.name
    return STAGE_BY_CALL_DIR.get(grand, name or "unknown")


def _first_error(payload: dict[str, Any]) -> dict[str, Any] | None:
    errors = payload.get("errors")
    if isinstance(errors, list):
        for item in errors:
            if isinstance(item, dict) and str(item.get("code") or "").strip():
                return item
    checks = payload.get("checks")
    if isinstance(checks, dict):
        for rows in checks.values():
            if not isinstance(rows, list):
                continue
            for item in rows:
                if isinstance(item, dict) and str(item.get("code") or "").strip():
                    return item
    return None


def _node_from_error(error: dict[str, Any]) -> str | None:
    for key in ("node_id", "node"):
        value = error.get(key)
        if value:
            return str(value)
    path = str(error.get("path") or "")
    named = path.removeprefix("plan_ir.")
    if named.startswith("nodes["):
        value = named.partition("[")[2].partition("]")[0]
        if value and not value.isdigit():
            return value
    if named.startswith("nodes."):
        parts = named.split(".")
        if len(parts) > 1 and not parts[1].isdigit():
            return parts[1]
    return None


def summarize_planner_failure(output_root: Path) -> dict[str, Any] | None:
    output_root = Path(output_root)
    if not output_root.exists():
        return None
    semantic = output_root / "semantic"
    execution = output_root / "execution"

    candidates: list[tuple[float, dict[str, Any]]] = []
    receipts = _failed_receipts(output_root)
    if receipts:
        receipt_mtime, path, receipt = receipts[-1]
        error = receipt.get("error") if isinstance(receipt.get("error"), dict) else {}
        code = str(error.get("code") or "provider_error")
        try:
            rel = str(path.relative_to(output_root))
        except ValueError:
            rel = str(path)
        candidates.append(
            (
                receipt_mtime,
                make_failure(
                    stage=_stage_for_call_dir(path),
                    code=code,
                    detail=str(error.get("detail") or ""),
                    receipt_ref=rel,
                ),
            )
        )

    for directory, table in (
        (execution, _EXECUTION_REJECTIONS),
        (semantic, _SEMANTIC_REJECTIONS),
    ):
        acceptance = _read_json(directory / "plan_acceptance.json")
        if not acceptance:
            continue
        decision = str(acceptance.get("decision") or "")
        if decision in {"accepted", "direct_response"}:
            continue
        for filename, stage in table:
            payload = _read_json(directory / filename)
            if not payload:
                continue
            error = _first_error(payload)
            status = str(payload.get("status") or payload.get("verdict") or "")
            if error is None and status not in {"fail", "failed", "rejected"}:
                continue
            code = str((error or {}).get("code") or f"{stage}_rejected")
            evidence_path = directory / filename
            try:
                evidence_mtime = max(evidence_path.stat().st_mtime, (directory / "plan_acceptance.json").stat().st_mtime)
            except OSError:
                evidence_mtime = 0.0
            candidates.append(
                (
                    evidence_mtime,
                    make_failure(
                        stage=stage,
                        code=code,
                        detail=str(
                            (error or {}).get("message")
                            or "; ".join(str(row) for row in acceptance.get("reasons") or [])
                        ),
                        node_id=_node_from_error(error or {}),
                        receipt_ref=str(evidence_path.relative_to(output_root)),
                        retry_safe=False,
                    ),
                )
            )
            break
        else:
            acceptance_path = directory / "plan_acceptance.json"
            try:
                acceptance_mtime = acceptance_path.stat().st_mtime
            except OSError:
                acceptance_mtime = 0.0
            candidates.append(
                (
                    acceptance_mtime,
                    make_failure(
                        stage="semantic_acceptance" if directory == semantic else "execution_acceptance",
                        code=decision or "failed",
                        detail="; ".join(str(row) for row in acceptance.get("reasons") or []),
                        receipt_ref=str(acceptance_path.relative_to(output_root)),
                        retry_safe=False,
                    ),
                )
            )
    return max(candidates, key=lambda item: item[0])[1] if candidates else None


def write_planner_failure(output_root: Path, failure: dict[str, Any]) -> Path:
    path = failure_path(output_root)
    _atomic_json(path, failure)
    return path


def read_planner_failure(output_root: Path) -> dict[str, Any] | None:
    payload = _read_json(failure_path(output_root))
    if not payload or payload.get("schema_version") != FAILURE_SCHEMA:
        return None
    return payload


def ensure_planner_failure(
    output_root: Path,
    *,
    fallback_stage: str,
    fallback_code: str,
    fallback_detail: str = "",
) -> dict[str, Any]:
    derived = summarize_planner_failure(output_root)
    if derived is None:
        existing = read_planner_failure(output_root)
        if existing:
            return existing
        derived = make_failure(stage=fallback_stage, code=fallback_code, detail=fallback_detail)
    write_planner_failure(output_root, derived)
    return derived
