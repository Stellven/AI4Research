"""Shared execution contract for bounded scientific evidence operators."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

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


SUCCESS = "success"
PRODUCT_FAILURE = "product_failure"
PROVIDER_ENVIRONMENT_FAILURE = "provider_environment_failure"


@dataclass(frozen=True)
class OperatorSpec:
    """Package-local, resolver-friendly physical operator declaration."""

    node_id: str
    operator_id: str
    version: str
    output_schema: str
    output_filename: str
    handler: Callable[[OperatorContext, "OperatorSpec"], dict[str, Any]]

    @property
    def entrypoint(self) -> str:
        return (
            "harness.plugins.autosci.operators.scientific_lifecycle.evidence.registry:"
            f"execute_{self.node_id}"
        )


def require_request_identity(context: OperatorContext, expected_node_id: str) -> None:
    for field in ("task_id", "run_id", "workflow_id", "node_id"):
        if not str(context.node_request.get(field) or "").strip():
            raise ResearchOperatorError(f"Missing required request identity: {field}", error_type="invalid_input")
    actual = str(context.node_request["node_id"])
    if actual != expected_node_id:
        raise ResearchOperatorError(
            f"Operator expected node_id={expected_node_id}, got {actual}",
            error_type="wrong_node_identity",
        )


def output_target(context: OperatorContext, filename: str) -> Path:
    if not context.write_scope:
        raise ResearchOperatorError("No write scope declared", error_type="scope_violation")
    raw = context.write_scope[0]
    candidate = Path(raw)
    path_text = raw if candidate.suffix.lower() == ".json" else f"{raw.rstrip('/\\')}/{filename}"
    return validate_scoped_path(path_text, context.write_scope, workspace_root=context.workspace_root)


def load_evidence_inputs(
    context: OperatorContext,
    *schemas: str,
    payload_keys: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    """Load all matching typed inputs, validating scope, content hash and task identity."""

    loaded: list[dict[str, Any]] = []
    allowed = set(schemas)
    for ref in context.input_artifact_refs():
        if str(ref.get("schema") or "") not in allowed:
            continue
        path = validate_scoped_path(
            str(ref.get("path") or ""),
            context.read_scope,
            workspace_root=context.workspace_root,
            must_exist=True,
        )
        body = path.read_bytes()
        actual_hash = sha256_bytes(body)
        expected_hash = str(ref.get("sha256") or "")
        if expected_hash and expected_hash.lower() != actual_hash:
            raise ResearchOperatorError(
                f"Input artifact hash does not match reference: {ref.get('path')}",
                error_type="artifact_hash_mismatch",
            )
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ResearchOperatorError(
                f"Input artifact is not valid JSON: {ref.get('path')}",
                error_type="invalid_input",
            ) from exc
        if not isinstance(payload, dict) or str(payload.get("schema") or "") not in allowed:
            raise ResearchOperatorError(
                f"Input artifact has unexpected schema: {ref.get('path')}",
                error_type="artifact_identity_mismatch",
            )
        request_task = str(context.node_request.get("task_id") or "")
        if payload.get("task_id") and str(payload["task_id"]) != request_task:
            raise ResearchOperatorError("Input artifact task_id mismatch", error_type="artifact_identity_mismatch")
        loaded.append(payload)
    for key in payload_keys:
        value = context.payload.get(key)
        if isinstance(value, dict) and str(value.get("schema") or "") in allowed:
            loaded.append(value)
    return loaded


def input_fingerprint(context: OperatorContext, spec: OperatorSpec) -> str:
    refs: list[dict[str, str]] = []
    for ref in context.input_artifact_refs():
        item = {
            "artifact_id": str(ref.get("artifact_id") or ""),
            "path": str(ref.get("path") or ""),
            "schema": str(ref.get("schema") or ""),
            "sha256": str(ref.get("sha256") or ""),
        }
        if item["path"]:
            path = validate_scoped_path(
                item["path"], context.read_scope, workspace_root=context.workspace_root, must_exist=True
            )
            item["sha256"] = sha256_bytes(path.read_bytes())
        refs.append(item)
    direct_paths: list[dict[str, str]] = []
    for key in ("source", "paper_path", "material_path", "repo_path", "code_path", "wiki_root"):
        raw = context.payload.get(key)
        if not isinstance(raw, str) or not raw.strip() or raw.lower().startswith(("http://", "https://")):
            continue
        path = validate_scoped_path(raw, context.read_scope, workspace_root=context.workspace_root, must_exist=True)
        if path.is_file():
            direct_paths.append({"field": key, "path": display_path(path, context.workspace_root), "sha256": sha256_bytes(path.read_bytes())})
        else:
            members = []
            for member in sorted(item for item in path.rglob("*") if item.is_file())[:1000]:
                members.append({"path": display_path(member, context.workspace_root), "sha256": sha256_bytes(member.read_bytes())})
            direct_paths.append({"field": key, "path": display_path(path, context.workspace_root), "sha256": stable_json_sha256(members)})
    material = {
        "operator_id": spec.operator_id,
        "operator_version": spec.version,
        "task_id": context.node_request.get("task_id"),
        "run_id": context.node_request.get("run_id"),
        "workflow_id": context.node_request.get("workflow_id"),
        "node_id": context.node_request.get("node_id"),
        "payload": redact_secrets(context.payload, context.secret_refs, context.secret_values),
        "input_artifacts": refs,
        "direct_path_hashes": direct_paths,
    }
    return stable_json_sha256(material)


def envelope(context: OperatorContext) -> dict[str, Any]:
    return {
        "task_id": str(context.node_request["task_id"]),
        "sprint_id": str(context.node_request.get("sprint_id") or context.node_request["run_id"]),
        "node_id": str(context.node_request["node_id"]),
        "inputs": redact_secrets(context.payload, context.secret_refs, context.secret_values),
    }


def enrich_evidence(
    payload: dict[str, Any],
    *,
    context: OperatorContext,
    spec: OperatorSpec,
    input_hash: str,
    outcome_class: str,
) -> dict[str, Any]:
    payload = redact_secrets(payload, context.secret_refs, context.secret_values)
    provenance = payload.setdefault("provenance", {})
    provenance.update(
        {
            "artifact_id": f"evidence.{spec.node_id}",
            "operator_id": spec.operator_id,
            "operator_version": spec.version,
            "implementation_package": "plugins/autosci/operators/scientific_lifecycle/evidence",
            "task_id": str(context.node_request["task_id"]),
            "run_id": str(context.node_request["run_id"]),
            "workflow_id": str(context.node_request["workflow_id"]),
            "node_id": str(context.node_request["node_id"]),
            "input_sha256": input_hash,
            "output_sha256": stable_json_sha256(payload.get("outputs") or {}),
            "outcome_class": outcome_class,
        }
    )
    return payload


def _existing_success(target: Path, spec: OperatorSpec, input_hash: str) -> dict[str, Any] | None:
    if not target.is_file():
        return None
    try:
        existing = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    provenance = existing.get("provenance") if isinstance(existing, dict) else None
    if not isinstance(provenance, dict):
        return None
    if (
        existing.get("status") == "completed"
        and provenance.get("operator_id") == spec.operator_id
        and provenance.get("operator_version") == spec.version
        and provenance.get("input_sha256") == input_hash
    ):
        return existing
    return None


def write_evidence(context: OperatorContext, target: Path, payload: dict[str, Any]) -> tuple[dict[str, str], str]:
    target.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    target.write_text(body, encoding="utf-8")
    digest = sha256_bytes(target.read_bytes())
    return (
        {
            "artifact_id": f"evidence.{context.node_request['node_id']}",
            "path": display_path(target, context.workspace_root),
            "schema": str(payload["schema"]),
            "sha256": digest,
        },
        digest,
    )


def execute_spec(
    spec: OperatorSpec,
    node_request: dict[str, Any],
    *,
    services: dict[str, Any] | None = None,
    workspace_root: Path | None = None,
) -> dict[str, Any]:
    context = OperatorContext.from_request(node_request, services=services, workspace_root=workspace_root or Path.cwd())
    input_hash = ""
    try:
        require_request_identity(context, spec.node_id)
        if not context.secret_verification_complete:
            raise ResearchOperatorError(
                "Authorized secret refs require matching in-memory secret_values",
                error_type="secret_verification_unavailable",
            )
        target = output_target(context, spec.output_filename)
        input_hash = input_fingerprint(context, spec)
        existing = _existing_success(target, spec, input_hash)
        if existing is not None:
            artifact, output_hash = write_evidence(context, target, existing)
            return build_node_result(
                context,
                status="completed",
                output_artifacts=[artifact],
                evidence=[evidence_ref(f"ev.{spec.node_id}", spec.output_schema, "Reused idempotent evidence output.", artifact["artifact_id"])],
                hashes=[
                    {"hash_id": artifact["artifact_id"], "algorithm": "sha256", "value": output_hash},
                ],
                limitations=["Idempotent replay reused the existing output because operator identity, version and input hash matched."],
            )
        raw = spec.handler(context, spec)
        typed = raw["evidence"]
        outcome_class = str(raw.get("outcome_class") or SUCCESS)
        typed = enrich_evidence(
            typed,
            context=context,
            spec=spec,
            input_hash=input_hash,
            outcome_class=outcome_class,
        )
        artifact, output_hash = write_evidence(context, target, typed)
        hashes = [{"hash_id": artifact["artifact_id"], "algorithm": "sha256", "value": output_hash}]
        evidence = [evidence_ref(f"ev.{spec.node_id}", spec.output_schema, str(raw["summary"]), artifact["artifact_id"])]
        limitations = list(typed.get("limitations") or [])
        if outcome_class == SUCCESS and typed.get("status") == "completed":
            return build_node_result(
                context,
                status="completed",
                output_artifacts=[artifact],
                evidence=evidence,
                hashes=hashes,
                model_provider_usage=list(raw.get("provider_usage") or []),
                limitations=limitations,
            )
        error = {
            "error_id": f"operator.{spec.node_id}.{outcome_class}",
            "error_type": outcome_class,
            "message": str(raw.get("error") or limitations[0] if limitations else outcome_class)[:500],
        }
        return build_node_result(
            context,
            status="awaiting_external" if outcome_class == PROVIDER_ENVIRONMENT_FAILURE else "failed",
            output_artifacts=[artifact],
            evidence=evidence,
            hashes=hashes,
            model_provider_usage=list(raw.get("provider_usage") or []),
            errors=[error],
            limitations=limitations,
        )
    except ResearchOperatorError as exc:
        return build_node_result(
            context,
            status="failed",
            hashes=[],
            errors=[{
                "error_id": f"operator.{spec.node_id}.product_failure",
                "error_type": PRODUCT_FAILURE,
                "message": f"{exc.error_type}: {str(exc)}"[:500],
            }],
            limitations=["The operator stopped before producing accepted evidence."],
        )


def evidence_document(
    context: OperatorContext,
    spec: OperatorSpec,
    outputs: dict[str, Any],
    *,
    status: str = "completed",
    limitations: list[str] | None = None,
    artifacts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "schema": spec.output_schema,
        "task_id": str(context.node_request["task_id"]),
        "sprint_id": str(context.node_request.get("sprint_id") or context.node_request["run_id"]),
        "node_id": spec.node_id,
        "status": status,
        "inputs": redact_secrets(context.payload, context.secret_refs, context.secret_values),
        "outputs": outputs,
        "artifacts": list(artifacts or []),
        "provenance": {
            "artifact_id": f"evidence.{spec.node_id}",
            "operator_id": spec.operator_id,
            "implementation_package": "plugins/autosci/operators/scientific_lifecycle/evidence",
            "task_id": str(context.node_request["task_id"]),
            "run_id": str(context.node_request["run_id"]),
            "workflow_id": str(context.node_request["workflow_id"]),
            "node_id": str(context.node_request["node_id"]),
            "timestamp": str(context.node_request.get("issued_at") or utc_now()),
        },
        "limitations": list(limitations or []),
    }
