#!/usr/bin/env python3
"""Construct and independently verify a local-only publication handoff bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import jsonschema


SECRET_PATTERNS = (
    re.compile(rb"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{12,}"),
    re.compile(rb"(?i)(?:OPENAI|OPENROUTER|ANTHROPIC)_API_KEY\s*[=:]\s*[^\s\"']+"),
    re.compile(rb"(?i)Bearer\s+[A-Za-z0-9._-]{12,}"),
)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON must be an object: {path}")
    return value


def _schema_path() -> Path:
    return Path(__file__).resolve().parents[1] / "schemas" / "evidence" / "publication_delivery_handoff.v1.schema.json"


def _validate_manifest(payload: dict[str, Any]) -> None:
    schema = _load_object(_schema_path())
    jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(payload)


def _safe_source(raw: str, root: Path) -> Path:
    source = Path(raw)
    if not source.is_absolute():
        source = root / source
    if source.is_symlink() or not source.is_file():
        raise ValueError(f"source must be a regular non-symlink file: {source}")
    resolved = source.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"source escapes source root: {source}") from exc
    return resolved


def _secret_free(data: bytes, label: str) -> None:
    for pattern in SECRET_PATTERNS:
        if pattern.search(data):
            raise ValueError(f"secret-like value detected in {label}")


def construct(request_path: Path, output_dir: Path, source_root: Path) -> Path:
    request_bytes = request_path.read_bytes()
    request = _load_object(request_path)
    if request.get("schema") != "publication_delivery_request.v1":
        raise ValueError("request schema must be publication_delivery_request.v1")
    required = ("delivery_id", "audience", "delivery_format", "content_scope", "permissions", "files")
    if any(not request.get(key) for key in required):
        raise ValueError("request is missing a required delivery field")
    permissions = request["permissions"]
    if permissions != {"distribution_scope": "local_only", "approval_required": True, "approval_state": "not_requested"}:
        raise ValueError("constructor only accepts truthful local-only/not-requested delivery permission")
    if output_dir.exists():
        raise ValueError(f"output directory already exists: {output_dir}")
    staging = output_dir.with_name(output_dir.name + ".tmp")
    if staging.exists():
        shutil.rmtree(staging)
    (staging / "files").mkdir(parents=True)
    files: list[dict[str, Any]] = []
    evidence_index: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    try:
        for index, item in enumerate(request["files"], 1):
            if not isinstance(item, dict):
                raise ValueError("every requested file must be an object")
            file_id = str(item.get("file_id") or "")
            evidence_ids = [str(value) for value in item.get("evidence_ids") or [] if str(value)]
            if not file_id or file_id in seen_ids or not evidence_ids:
                raise ValueError("file_id must be unique and evidence_ids must be non-empty")
            seen_ids.add(file_id)
            source = _safe_source(str(item.get("source_path") or ""), source_root)
            data = source.read_bytes()
            if not data:
                raise ValueError(f"source is empty: {source}")
            _secret_free(data, str(source))
            suffix = source.suffix.lower() or ".bin"
            target_name = f"{index:02d}-{file_id}{suffix}"
            target = staging / "files" / target_name
            target.write_bytes(data)
            digest = _sha(data)
            files.append({
                "file_id": file_id,
                "type": str(item.get("type") or "artifact"),
                "path": f"files/{target_name}",
                "bytes": len(data),
                "sha256": digest,
                "source_sha256": digest,
                "evidence_ids": evidence_ids,
            })
            evidence_index.extend({"evidence_id": evidence_id, "file_id": file_id, "sha256": digest} for evidence_id in evidence_ids)
        checklist = [
            {"check_id": "audience-defined", "status": "completed", "evidence": str(request["audience"]["role"])},
            {"check_id": "format-defined", "status": "completed", "evidence": str(request["delivery_format"])},
            {"check_id": "content-scope-defined", "status": "completed", "evidence": ", ".join(request["content_scope"])},
            {"check_id": "evidence-index-verified", "status": "completed", "evidence": f"{len(evidence_index)} indexed links"},
            {"check_id": "permissions-fail-closed", "status": "completed", "evidence": "local_only; external approval not requested"},
            {"check_id": "secret-scan-clean", "status": "completed", "evidence": f"{len(files)} files scanned"},
        ]
        manifest = {
            "schema": "publication_delivery_handoff.v1",
            "delivery_id": str(request["delivery_id"]),
            "audience": request["audience"],
            "delivery_format": request["delivery_format"],
            "content_scope": request["content_scope"],
            "permissions": permissions,
            "handoff_checklist": checklist,
            "files": files,
            "evidence_index": evidence_index,
            "provenance": {
                "request_sha256": _sha(request_bytes),
                "constructed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "tool": "harness/tools/publication_delivery_bundle.py",
            },
            "limitations": ["This is a local handoff bundle; external distribution and recipient acceptance were not requested or performed."],
        }
        _validate_manifest(manifest)
        manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
        _secret_free(manifest_bytes, "publication-delivery-manifest.json")
        (staging / "publication-delivery-manifest.json").write_bytes(manifest_bytes)
        staging.rename(output_dir)
        return output_dir / "publication-delivery-manifest.json"
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise


def verify(bundle_dir: Path) -> Path:
    manifest_path = bundle_dir / "publication-delivery-manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    _secret_free(manifest_bytes, "publication-delivery-manifest.json")
    manifest = json.loads(manifest_bytes)
    if not isinstance(manifest, dict):
        raise ValueError("publication delivery manifest must be an object")
    _validate_manifest(manifest)
    expected_paths = {"publication-delivery-manifest.json", *[str(item["path"]) for item in manifest["files"]]}
    actual_paths = {
        path.relative_to(bundle_dir).as_posix()
        for path in bundle_dir.rglob("*")
        if path.is_file() or path.is_symlink()
    }
    if actual_paths != expected_paths:
        raise ValueError(f"bundle inventory mismatch: unexpected={sorted(actual_paths - expected_paths)}, missing={sorted(expected_paths - actual_paths)}")
    for item in manifest["files"]:
        path = bundle_dir / item["path"]
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"bundle file missing or unsafe: {item['path']}")
        resolved = path.resolve()
        try:
            resolved.relative_to(bundle_dir.resolve())
        except ValueError as exc:
            raise ValueError(f"bundle file escapes root: {item['path']}") from exc
        data = path.read_bytes()
        _secret_free(data, item["path"])
        if len(data) != item["bytes"] or _sha(data) != item["sha256"] or item["sha256"] != item["source_sha256"]:
            raise ValueError(f"bundle file integrity mismatch: {item['path']}")
    evidence_pairs = {(item["evidence_id"], item["file_id"], item["sha256"]) for item in manifest["evidence_index"]}
    expected_pairs = {(evidence_id, item["file_id"], item["sha256"]) for item in manifest["files"] for evidence_id in item["evidence_ids"]}
    if evidence_pairs != expected_pairs:
        raise ValueError("evidence index does not exactly match bundled files")
    return manifest_path


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build")
    build.add_argument("--request", type=Path, required=True)
    build.add_argument("--output-dir", type=Path, required=True)
    build.add_argument("--source-root", type=Path, required=True)
    check = sub.add_parser("verify")
    check.add_argument("--bundle-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        path = construct(args.request, args.output_dir, args.source_root) if args.command == "build" else verify(args.bundle_dir)
        print(json.dumps({"status": "completed", "manifest": str(path)}))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
