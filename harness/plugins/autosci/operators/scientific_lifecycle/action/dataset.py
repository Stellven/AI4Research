"""Prepare retained public data and executable assets for supported PoCs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...research_synthesis.base import display_path, sha256_bytes, validate_scoped_path
from .common import (
    OperatorContext,
    ResearchOperatorError,
    completed_result,
    load_documents,
)


PREPARER_ID = "autosci-dataset-package-preparation-physical"


def _request_text(context: OperatorContext, documents: list[dict[str, Any]]) -> str:
    task_contract = context.payload.get("task_contract") if isinstance(context.payload.get("task_contract"), dict) else {}
    fragments = [
        str(task_contract.get("user_intent") or ""),
        str(context.payload.get("objective") or ""),
    ]
    for document in documents:
        outputs = document.get("outputs") if isinstance(document.get("outputs"), dict) else document
        for claim in outputs.get("claims") or [] if isinstance(outputs, dict) else []:
            if isinstance(claim, dict):
                fragments.append(str(claim.get("text") or ""))
    return "\n".join(value for value in fragments if value.strip())


def prepare_dataset(node_request: dict[str, Any], context: OperatorContext) -> dict[str, Any]:
    documents = load_documents(
        context,
        schemas=("research_claims.v1",),
        payload_keys=("research_claims", "claims"),
    )
    builder = context.services.get("experiment_package_builder")
    if not callable(builder):
        raise ResearchOperatorError("experiment_package_builder service is unavailable", error_type="environment_unavailable")
    if not context.write_scope:
        raise ResearchOperatorError("Dataset preparation has no declared output scope", error_type="scope_violation")
    raw_scope = str(context.write_scope[0])
    scope = validate_scoped_path(raw_scope, context.write_scope, workspace_root=context.workspace_root)
    if Path(raw_scope).suffix:
        raise ResearchOperatorError(
            "Dataset manifest must be materialized as a directory collection so retained assets share its scope",
            error_type="invalid_input",
        )
    output_dir = scope
    result_scope = str(context.payload.get("experiment_result_scope") or "").strip()
    if not result_scope:
        raise ResearchOperatorError("Frozen downstream experiment result scope is missing", error_type="missing_input")
    result_path = (context.workspace_root / result_scope).resolve()
    authorization = context.node_request.get("authorization") if isinstance(context.node_request.get("authorization"), dict) else {}
    manifest = builder(
        objective=_request_text(context, documents),
        output_dir=output_dir,
        result_path=result_path,
        experiment_id=str(context.payload.get("experiment_id") or "exp-kv-cache-quantization"),
        allow_network=bool(authorization.get("allow_network", False)),
    )
    assets = []
    hashes = []
    for item in manifest.get("assets") or []:
        if not isinstance(item, dict):
            continue
        path = (context.workspace_root / str(item.get("path") or "")).resolve()
        digest = sha256_bytes(path.read_bytes())
        if digest != str(item.get("sha256") or ""):
            raise ResearchOperatorError("Prepared asset hash changed before publication", error_type="artifact_hash_mismatch")
        artifact_id = f"experiment_asset_{str(item.get('role') or 'file')}"
        assets.append(
            {
                "artifact_id": artifact_id,
                "path": display_path(path, context.workspace_root),
                "schema": f"file.{str(item.get('role') or 'binary')}",
                "sha256": digest,
            }
        )
        hashes.append({"hash_id": artifact_id, "algorithm": "sha256", "value": digest})
    return completed_result(
        context,
        operator_id=PREPARER_ID,
        schema="dataset_manifest.v1",
        outputs={"dataset_manifest": manifest},
        filename="dataset_manifest.v1.json",
        artifact_id="dataset_manifest",
        limitations=[str(item) for item in manifest.get("limitations") or [] if str(item).strip()],
        extra_artifacts=assets,
        extra_hashes=hashes,
    )
