"""seed_fetch node implementation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import (
    OperatorContext,
    ResearchOperatorError,
    build_node_result,
    evidence_ref,
    no_provider_result,
    output_path,
    require_node,
    sha256_bytes,
    utc_now,
    validate_scoped_path,
    write_artifact,
)


SUPPORTED_LOCAL_KINDS = {"pdf", "markdown"}


def _seed_inputs(payload: dict[str, Any]) -> list[dict[str, Any]]:
    task_contract = payload.get("task_contract") if isinstance(payload.get("task_contract"), dict) else {}
    raw = payload.get("seed_inputs") or task_contract.get("seed_inputs") or payload.get("seeds") or []
    if isinstance(raw, dict):
        return [raw]
    return [item for item in raw if isinstance(item, dict)]


def _snapshot_url(seed: dict[str, Any], context: OperatorContext) -> dict[str, Any] | None:
    fetch_url = context.services.get("fetch_url")
    if fetch_url is None:
        return None
    fetched = fetch_url(str(seed.get("value") or ""), seed=seed)
    if not isinstance(fetched, dict):
        raise ResearchOperatorError("fetch_url service must return a JSON object", error_type="provider_contract")
    content = fetched.get("content", "")
    body = content if isinstance(content, bytes) else str(content).encode("utf-8")
    return {
        "seed_id": str(seed.get("seed_id") or "seed-url"),
        "seed_kind": "url",
        "source": str(seed.get("value") or ""),
        "fetched_at": str(fetched.get("fetched_at") or utc_now()),
        "sha256": sha256_bytes(body),
        "content_type": str(fetched.get("content_type") or "text/plain"),
        "content": content.decode("utf-8", errors="replace") if isinstance(content, bytes) else str(content),
        "limitations": list(fetched.get("limitations") or []),
    }


def _snapshot_local(seed: dict[str, Any], context: OperatorContext) -> dict[str, Any]:
    path = validate_scoped_path(str(seed.get("value") or ""), context.read_scope, workspace_root=context.workspace_root, must_exist=True)
    if not path.is_file():
        raise ResearchOperatorError(f"Local seed is not a file: {seed.get('value')}", error_type="invalid_input")
    data = path.read_bytes()
    kind = str(seed.get("seed_kind") or path.suffix.lstrip(".")).lower()
    text = data.decode("utf-8", errors="replace")
    return {
        "seed_id": str(seed.get("seed_id") or f"seed-{path.stem}"),
        "seed_kind": kind,
        "source": str(seed.get("value") or ""),
        "fetched_at": utc_now(),
        "sha256": sha256_bytes(data),
        "content_type": "application/pdf" if kind == "pdf" else "text/markdown",
        "content": text,
        "limitations": ["PDF content is captured as bounded raw text bytes for this draft operator."] if kind == "pdf" else [],
    }


def _snapshot_inline(seed: dict[str, Any]) -> dict[str, Any]:
    value = str(seed.get("value") or "")
    kind = str(seed.get("seed_kind") or "topic")
    return {
        "seed_id": str(seed.get("seed_id") or f"seed-{kind}"),
        "seed_kind": kind,
        "source": kind,
        "fetched_at": utc_now(),
        "sha256": sha256_bytes(value.encode("utf-8")),
        "content_type": "text/plain",
        "content": value,
        "limitations": ["External evidence seed was imported as context only."] if kind == "external_evidence" else [],
    }


def execute(node_request: dict, context: OperatorContext) -> dict:
    require_node(context, "seed_fetch")
    snapshots: list[dict[str, Any]] = []
    for seed in _seed_inputs(context.payload):
        kind = str(seed.get("seed_kind") or "").lower()
        if kind == "url":
            snapshot = _snapshot_url(seed, context)
            if snapshot is None:
                return no_provider_result(context, "fetch_url")
            snapshots.append(snapshot)
        elif kind in SUPPORTED_LOCAL_KINDS:
            snapshots.append(_snapshot_local(seed, context))
        elif kind in {"topic", "research_brief", "external_evidence"}:
            snapshots.append(_snapshot_inline(seed))
        else:
            raise ResearchOperatorError(f"Unsupported seed_kind: {kind}", error_type="invalid_input")
    if not snapshots:
        raise ResearchOperatorError("seed_fetch requires at least one seed input", error_type="invalid_input")
    artifact_payload = {
        "schema": "research_synthesis.seed_snapshot.v1",
        "node_id": "seed_fetch",
        "created_at": utc_now(),
        "seeds": snapshots,
        "seed_count": len(snapshots),
    }
    artifact, hash_record = write_artifact(
        context,
        output_path(context, "seed_snapshot.json"),
        artifact_payload,
        artifact_id="seed_snapshot",
        schema="research_synthesis.seed_snapshot.v1",
    )
    return build_node_result(
        context,
        status="completed",
        output_artifacts=[artifact],
        evidence=[evidence_ref("seed_fetch.snapshot", "seed_snapshot", "Seed snapshot captured with source hashes.", artifact["artifact_id"])],
        hashes=[hash_record],
        limitations=[item for seed in snapshots for item in seed.get("limitations", [])],
    )
