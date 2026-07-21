#!/usr/bin/env python3
"""Write parity runtime proof for completed wiki mutation sidecars."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from autosci_runtime_proof import utc_now, write_runtime_proof_manifest

SCHEMA = "autosci_wiki_mutation_runtime_proof_cli.v1"
KNOWN_WRITEBACK_SCHEMAS = {
    "claim_verdict_writeback.v1",
    "novelty_writeback.v1",
    "pilot_verdict_writeback.v1",
    "refine_apply_writeback.v1",
    "source_fan_in_writeback.v1",
}
WIKI_ARTIFACT_TYPES = {
    "wiki_claim_verdict_target",
    "wiki_graph_edges",
    "wiki_idea",
    "wiki_log",
    "wiki_page",
    "wiki_rebuild",
}


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("writeback sidecar must be a JSON object")
    return payload


def resolve_path(raw: str, *, sidecar_path: Path) -> Path:
    path = Path(str(raw or ""))
    if path.is_absolute():
        return path
    roots = [
        Path(os.environ["HARNESS_DIR"]) if os.environ.get("HARNESS_DIR") else None,
        sidecar_path.parent,
        Path.cwd(),
    ]
    for root in roots:
        if root is None:
            continue
        candidate = root / path
        if candidate.exists():
            return candidate
    return (roots[0] or Path.cwd()) / path


def write_dict(payload: dict[str, Any]) -> dict[str, Any]:
    outputs = payload.get("outputs") if isinstance(payload.get("outputs"), dict) else {}
    write = outputs.get("write") if isinstance(outputs.get("write"), dict) else {}
    if write:
        return write
    summary = outputs.get("fan_in") if isinstance(outputs.get("fan_in"), dict) else {}
    return summary


def artifact_paths(payload: dict[str, Any], *, sidecar_path: Path) -> list[Path]:
    paths: list[Path] = []
    for artifact in payload.get("artifacts") or []:
        if not isinstance(artifact, dict):
            continue
        if str(artifact.get("type") or "") not in WIKI_ARTIFACT_TYPES:
            continue
        raw = str(artifact.get("path") or "").strip()
        if raw:
            paths.append(resolve_path(raw, sidecar_path=sidecar_path))
    write = write_dict(payload)
    for key in ("target_path", "idea_path", "log_path", "edge_path"):
        raw = str(write.get(key) or "").strip()
        if raw:
            paths.append(resolve_path(raw, sidecar_path=sidecar_path))
    for key in ("rebuilt_paths", "edge_paths"):
        values = write.get(key) if isinstance(write.get(key), list) else []
        for raw in values:
            if str(raw or "").strip():
                paths.append(resolve_path(str(raw), sidecar_path=sidecar_path))
    deduped: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(path)
    return deduped


def payload_timestamp(payload: dict[str, Any]) -> str:
    provenance = payload.get("provenance") if isinstance(payload.get("provenance"), dict) else {}
    for value in (payload.get("generated_at"), payload.get("captured_at"), provenance.get("timestamp")):
        text = str(value or "").strip()
        if text:
            return text
    return utc_now()


def validation_errors(payload: dict[str, Any], *, sidecar_path: Path) -> list[str]:
    errors: list[str] = []
    if str(payload.get("schema") or "") not in KNOWN_WRITEBACK_SCHEMAS:
        errors.append("writeback schema is not a recognized wiki mutation sidecar")
    if str(payload.get("status") or "") != "completed":
        errors.append("writeback status must be completed")
    write = write_dict(payload)
    if write.get("applied") is not True:
        errors.append("outputs.write.applied must be true")
    paths = artifact_paths(payload, sidecar_path=sidecar_path)
    if not paths:
        errors.append("writeback must reference wiki mutation artifacts")
    missing = [str(path) for path in paths if not path.exists()]
    if missing:
        errors.extend(f"wiki artifact path does not exist: {path}" for path in missing)
    return errors


def cmd_from_writeback(args: argparse.Namespace) -> int:
    sidecar_path = Path(args.writeback_json)
    try:
        payload = load_json(sidecar_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        out = {"schema": SCHEMA, "status": "failed", "ok": False, "reason": str(exc)}
        print(json.dumps(out, indent=2, sort_keys=True))
        return 2
    errors = validation_errors(payload, sidecar_path=sidecar_path)
    if errors:
        out = {
            "schema": SCHEMA,
            "status": "inconclusive",
            "ok": False,
            "errors": errors,
            "runtime_proof_manifest_status": "not_written",
        }
        print(json.dumps(out, indent=2, sort_keys=True))
        return 0
    if args.runtime_proof_out and not args.native_skill:
        out = {
            "schema": SCHEMA,
            "status": "failed",
            "ok": False,
            "reason": "--native-skill is required with --runtime-proof-out",
            "runtime_proof_manifest_status": "not_written",
        }
        print(json.dumps(out, indent=2, sort_keys=True))
        return 2
    evidence_paths = [sidecar_path, *artifact_paths(payload, sidecar_path=sidecar_path)]
    out: dict[str, Any] = {
        "schema": SCHEMA,
        "status": "completed",
        "ok": True,
        "writeback_schema": str(payload.get("schema") or ""),
        "evidence_path_count": len(evidence_paths),
        "runtime_proof_manifest_status": "not_requested",
    }
    if args.runtime_proof_out:
        manifest_path = write_runtime_proof_manifest(
            path_text=args.runtime_proof_out,
            native_skill=args.native_skill,
            categories=["wiki_mutation_evidence"],
            collection_mode=args.collection_mode,
            source="wiki_writeback_sidecar",
            artifact_kind=str(payload.get("schema") or "wiki_writeback"),
            command=" ".join(sys.argv),
            evidence_paths=evidence_paths,
            description="Completed wiki mutation writeback sidecar for AutoSci parity.",
            generated_at=payload_timestamp(payload),
        )
        out["runtime_proof_manifest"] = str(manifest_path)
        out["runtime_proof_manifest_status"] = "written"
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    command = sub.add_parser("from-writeback")
    command.add_argument("writeback_json")
    command.add_argument("--native-skill", default="")
    command.add_argument("--runtime-proof-out", default="")
    command.add_argument("--collection-mode", default="approved_side_effect")
    command.set_defaults(func=cmd_from_writeback)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
