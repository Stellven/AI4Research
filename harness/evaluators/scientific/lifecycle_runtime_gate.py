#!/usr/bin/env python3
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evaluators.scientific.common import (
    ARTIFACT_HARNESS_DIR,
    HARNESS_DIR,
    GateResult,
    load_json,
    run_cli,
    validate_schema,
)

SCHEMA = "scientific_lifecycle.v1"
BLACK_BOX_OPERATORS = {"AutoSciRunner", "BackendFullWorkflowRunner"}
BRIDGE_LIFECYCLE_ACTIONS = {"run_research_lifecycle", "project_research_lifecycle_state"}


def evaluate(payload: dict[str, Any], path: str | Path | None = None) -> GateResult:
    reasons: list[str] = []
    warnings: list[str] = []
    if payload.get("schema") != SCHEMA:
        reasons.append(f"schema must be {SCHEMA}")
        return _finish(reasons, warnings, path)
    if "artifact_contract" in payload:
        reasons.append("lifecycle_runtime_gate requires runtime summary evidence, not a workflow contract")

    job_id = str(payload.get("job_id") or payload.get("sprint_id") or "").strip()
    if not job_id:
        reasons.append("job_id is required for runtime lifecycle acceptance")

    required_nodes = _required_nodes(payload)
    if not required_nodes:
        reasons.append("required_nodes or nodes must list required runtime nodes")

    node_results = payload.get("node_results")
    gate_results = payload.get("gate_results")
    blocked_nodes = payload.get("blocked_nodes")
    if not isinstance(node_results, dict) or not node_results:
        reasons.append("node_results must be a non-empty map")
        node_results = {}
    if not isinstance(gate_results, dict) or not gate_results:
        reasons.append("gate_results must be a non-empty map")
        gate_results = {}
    if blocked_nodes is not None and not isinstance(blocked_nodes, dict):
        reasons.append("blocked_nodes must be a map when present")
        blocked_nodes = {}
    blocked_nodes = blocked_nodes if isinstance(blocked_nodes, dict) else {}

    _reject_black_box_runtime(payload, reasons)

    for node_id in required_nodes:
        result = node_results.get(node_id)
        if not isinstance(result, dict):
            blocked = blocked_nodes.get(node_id)
            if isinstance(blocked, dict):
                _validate_blocked_node(node_id, blocked, job_id=job_id, reasons=reasons)
            else:
                reasons.append(f"node_results.{node_id} is required")
            continue
        _validate_node_result(
            node_id,
            result,
            gate_results,
            job_id=job_id,
            input_path=Path(path) if path else None,
            reasons=reasons,
            warnings=warnings,
        )

    lifecycle_status = str(payload.get("lifecycle_status") or payload.get("status") or "").lower()
    if lifecycle_status and lifecycle_status not in {"passed", "failed", "inconclusive", "blocked"}:
        reasons.append("lifecycle_status must be passed, failed, inconclusive, or blocked")
    if lifecycle_status in {"failed", "inconclusive"} and not reasons:
        return GateResult(
            ok=False,
            status=lifecycle_status,
            reasons=[],
            warnings=warnings,
            schema=SCHEMA,
            path=str(path) if path else None,
            evidence_status=lifecycle_status,
        )
    if lifecycle_status == "blocked" and not reasons:
        return GateResult(
            ok=False,
            status="inconclusive",
            reasons=[],
            warnings=[*warnings, "lifecycle is blocked waiting for external evidence"],
            schema=SCHEMA,
            path=str(path) if path else None,
            evidence_status="blocked",
        )
    return _finish(reasons, warnings, path)


def _required_nodes(payload: dict[str, Any]) -> list[str]:
    explicit = payload.get("required_nodes")
    if isinstance(explicit, list):
        return [str(item) for item in explicit if str(item).strip()]
    nodes = payload.get("nodes")
    if isinstance(nodes, list):
        return [
            str(node.get("id") or "")
            for node in nodes
            if isinstance(node, dict) and str(node.get("id") or "").strip()
        ]
    return []


