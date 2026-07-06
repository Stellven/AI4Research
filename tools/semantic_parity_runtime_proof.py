#!/usr/bin/env python3
"""Write parity runtime proof for completed semantic parity audits."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from autosci_runtime_proof import utc_now, write_runtime_proof_manifest

SCHEMA = "autosci_semantic_parity_runtime_proof_cli.v1"
AUDIT_SCHEMA = "autosci_semantic_parity_audit.v1"
REPO_ROOT = Path(__file__).resolve().parents[1]


def configured_autosci_repo() -> Path:
    for key in ("AUTOSCI_REPO", "AUTOSCI_NATIVE_REPO", "NATIVE_AUTOSCI_REPO"):
        value = str(os.environ.get(key) or "").strip()
        if value:
            return Path(value).expanduser()
    return REPO_ROOT.parent / "AutoSci"


def configured_evidence_roots() -> list[Path]:
    roots: list[Path] = []
    if os.environ.get("HARNESS_DIR"):
        roots.append(Path(os.environ["HARNESS_DIR"]).expanduser())
    roots.extend([REPO_ROOT, Path.cwd()])
    for raw in str(os.environ.get("SOLAR_AUTOSCI_EVIDENCE_ROOTS") or "").split(os.pathsep):
        value = raw.strip()
        if value:
            roots.append(Path(value).expanduser())
    deduped: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(root)
    return deduped


def native_repo_ref_candidate(path: Path) -> Path | None:
    parts = list(path.parts)
    if "AutoSci" not in parts:
        return None
    index = parts.index("AutoSci")
    tail = parts[index + 1 :]
    if not tail:
        return configured_autosci_repo()
    return configured_autosci_repo() / Path(*tail)


def evidence_root_candidates(root: Path, path: Path) -> list[Path]:
    candidates = [root / path]
    if path.parts and path.parts[0] == "harness" and root.name == "harness":
        candidates.append(root / Path(*path.parts[1:]))
    if path.parts and path.parts[0] == "artifacts" and root.name != "harness":
        candidates.append(root / "harness" / path)
    return candidates


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("semantic parity audit must be a JSON object")
    return payload


def non_empty_strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item or "").strip()]


def resolve_ref(ref: str, *, audit_path: Path) -> Path | None:
    text = str(ref or "").strip()
    if not text or text.startswith(("route:", "native:", "runtime:", "http://", "https://")):
        return None
    path = Path(text)
    if path.is_absolute():
        return path
    candidates = [audit_path.parent / path]
    native_candidate = native_repo_ref_candidate(path)
    if native_candidate is not None:
        candidates.append(native_candidate)
    for root in configured_evidence_roots():
        candidates.extend(evidence_root_candidates(root, path))
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def audit_timestamp(payload: dict[str, Any]) -> str:
    provenance = payload.get("provenance") if isinstance(payload.get("provenance"), dict) else {}
    for value in (payload.get("audited_at"), payload.get("generated_at"), provenance.get("timestamp")):
        text = str(value or "").strip()
        if text:
            return text
    return utc_now()


def checks_pass(payload: dict[str, Any]) -> bool:
    checks = payload.get("acceptance_checks")
    if not isinstance(checks, list) or not checks:
        return False
    for check in checks:
        if not isinstance(check, dict):
            return False
        status = str(check.get("status") or "").lower()
        if status not in {"ok", "pass", "passed"}:
            return False
    return True


def validation_errors(payload: dict[str, Any], *, audit_path: Path, native_skill: str) -> list[str]:
    errors: list[str] = []
    if str(payload.get("schema") or "") != AUDIT_SCHEMA:
        errors.append(f"audit schema must be {AUDIT_SCHEMA}")
    if str(payload.get("status") or "") != "completed":
        errors.append("audit status must be completed")
    audit_skill = str(payload.get("native_skill") or "").strip()
    if not audit_skill:
        errors.append("native_skill is required")
    elif native_skill and audit_skill != native_skill:
        errors.append(f"audit native_skill {audit_skill} does not match requested {native_skill}")
    if str(payload.get("semantic_parity") or "") != "full":
        errors.append("semantic_parity must be full")
    if not str(payload.get("auditor") or "").strip():
        errors.append("auditor is required")
    native_refs = non_empty_strings(payload.get("native_evidence_refs"))
    solar_refs = non_empty_strings(payload.get("solar_evidence_refs"))
    if not native_refs:
        errors.append("native_evidence_refs are required")
    if not solar_refs:
        errors.append("solar_evidence_refs are required")
    if not checks_pass(payload):
        errors.append("acceptance_checks must all pass")
    for ref in [*native_refs, *solar_refs]:
        path = resolve_ref(ref, audit_path=audit_path)
        if path is not None and not path.exists():
            errors.append(f"evidence ref does not exist: {ref}")
    return errors


def evidence_paths(payload: dict[str, Any], *, audit_path: Path) -> list[Path]:
    paths = [audit_path]
    for ref in [*non_empty_strings(payload.get("native_evidence_refs")), *non_empty_strings(payload.get("solar_evidence_refs"))]:
        path = resolve_ref(ref, audit_path=audit_path)
        if path is not None:
            paths.append(path)
    deduped: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(path)
    return deduped


def cmd_from_audit(args: argparse.Namespace) -> int:
    audit_path = Path(args.audit_json)
    try:
        payload = load_json(audit_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        out = {"schema": SCHEMA, "status": "failed", "ok": False, "reason": str(exc)}
        print(json.dumps(out, indent=2, sort_keys=True))
        return 2
    requested_skill = args.native_skill or str(payload.get("native_skill") or "")
    errors = validation_errors(payload, audit_path=audit_path, native_skill=requested_skill)
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
    if args.runtime_proof_out and not requested_skill:
        out = {
            "schema": SCHEMA,
            "status": "failed",
            "ok": False,
            "reason": "--native-skill or audit native_skill is required with --runtime-proof-out",
            "runtime_proof_manifest_status": "not_written",
        }
        print(json.dumps(out, indent=2, sort_keys=True))
        return 2
    out: dict[str, Any] = {
        "schema": SCHEMA,
        "status": "completed",
        "ok": True,
        "native_skill": requested_skill,
        "runtime_proof_manifest_status": "not_requested",
    }
    if args.runtime_proof_out:
        manifest_path = write_runtime_proof_manifest(
            path_text=args.runtime_proof_out,
            native_skill=requested_skill,
            categories=["semantic_equivalence_evidence"],
            collection_mode="semantic_audit",
            source=str(payload.get("auditor") or "semantic_parity_audit"),
            artifact_kind=AUDIT_SCHEMA,
            command=" ".join(sys.argv),
            evidence_paths=evidence_paths(payload, audit_path=audit_path),
            description="Completed semantic parity audit for AutoSci route equivalence.",
            generated_at=audit_timestamp(payload),
        )
        out["runtime_proof_manifest"] = str(manifest_path)
        out["runtime_proof_manifest_status"] = "written"
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    command = sub.add_parser("from-audit")
    command.add_argument("audit_json")
    command.add_argument("--native-skill", default="")
    command.add_argument("--runtime-proof-out", default="")
    command.set_defaults(func=cmd_from_audit)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
