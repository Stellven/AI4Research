#!/usr/bin/env python3
"""Write parity runtime proof for verified approval contracts."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from autosci_runtime_proof import utc_now, write_runtime_proof_manifest

SCHEMA = "autosci_approval_runtime_proof_cli.v1"
CONTRACT_SCHEMA = "autosci_approval_contract.v1"
CONTRACT_ENTRY_KEYS = ("allowlist_evidence", "runtime_evidence", "before_artifacts", "after_artifacts")


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("approval contract must be a JSON object")
    return payload


def resolve_entry_path(raw: str, *, contract_path: Path) -> Path:
    path = Path(str(raw or ""))
    if path.is_absolute():
        return path
    roots = [
        Path(os.environ["HARNESS_DIR"]) if os.environ.get("HARNESS_DIR") else None,
        contract_path.parent,
        Path.cwd(),
    ]
    for root in roots:
        if root is None:
            continue
        candidate = root / path
        if candidate.exists():
            return candidate
    return (roots[0] or Path.cwd()) / path


def contract_entry_paths(contract: dict[str, Any], *, contract_path: Path) -> list[Path]:
    paths: list[Path] = []
    for key in CONTRACT_ENTRY_KEYS:
        entries = contract.get(key)
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            raw = str(entry.get("artifact_path") or entry.get("path") or "").strip()
            if raw:
                paths.append(resolve_entry_path(raw, contract_path=contract_path))
    return paths


def contract_timestamp(contract: dict[str, Any]) -> str:
    for key in ("timestamp", "generated_at", "captured_at"):
        text = str(contract.get(key) or "").strip()
        if text:
            return text
    return utc_now()


def validation_errors(contract: dict[str, Any], *, contract_path: Path) -> list[str]:
    errors: list[str] = []
    if str(contract.get("schema") or "") != CONTRACT_SCHEMA:
        errors.append(f"contract schema must be {CONTRACT_SCHEMA}")
    if not str(contract.get("approval_ref") or "").strip():
        errors.append("approval_ref is required")
    expected_flags = {
        "approved": True,
        "allowlist_ready": True,
        "before_ready": True,
        "runtime_ready": True,
        "after_ready": True,
        "execution_verified": True,
    }
    for key, expected in expected_flags.items():
        if contract.get(key) is not expected:
            errors.append(f"{key} must be {expected}")
    for key in CONTRACT_ENTRY_KEYS:
        entries = contract.get(key)
        if not isinstance(entries, list) or not entries:
            errors.append(f"{key} must contain at least one artifact entry")
    missing = [str(path) for path in contract_entry_paths(contract, contract_path=contract_path) if not path.exists()]
    if missing:
        errors.extend(f"artifact path does not exist: {path}" for path in missing)
    return errors


def proof_categories(args: argparse.Namespace) -> list[str]:
    categories = [str(item).strip() for item in (args.category or []) if str(item).strip()]
    if not categories:
        categories = ["approval_boundary_evidence", "side_effect_execution_evidence", "external_runtime_evidence"]
    if args.wiki_mutation and "wiki_mutation_evidence" not in categories:
        categories.append("wiki_mutation_evidence")
    return categories


def cmd_from_contract(args: argparse.Namespace) -> int:
    contract_path = Path(args.contract_json)
    try:
        contract = load_json(contract_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        out = {"schema": SCHEMA, "status": "failed", "ok": False, "reason": str(exc)}
        print(json.dumps(out, indent=2, sort_keys=True))
        return 2
    errors = validation_errors(contract, contract_path=contract_path)
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
    evidence_paths = [contract_path, *contract_entry_paths(contract, contract_path=contract_path)]
    out: dict[str, Any] = {
        "schema": SCHEMA,
        "status": "completed",
        "ok": True,
        "approval_ref": str(contract.get("approval_ref") or ""),
        "action": str(contract.get("action") or ""),
        "evidence_path_count": len(evidence_paths),
        "runtime_proof_manifest_status": "not_requested",
    }
    if args.runtime_proof_out:
        manifest_path = write_runtime_proof_manifest(
            path_text=args.runtime_proof_out,
            native_skill=args.native_skill,
            categories=proof_categories(args),
            collection_mode="approved_side_effect",
            source="approval_contract",
            artifact_kind="approval_runtime_contract",
            command=" ".join(sys.argv),
            evidence_paths=evidence_paths,
            description="Verified approval contract and runtime side-effect evidence for AutoSci parity.",
            generated_at=contract_timestamp(contract),
        )
        out["runtime_proof_manifest"] = str(manifest_path)
        out["runtime_proof_manifest_status"] = "written"
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    command = sub.add_parser("from-contract")
    command.add_argument("contract_json")
    command.add_argument("--native-skill", default="")
    command.add_argument("--runtime-proof-out", default="")
    command.add_argument("--category", action="append", default=[])
    command.add_argument("--wiki-mutation", action="store_true")
    command.set_defaults(func=cmd_from_contract)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