def _reject_black_box_runtime(payload: dict[str, Any], reasons: list[str]) -> None:
    owner = str(payload.get("execution_owner") or payload.get("runtime_owner") or "")
    if "autosci_bridge" in owner and "lifecycle" in owner:
        reasons.append("runtime lifecycle acceptance cannot be owned by autosci_bridge lifecycle projection")
    nodes = payload.get("nodes")
    if isinstance(nodes, list):
        for node in nodes:
            if not isinstance(node, dict):
                continue
            node_id = str(node.get("id") or "node")
            logical_operator = str(node.get("logical_operator") or "")
            if logical_operator in BLACK_BOX_OPERATORS:
                reasons.append(f"{node_id} must not use black-box workflow runner {logical_operator}")
    node_results = payload.get("node_results")
    if isinstance(node_results, dict):
        for node_id, result in node_results.items():
            if not isinstance(result, dict):
                continue
            action = str(result.get("action") or result.get("backend_action") or "")
            if action in BRIDGE_LIFECYCLE_ACTIONS:
                reasons.append(f"node_results.{node_id}.action must not be bridge-owned lifecycle action {action}")


def _validate_node_result(
    node_id: str,
    result: dict[str, Any],
    gate_results: dict[str, Any],
    *,
    job_id: str,
    input_path: Path | None,
    reasons: list[str],
    warnings: list[str],
) -> None:
    if str(result.get("status") or "").lower() != "passed":
        reasons.append(f"node_results.{node_id}.status must be passed")
    if result.get("node_id") and str(result.get("node_id")) != node_id:
        reasons.append(f"node_results.{node_id}.node_id must match {node_id}")
    if job_id and result.get("job_id") and str(result.get("job_id")) != job_id:
        reasons.append(f"node_results.{node_id}.job_id must match {job_id}")
    if not str(result.get("gate") or "").strip():
        reasons.append(f"node_results.{node_id}.gate is required")
    _require_existing_file_field(
        result,
        "operator_result_path",
        node_id=node_id,
        input_path=input_path,
        reasons=reasons,
    )
    _require_existing_file_field(
        result,
        "bridge_result_path",
        node_id=node_id,
        input_path=input_path,
        reasons=reasons,
    )

    artifact_raw = str(result.get("evidence_path") or result.get("artifact_path") or result.get("artifact") or "").strip()
    if not artifact_raw:
        reasons.append(f"node_results.{node_id}.artifact_path is required")
        return
    artifact_path = _resolve_path(artifact_raw, input_path)
    if artifact_path is None:
        reasons.append(f"node_results.{node_id}.artifact_path does not exist: {artifact_raw}")
        return

    expected_hash = str(result.get("artifact_sha256") or result.get("sha256") or "").strip().lower()
    if not expected_hash:
        reasons.append(f"node_results.{node_id}.artifact_sha256 is required")
    else:
        actual_hash = _sha256(artifact_path)
        if actual_hash != expected_hash:
            reasons.append(f"node_results.{node_id}.artifact_sha256 mismatch")

    try:
        evidence = load_json(artifact_path)
    except Exception as exc:  # noqa: BLE001 - gate reason should preserve parse/read failures.
        reasons.append(f"node_results.{node_id}.artifact_path is not valid JSON: {exc}")
        return

    expected_schema = str(result.get("expected_schema") or evidence.get("schema") or "").strip()
    if not expected_schema:
        reasons.append(f"node_results.{node_id}.expected_schema is required")
    elif evidence.get("schema") != expected_schema:
        reasons.append(f"node_results.{node_id}.expected_schema mismatch: artifact has {evidence.get('schema')}")
    if expected_schema:
        schema_reasons, schema_warnings = validate_schema(evidence, expected_schema)
        reasons.extend(f"node_results.{node_id}.artifact:{reason}" for reason in schema_reasons)
        warnings.extend(f"node_results.{node_id}.artifact:{warning}" for warning in schema_warnings)

    if str(evidence.get("status") or "") != "completed":
        reasons.append(f"node_results.{node_id}.artifact status must be completed")
    if job_id and str(evidence.get("sprint_id") or "") != job_id:
        reasons.append(f"node_results.{node_id}.artifact sprint_id must match job_id {job_id}")
    if str(evidence.get("node_id") or "") != node_id:
        reasons.append(f"node_results.{node_id}.artifact node_id must match {node_id}")

    gate = gate_results.get(node_id) or gate_results.get(str(result.get("gate") or ""))
    if not isinstance(gate, dict):
        reasons.append(f"gate_results.{node_id} is required")
        return
    gate_status = str(gate.get("status") or "").lower()
    if gate_status not in {"passed", "ok"} and gate.get("ok") is not True:
        reasons.append(f"gate_results.{node_id}.status must be passed")
    if job_id and gate.get("job_id") and str(gate.get("job_id")) != job_id:
        reasons.append(f"gate_results.{node_id}.job_id must match {job_id}")
    if gate.get("node_id") and str(gate.get("node_id")) != node_id:
            reasons.append(f"gate_results.{node_id}.node_id must match {node_id}")


