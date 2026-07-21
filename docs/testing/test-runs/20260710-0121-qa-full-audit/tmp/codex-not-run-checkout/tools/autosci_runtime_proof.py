#!/usr/bin/env python3
"""Helpers for writing AutoSci parity runtime proof manifests."""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def slug(value: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9_.-]+", "-", str(value or "").strip()).strip("-")
    return text or "proof"


def resolve_output_path(path_text: str) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path
    return Path.cwd() / path


def evidence_ref(path: Path) -> str:
    resolved = path.resolve()
    roots = [os.environ.get("HARNESS_DIR", ""), str(Path.cwd())]
    for raw_root in roots:
        if not raw_root:
            continue
        root = Path(raw_root).resolve()
        try:
            return str(resolved.relative_to(root))
        except ValueError:
            continue
    return str(resolved)


def write_json(path_text: str, payload: dict[str, Any]) -> Path:
    path = resolve_output_path(path_text)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_runtime_proof_manifest(
    *,
    path_text: str,
    native_skill: str,
    categories: list[str],
    collection_mode: str,
    source: str,
    artifact_kind: str,
    command: str,
    evidence_paths: list[Path],
    description: str,
    generated_at: str | None = None,
) -> Path:
    captured_at = generated_at or utc_now()
    clean_skill = slug(native_skill)
    proof_id = f"runtime:{clean_skill}:{slug(source)}:{captured_at.replace(':', '').replace('-', '')}"
    manifest = {
        "schema": "autosci_runtime_proof_manifest.v1",
        "generated_at": captured_at,
        "proofs": [
            {
                "native_skill": native_skill,
                "proof_id": proof_id,
                "categories": categories,
                "collection_mode": collection_mode,
                "production_ready": True,
                "provenance": {
                    "source": source,
                    "captured_at": captured_at,
                    "artifact_kind": artifact_kind,
                    "command": command,
                },
                "evidence_refs": [evidence_ref(path) for path in evidence_paths],
                "description": description,
            }
        ],
    }
    return write_json(path_text, manifest)


def maybe_write_provider_proof(
    output: dict[str, Any],
    *,
    evidence_out: str = "",
    runtime_proof_out: str = "",
    native_skill: str = "",
    categories: list[str] | None = None,
    collection_mode: str = "live_provider",
    source: str,
    artifact_kind: str,
    command: str,
    description: str,
) -> dict[str, Any]:
    enriched = dict(output)
    evidence_path: Path | None = None
    if evidence_out:
        evidence_path = write_json(evidence_out, enriched)
        enriched["evidence_path"] = str(evidence_path)

    if not runtime_proof_out:
        return enriched

    if enriched.get("ok") is not True or enriched.get("status") != "completed":
        enriched["runtime_proof_manifest_status"] = "not_written"
        enriched["runtime_proof_manifest_reason"] = "Runtime proof requires completed provider evidence."
        return enriched

    if not native_skill:
        enriched["runtime_proof_manifest_status"] = "not_written"
        enriched["runtime_proof_manifest_reason"] = "--native-skill is required when writing runtime proof."
        return enriched

    if evidence_path is None:
        default_evidence = resolve_output_path(runtime_proof_out).with_suffix(".evidence.json")
        evidence_path = write_json(str(default_evidence), enriched)
        enriched["evidence_path"] = str(evidence_path)

    manifest_path = write_runtime_proof_manifest(
        path_text=runtime_proof_out,
        native_skill=native_skill,
        categories=categories or ["provider_source_evidence"],
        collection_mode=collection_mode,
        source=source,
        artifact_kind=artifact_kind,
        command=command,
        evidence_paths=[evidence_path],
        description=description,
    )
    enriched["runtime_proof_manifest"] = str(manifest_path)
    enriched["runtime_proof_manifest_status"] = "written"
    return enriched
