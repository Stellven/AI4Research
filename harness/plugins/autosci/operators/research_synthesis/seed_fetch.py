"""seed_fetch node implementation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .base import (
    OperatorContext,
    ResearchOperatorError,
    build_node_result,
    evidence_ref,
    no_provider_result,
    output_path,
    _is_file,
    _read_bytes,
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
    snapshot = {
        "seed_id": str(seed.get("seed_id") or "seed-url"),
        "seed_kind": "url",
        "source": str(fetched.get("requested_url") or seed.get("value") or ""),
        "final_url": str(fetched.get("final_url") or seed.get("value") or ""),
        "fetched_at": str(fetched.get("fetched_at") or utc_now()),
        "sha256": sha256_bytes(body),
        "content_sha256": str(fetched.get("content_sha256") or sha256_bytes(body)),
        "raw_sha256": str(fetched.get("response_sha256") or ""),
        "request_sha256": str(fetched.get("request_sha256") or ""),
        "content_type": str(fetched.get("content_type") or "text/plain"),
        "content": content.decode("utf-8", errors="replace") if isinstance(content, bytes) else str(content),
        "title": str(fetched.get("title") or ""),
        "description": str(fetched.get("description") or ""),
        "provider": str(fetched.get("provider") or "bounded_http"),
        "service_id": str(fetched.get("service_id") or ""),
        "service_version": str(fetched.get("service_version") or ""),
        "archive_path": str(fetched.get("archive_path") or ""),
        "metadata_path": str(fetched.get("metadata_path") or ""),
        "response_bytes": int(fetched.get("response_bytes") or len(body)),
        "redirect_count": int(fetched.get("redirect_count") or 0),
        "limitations": list(fetched.get("limitations") or []),
    }
    snapshot["fetch_metadata_sha256"] = str(fetched.get("metadata_sha256") or "")
    snapshot["source_contract"] = _source_contract(snapshot)
    return snapshot


def _snapshot_local(seed: dict[str, Any], context: OperatorContext) -> dict[str, Any]:
    path = validate_scoped_path(str(seed.get("value") or ""), context.read_scope, workspace_root=context.workspace_root, must_exist=True)
    if not _is_file(path):
        raise ResearchOperatorError(f"Local seed is not a file: {seed.get('value')}", error_type="invalid_input")
    data = _read_bytes(path)
    kind = str(seed.get("seed_kind") or path.suffix.lstrip(".")).lower()
    limitations: list[str] = []
    if kind == "pdf":
        extractor = context.services.get("extract_pdf_text")
        if extractor is not None:
            extracted = extractor(path)
            if isinstance(extracted, tuple):
                text, warnings = extracted
            elif isinstance(extracted, dict):
                text = extracted.get("text", "")
                warnings = extracted.get("warnings", [])
            else:
                text, warnings = extracted, []
        else:
            try:
                from harness.plugins.autosci.backends.paper_prepare import _extract_pdf_text
            except ImportError as exc:  # pragma: no cover - installation shape
                raise ResearchOperatorError(
                    "PDF extraction dependency is unavailable; raw PDF bytes were not treated as text.",
                    error_type="pdf_extraction_unavailable",
                ) from exc
            text, warnings = _extract_pdf_text(path)
        text = str(text or "").strip()
        limitations = [str(item) for item in warnings or [] if str(item).strip()]
        if not text:
            raise ResearchOperatorError(
                "PDF extraction produced no usable document text; raw PDF bytes were not treated as text.",
                error_type="pdf_extraction_unavailable",
            )
    else:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ResearchOperatorError("Markdown seed is not valid UTF-8", error_type="invalid_input") from exc
    snapshot = {
        "seed_id": str(seed.get("seed_id") or f"seed-{path.stem}"),
        "seed_kind": kind,
        "source": str(seed.get("value") or ""),
        "fetched_at": utc_now(),
        "sha256": sha256_bytes(data),
        "content_sha256": sha256_bytes(str(text).encode("utf-8")),
        "content_type": "application/pdf" if kind == "pdf" else "text/markdown",
        "content": text,
        "canonical_path": str(path.resolve()),
        "limitations": limitations,
    }
    snapshot["source_contract"] = _source_contract(snapshot)
    return snapshot


def _snapshot_external_evidence(seed: dict[str, Any], context: OperatorContext) -> dict[str, Any]:
    task_contract = context.payload.get("task_contract") if isinstance(context.payload.get("task_contract"), dict) else {}
    if str(task_contract.get("run_mode") or "") not in {"resume", "import_evidence"}:
        raise ResearchOperatorError(
            "external_evidence is accepted only for a validated resume or import_evidence task contract.",
            error_type="unverified_external_evidence",
        )
    declared_ref = seed.get("artifact_ref") if isinstance(seed.get("artifact_ref"), dict) else {}
    provenance = declared_ref.get("provenance") if isinstance(declared_ref.get("provenance"), dict) else {}
    if not declared_ref or not str(provenance.get("source") or "").strip() or not str(provenance.get("captured_at") or "").strip():
        raise ResearchOperatorError(
            "external_evidence requires a provenance-bearing artifact_ref.",
            error_type="unverified_external_evidence",
        )
    matching_ref = next(
        (
            ref for ref in context.input_artifact_refs()
            if str(ref.get("artifact_id") or "") == str(declared_ref.get("artifact_id") or "")
            and str(ref.get("path") or "").replace("\\", "/") == str(declared_ref.get("path") or "").replace("\\", "/")
        ),
        None,
    )
    if matching_ref is None:
        raise ResearchOperatorError(
            "external_evidence artifact_ref is not present in the scoped node inputs.",
            error_type="unverified_external_evidence",
        )
    path = validate_scoped_path(str(matching_ref.get("path") or ""), context.read_scope, workspace_root=context.workspace_root, must_exist=True)
    data = _read_bytes(path)
    expected_hash = str(declared_ref.get("sha256") or matching_ref.get("sha256") or "")
    actual_hash = sha256_bytes(data)
    if expected_hash and expected_hash.lower() != actual_hash:
        raise ResearchOperatorError("external_evidence artifact hash does not match its reference.", error_type="artifact_hash_mismatch")
    try:
        content = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ResearchOperatorError("external_evidence artifact must be a UTF-8 JSON document.", error_type="invalid_input") from exc
    snapshot = {
        "seed_id": str(seed.get("seed_id") or "seed-external-evidence"),
        "seed_kind": "external_evidence",
        "source": str(declared_ref.get("path") or ""),
        "fetched_at": str(provenance.get("captured_at")),
        "sha256": actual_hash,
        "content_type": "application/json",
        "content": content,
        "provenance": provenance,
        "limitations": ["External evidence was imported from a scoped, provenance-bearing artifact; its claims remain subject to validation."],
    }
    snapshot["source_contract"] = _source_contract(snapshot)
    return snapshot


def _snapshot_inline(seed: dict[str, Any]) -> dict[str, Any]:
    value = str(seed.get("value") or "")
    kind = str(seed.get("seed_kind") or "topic")
    snapshot = {
        "seed_id": str(seed.get("seed_id") or f"seed-{kind}"),
        "seed_kind": kind,
        "source": kind,
        "fetched_at": utc_now(),
        "sha256": sha256_bytes(value.encode("utf-8")),
        "content_sha256": sha256_bytes(value.encode("utf-8")),
        "content_type": "text/plain",
        "content": value,
        "limitations": [],
    }
    snapshot["source_contract"] = _source_contract(snapshot)
    return snapshot


def _source_contract(snapshot: dict[str, Any]) -> dict[str, Any]:
    seed_id = str(snapshot.get("seed_id") or "seed")
    content = snapshot.get("content")
    content_text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False, sort_keys=True)
    content_hash = str(snapshot.get("content_sha256") or sha256_bytes(content_text.encode("utf-8")))
    source = str(snapshot.get("source") or snapshot.get("final_url") or snapshot.get("canonical_path") or seed_id)
    provenance = snapshot.get("provenance") if isinstance(snapshot.get("provenance"), dict) else {}
    return {
        "schema": "autosci_seed_source_contract.v1",
        "source_id": seed_id,
        "seed_kind": str(snapshot.get("seed_kind") or "unknown"),
        "source_kind": str(snapshot.get("seed_kind") or "unknown"),
        "source_ref": source,
        "canonical_path": str(snapshot.get("canonical_path") or snapshot.get("final_url") or source),
        "content_sha256": content_hash,
        "raw_file_sha256": str(snapshot.get("sha256") or snapshot.get("raw_sha256") or ""),
        "title": str(snapshot.get("title") or seed_id),
        "content_proof": {
            "content_type": str(snapshot.get("content_type") or ""),
            "content_chars": len(content_text),
            "non_empty": bool(content_text.strip()),
        },
        "provenance": {
            "provider": str(snapshot.get("provider") or provenance.get("provider") or "supplied"),
            "fetched_at": str(snapshot.get("fetched_at") or ""),
            "service_id": str(snapshot.get("service_id") or ""),
            "request_sha256": str(snapshot.get("request_sha256") or ""),
            **provenance,
        },
        "limitations": [str(item) for item in snapshot.get("limitations") or [] if str(item).strip()],
        "evidence_ids": list(dict.fromkeys([seed_id, source, content_hash])),
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
            try:
                snapshots.append(_snapshot_local(seed, context))
            except ResearchOperatorError as exc:
                if exc.error_type != "pdf_extraction_unavailable":
                    raise
                return build_node_result(
                    context,
                    status="blocked",
                    errors=[{"error_id": "seed_fetch.pdf_extraction", "error_type": exc.error_type, "message": str(exc)}],
                    limitations=["A supported PDF extraction surface is required before this seed can be ingested."],
                )
        elif kind == "external_evidence":
            snapshots.append(_snapshot_external_evidence(seed, context))
        elif kind in {"topic", "research_brief"}:
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