def _require_existing_file_field(
    result: dict[str, Any],
    field: str,
    *,
    node_id: str,
    input_path: Path | None,
    reasons: list[str],
) -> None:
    raw = str(result.get(field) or "").strip()
    if not raw:
        reasons.append(f"node_results.{node_id}.{field} is required")
        return
    if _resolve_path(raw, input_path) is None:
        reasons.append(f"node_results.{node_id}.{field} does not exist: {raw}")


def _validate_blocked_node(
    node_id: str,
    blocked: dict[str, Any],
    *,
    job_id: str,
    reasons: list[str],
) -> None:
    if str(blocked.get("status") or "").lower() not in {"blocked", "waiting", "wait"}:
        reasons.append(f"blocked_nodes.{node_id}.status must be blocked or waiting")
    if blocked.get("node_id") and str(blocked.get("node_id")) != node_id:
        reasons.append(f"blocked_nodes.{node_id}.node_id must match {node_id}")
    if job_id and blocked.get("job_id") and str(blocked.get("job_id")) != job_id:
        reasons.append(f"blocked_nodes.{node_id}.job_id must match {job_id}")
    if not str(blocked.get("reason") or "").strip():
        reasons.append(f"blocked_nodes.{node_id}.reason is required")
    required = blocked.get("required_evidence")
    if not isinstance(required, list) or not any(str(item).strip() for item in required):
        reasons.append(f"blocked_nodes.{node_id}.required_evidence must be a non-empty list")
    if not str(blocked.get("unblock_condition") or "").strip():
        reasons.append(f"blocked_nodes.{node_id}.unblock_condition is required")


def _resolve_path(raw: str, input_path: Path | None) -> Path | None:
    path = Path(raw).expanduser()
    candidates = [path] if path.is_absolute() else []
    if not path.is_absolute():
        if input_path is not None:
            candidates.append(input_path.resolve().parent / path)
        candidates.extend([ARTIFACT_HARNESS_DIR / path, HARNESS_DIR / path, HARNESS_DIR.parent / path])
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _finish(reasons: list[str], warnings: list[str], path: str | Path | None) -> GateResult:
    status = "failed" if reasons else "passed"
    return GateResult(
        ok=status == "passed",
        status=status,
        reasons=reasons,
        warnings=warnings,
        schema=SCHEMA,
        path=str(path) if path else None,
        evidence_status="completed" if status == "passed" else "failed",
    )


if __name__ == "__main__":
    raise SystemExit(run_cli(evaluate, SCHEMA))
