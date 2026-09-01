"""Shared contracts for bounded scientific lifecycle action operators."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from ...research_synthesis.base import (
    OperatorContext,
    ResearchOperatorError,
    build_node_result,
    display_path,
    evidence_ref,
    redact_secrets,
    sha256_bytes,
    stable_json_sha256,
    utc_now,
    validate_scoped_path,
)


OPERATOR_VERSION = "1.1.0"
IMPLEMENTATION_PACKAGE = "plugins/autosci/operators/scientific_lifecycle/action"


def require_text(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ResearchOperatorError(f"{field} must be non-empty", error_type="invalid_input")
    return text


def require_list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list) or not value:
        raise ResearchOperatorError(f"{field} must be a non-empty list", error_type="invalid_input")
    return value


def request_input_hash(context: OperatorContext) -> str:
    authorization = context.node_request.get("authorization") or {}
    safe_authorization = {
        "scope_id": authorization.get("scope_id"),
        "approved_capabilities": authorization.get("approved_capabilities") or [],
        "approval_ref": authorization.get("approval_ref"),
        "allow_network": bool(authorization.get("allow_network", False)),
        "allow_live_provider": bool(authorization.get("allow_live_provider", False)),
    }
    return stable_json_sha256({
        "task_id": context.node_request.get("task_id"),
        "run_id": context.node_request.get("run_id"),
        "workflow_id": context.node_request.get("workflow_id"),
        "node_id": context.node_request.get("node_id"),
        "payload": redact_secrets(context.payload, context.secret_refs, context.secret_values),
        "input_artifacts": [
            {
                "artifact_id": item.get("artifact_id"),
                "schema": item.get("schema"),
                "sha256": item.get("sha256"),
            }
            for item in context.input_artifact_refs()
        ],
        "authorization": safe_authorization,
        "read_scope": context.read_scope,
        "write_scope": context.write_scope,
    })


def evidence_timestamp(context: OperatorContext) -> str:
    # A caller-supplied timestamp makes retry output byte-for-byte reproducible.
    # Otherwise the evidence truthfully records this execution time.
    return str(context.payload.get("evidence_timestamp") or utc_now())


def run_provenance(context: OperatorContext) -> dict[str, Any]:
    task_contract = context.payload.get("task_contract")
    value = task_contract.get("run_provenance") if isinstance(task_contract, dict) else None
    if not isinstance(value, dict):
        return {}
    return redact_secrets(value, context.secret_refs, context.secret_values)


def output_location(context: OperatorContext, filename: str, *, scope_index: int = 0) -> str:
    if len(context.write_scope) <= scope_index:
        raise ResearchOperatorError("No write scope declared for output", error_type="scope_violation")
    scope = context.write_scope[scope_index].replace("\\", "/").rstrip("/")
    if Path(scope).suffix:
        return scope
    return f"{scope}/{filename}"


def load_documents(
    context: OperatorContext,
    *,
    schemas: Iterable[str] = (),
    payload_keys: Iterable[str] = (),
    required: bool = True,
) -> list[dict[str, Any]]:
    """Load hash-verified ABI evidence, falling back to explicit inline payloads."""

    wanted = set(schemas)
    documents: list[dict[str, Any]] = []
    for ref in context.input_artifact_refs():
        if wanted and str(ref.get("schema") or "") not in wanted:
            continue
        if not str(ref.get("sha256") or ""):
            raise ResearchOperatorError(
                f"Input artifact requires sha256: {ref.get('path')}",
                error_type="missing_artifact_hash",
            )
        document = context.load_json_artifact(ref)
        schema = str(document.get("schema") or "")
        if wanted and schema not in wanted:
            raise ResearchOperatorError(
                f"Input artifact schema mismatch: {schema or '<missing>'}",
                error_type="artifact_identity_mismatch",
            )
        task_id = str(document.get("task_id") or "")
        if task_id and task_id != str(context.node_request.get("task_id") or ""):
            raise ResearchOperatorError("Input artifact task_id mismatch", error_type="artifact_identity_mismatch")
        documents.append(document)
    if documents:
        return documents
    if context.input_artifact_refs():
        if required:
            names = ", ".join(schemas) or ", ".join(payload_keys)
            raise ResearchOperatorError(
                f"Referenced evidence does not include a required schema: {names}",
                error_type="artifact_identity_mismatch",
            )
        return []
    for key in payload_keys:
        value = context.payload.get(key)
        if isinstance(value, dict):
            documents.append(value)
        elif isinstance(value, list):
            documents.extend(item for item in value if isinstance(item, dict))
    if required and not documents:
        names = ", ".join(payload_keys) or ", ".join(schemas)
        raise ResearchOperatorError(f"Required input evidence is missing: {names}", error_type="missing_input")
    return documents


def write_evidence_artifact(
    context: OperatorContext,
    *,
    operator_id: str,
    schema: str,
    outputs: dict[str, Any],
    filename: str,
    artifact_id: str | None = None,
    status: str = "completed",
    limitations: list[str] | None = None,
    scope_index: int = 0,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, str]]:
    if status not in {"completed", "failed", "inconclusive"}:
        raise ResearchOperatorError(f"Unsupported evidence status: {status}", error_type="invalid_status")
    input_hash = request_input_hash(context)
    clean_outputs = redact_secrets(outputs, context.secret_refs, context.secret_values)
    output_hash = stable_json_sha256(clean_outputs)
    final_artifact_id = artifact_id or schema.removesuffix(".v1")
    linked_artifacts: list[dict[str, str]] = []
    for index, item in enumerate(context.payload.get("source_artifacts") or []):
        if not isinstance(item, dict):
            raise ResearchOperatorError(
                f"source_artifacts[{index}] must be an object",
                error_type="invalid_input",
            )
        raw_path = str(item.get("path") or "").strip()
        expected_digest = str(item.get("sha256") or "").strip().lower()
        if not raw_path or not expected_digest:
            raise ResearchOperatorError(
                f"source_artifacts[{index}] requires path and sha256",
                error_type="missing_artifact_hash",
            )
        source_path = validate_scoped_path(
            raw_path,
            context.read_scope,
            workspace_root=context.workspace_root,
            must_exist=True,
            # Scheduler-owned controller inputs (for example RequirementIR)
            # are exact, hash-bound file routes beside the runtime workspace.
            # Permit only an exact declared external file here; ordinary reads
            # and every write remain confined to the workspace root.
            allow_external_exact=True,
        )
        actual_digest = sha256_bytes(source_path.read_bytes())
        if actual_digest != expected_digest:
            raise ResearchOperatorError(
                f"source_artifacts[{index}] hash mismatch",
                error_type="artifact_hash_mismatch",
            )
        linked_artifacts.append(
            {
                "type": "input_evidence",
                "path": display_path(source_path, context.workspace_root),
                "sha256": actual_digest,
            }
        )

    payload = {
        "schema": schema,
        "task_id": str(context.node_request.get("task_id") or ""),
        "sprint_id": str(context.node_request.get("run_id") or ""),
        "node_id": context.output_node_id,
        "status": status,
        "inputs": {
            "request_sha256": input_hash,
            "artifact_sha256": [str(item.get("sha256")) for item in context.input_artifact_refs()],
        },
        "outputs": clean_outputs,
        "artifacts": linked_artifacts,
        "provenance": {
            "artifact_id": final_artifact_id,
            "operator_id": operator_id,
            "operator_version": OPERATOR_VERSION,
            "implementation_package": IMPLEMENTATION_PACKAGE,
            "task_id": str(context.node_request.get("task_id") or ""),
            "run_id": str(context.node_request.get("run_id") or ""),
            "workflow_id": str(context.node_request.get("workflow_id") or ""),
            "node_id": context.output_node_id,
            "timestamp": evidence_timestamp(context),
            "input_sha256": input_hash,
            "output_sha256": output_hash,
            "run_provenance": run_provenance(context),
        },
        "limitations": [str(item) for item in limitations or [] if str(item).strip()],
    }
    target = validate_scoped_path(
        output_location(context, filename, scope_index=scope_index),
        context.write_scope,
        workspace_root=context.workspace_root,
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    target.write_text(body, encoding="utf-8")
    digest = sha256_bytes(target.read_bytes())
    ref = {
        "artifact_id": final_artifact_id,
        "path": display_path(target, context.workspace_root),
        "schema": schema,
        "sha256": digest,
    }
    hashes = [{"hash_id": final_artifact_id, "algorithm": "sha256", "value": digest}]
    ev = evidence_ref(
        f"{operator_id}.execution",
        "physical_operator_execution",
        f"{operator_id}@{OPERATOR_VERSION} produced hash-verified {schema} evidence.",
        final_artifact_id,
    )
    return ref, ev, hashes


def completed_result(
    context: OperatorContext,
    *,
    operator_id: str,
    schema: str,
    outputs: dict[str, Any],
    filename: str,
    artifact_id: str | None = None,
    limitations: list[str] | None = None,
    extra_artifacts: list[dict[str, Any]] | None = None,
    extra_hashes: list[dict[str, str]] | None = None,
    model_provider_usage: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    artifact, ev, hashes = write_evidence_artifact(
        context,
        operator_id=operator_id,
        schema=schema,
        outputs=outputs,
        filename=filename,
        artifact_id=artifact_id,
        limitations=limitations,
    )
    extras = list(extra_artifacts or [])
    evidence = [ev]
    evidence.extend(
        evidence_ref(
            f"{operator_id}.artifact.{index}",
            "physical_operator_artifact",
            f"{operator_id}@{OPERATOR_VERSION} produced an additional hash-verified artifact.",
            str(item["artifact_id"]),
        )
        for index, item in enumerate(extras, start=1)
        if isinstance(item, dict) and item.get("artifact_id")
    )
    return build_node_result(
        context,
        status="completed",
        output_artifacts=[artifact, *extras],
        evidence=evidence,
        hashes=[*hashes, *(extra_hashes or [])],
        model_provider_usage=model_provider_usage,
        limitations=limitations,
    )


def write_scoped_text(
    context: OperatorContext,
    *,
    relative_path: str,
    content: str,
    artifact_id: str,
    schema: str,
) -> tuple[dict[str, Any], dict[str, str]]:
    clean = str(redact_secrets(content, context.secret_refs, context.secret_values))
    if not clean.strip():
        raise ResearchOperatorError("Compiled artifact content is empty", error_type="product_failure")
    target = validate_scoped_path(relative_path, context.write_scope, workspace_root=context.workspace_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(clean, encoding="utf-8")
    digest = sha256_bytes(target.read_bytes())
    return (
        {
            "artifact_id": artifact_id,
            "path": display_path(target, context.workspace_root),
            "schema": schema,
            "sha256": digest,
        },
        {"hash_id": artifact_id, "algorithm": "sha256", "value": digest},
    )


def authorization(context: OperatorContext) -> dict[str, Any]:
    value = context.node_request.get("authorization")
    return value if isinstance(value, dict) else {}


def service_failure(name: str, exc: Exception) -> ResearchOperatorError:
    if isinstance(exc, (TimeoutError, ConnectionError, OSError)):
        category = "provider_environment_failure"
    else:
        category = "provider_contract_failure"
    return ResearchOperatorError(f"{name} failed: {str(exc)[:300]}", error_type=category)
