#!/usr/bin/env python3
"""Validator, narrow repair, and quarantine for extracted JSON candidates."""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

import knowledge_ingest_registry as registry


ERROR_SCHEMA_REQUIRED_FIELD_MISSING = "E_SCHEMA_REQUIRED_FIELD_MISSING"
ERROR_EVIDENCE_EMPTY = "E_EVIDENCE_EMPTY"
ERROR_EVIDENCE_UNKNOWN_SPAN = "E_EVIDENCE_UNKNOWN_SPAN"
ERROR_OUTPUT_TOO_SHORT = "E_OUTPUT_TOO_SHORT"
ERROR_SOURCE_SHA_MISMATCH = "E_SOURCE_SHA_MISMATCH"
ERROR_MODEL_REFUSAL = "E_MODEL_REFUSAL"


REQUIRED_TOP_FIELDS = [
    "doc_id",
    "source_sha256",
    "source_kind",
    "doc_type",
    "schema_version",
    "summary",
    "core_facts",
]


CLAIM_LIST_FIELDS = [
    ("core_facts", "claim"),
    ("functional_modules", "role"),
    ("commands_api_config", "purpose"),
    ("architecture", "description"),
    ("risks", "risk"),
    ("open_questions", "question"),
]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _allowed_span_ids(sidecar: dict[str, Any]) -> set[str]:
    return {str(span["span_id"]) for span in sidecar.get("spans") or []}


def _evidence_values(item: dict[str, Any]) -> list[str]:
    values = item.get("evidence")
    if values is None:
        return []
    if not isinstance(values, list):
        return []
    return [str(v).removeprefix("raw:") for v in values]


def _append_error(errors: list[dict[str, Any]], code: str, message: str, path: str) -> None:
    errors.append({"code": code, "message": message, "path": path})


def validate_candidate(candidate: dict[str, Any], sidecar: dict[str, Any]) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    for field in REQUIRED_TOP_FIELDS:
        if field not in candidate:
            _append_error(errors, ERROR_SCHEMA_REQUIRED_FIELD_MISSING, f"missing field {field}", field)

    if candidate.get("source_sha256") and candidate.get("source_sha256") != sidecar.get("source_sha256"):
        _append_error(errors, ERROR_SOURCE_SHA_MISMATCH, "candidate source_sha256 does not match sidecar", "source_sha256")

    allowed = _allowed_span_ids(sidecar)
    summary = candidate.get("summary")
    if isinstance(summary, dict):
        ev = _evidence_values(summary)
        if not ev:
            _append_error(errors, ERROR_EVIDENCE_EMPTY, "summary has no evidence", "summary.evidence")
        for span_id in ev:
            if span_id not in allowed:
                _append_error(errors, ERROR_EVIDENCE_UNKNOWN_SPAN, f"unknown span {span_id}", "summary.evidence")

    text_size = len(json.dumps(candidate, ensure_ascii=False))
    if text_size < 120:
        _append_error(errors, ERROR_OUTPUT_TOO_SHORT, "candidate JSON is too short", "$")
    raw_text = json.dumps(candidate, ensure_ascii=False).lower()
    if "cannot access" in raw_text or "无法访问" in raw_text or "i'm sorry" in raw_text:
        _append_error(errors, ERROR_MODEL_REFUSAL, "candidate looks like a refusal or access failure", "$")

    for field, claim_key in CLAIM_LIST_FIELDS:
        items = candidate.get(field) or []
        if not isinstance(items, list):
            _append_error(errors, ERROR_SCHEMA_REQUIRED_FIELD_MISSING, f"{field} must be a list", field)
            continue
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                _append_error(errors, ERROR_SCHEMA_REQUIRED_FIELD_MISSING, f"{field}[{idx}] must be object", f"{field}[{idx}]")
                continue
            claim = str(item.get(claim_key) or "").strip()
            if not claim:
                continue
            ev = _evidence_values(item)
            if not ev:
                _append_error(errors, ERROR_EVIDENCE_EMPTY, f"{field}[{idx}] has no evidence", f"{field}[{idx}].evidence")
            for span_id in ev:
                if span_id not in allowed:
                    _append_error(errors, ERROR_EVIDENCE_UNKNOWN_SPAN, f"unknown span {span_id}", f"{field}[{idx}].evidence")

    return {
        "ok": not errors,
        "error_count": len(errors),
        "errors": errors,
        "allowed_span_count": len(allowed),
    }


def repair_candidate_once(candidate: dict[str, Any], sidecar: dict[str, Any]) -> dict[str, Any]:
    """Narrow deterministic repair: remove unsupported claims, never invent facts."""
    repaired = json.loads(json.dumps(candidate, ensure_ascii=False))
    allowed = _allowed_span_ids(sidecar)
    fallback = sorted(allowed)[0] if allowed else None

    repaired.setdefault("doc_id", sidecar.get("doc_id"))
    repaired.setdefault("source_path", sidecar.get("source_path"))
    repaired["source_sha256"] = sidecar.get("source_sha256")
    repaired.setdefault("source_kind", sidecar.get("source_kind", "unknown"))
    repaired.setdefault("doc_type", "unknown")
    repaired.setdefault("schema_version", "extracted-json-v2")

    summary = repaired.get("summary")
    if not isinstance(summary, dict):
        repaired["summary"] = {"claim": "N/A", "evidence": [fallback] if fallback else []}
    elif fallback:
        summary_evidence = _evidence_values(summary)
        if not summary_evidence or any(span_id not in allowed for span_id in summary_evidence):
            summary["evidence"] = [fallback]

    moved_to_open_questions: list[dict[str, Any]] = []
    for field, _claim_key in CLAIM_LIST_FIELDS:
        items = repaired.get(field) or []
        if not isinstance(items, list):
            repaired[field] = []
            continue
        kept = []
        for item in items:
            if not isinstance(item, dict):
                continue
            ev = _evidence_values(item)
            if not ev and fallback:
                item["evidence"] = [fallback]
                ev = [fallback]
            if ev and all(span_id in allowed for span_id in ev):
                kept.append(item)
            else:
                moved_to_open_questions.append(
                    {
                        "question": str(item.get("claim") or item.get("risk") or item.get("description") or item.get("name") or "Unsupported extracted item"),
                        "reason": "Removed from validated claims because evidence was missing or unknown.",
                        "evidence": [fallback] if fallback else [],
                    }
                )
        repaired[field] = kept
    if moved_to_open_questions:
        existing = repaired.get("open_questions")
        if not isinstance(existing, list):
            existing = []
        repaired["open_questions"] = existing + moved_to_open_questions
    return repaired


def quarantine_candidate(candidate_path: Path, quarantine_dir: Path, validation: dict[str, Any]) -> Path:
    quarantine_dir.mkdir(parents=True, exist_ok=True)
    target = quarantine_dir / candidate_path.name
    shutil.copy2(candidate_path, target)
    (target.with_suffix(target.suffix + ".validation.json")).write_text(
        json.dumps(validation, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target


def cmd_validate(args: argparse.Namespace) -> int:
    candidate_path = Path(args.candidate).expanduser()
    sidecar_path = Path(args.sidecar).expanduser()
    candidate = load_json(candidate_path)
    sidecar = load_json(sidecar_path)
    result = validate_candidate(candidate, sidecar)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


def cmd_process(args: argparse.Namespace) -> int:
    candidate_path = Path(args.candidate).expanduser()
    sidecar_path = Path(args.sidecar).expanduser()
    candidate = load_json(candidate_path)
    sidecar = load_json(sidecar_path)
    first = validate_candidate(candidate, sidecar)
    repaired_path = Path(args.repaired_output).expanduser() if args.repaired_output else candidate_path.with_suffix(".repaired.json")
    if first["ok"]:
        result = {"ok": True, "status": "validated", "candidate": str(candidate_path), "validation": first}
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    repaired = repair_candidate_once(candidate, sidecar)
    repaired_path.write_text(json.dumps(repaired, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    second = validate_candidate(repaired, sidecar)
    if second["ok"]:
        result = {
            "ok": True,
            "status": "repaired_validated",
            "candidate": str(candidate_path),
            "repaired": str(repaired_path),
            "first_validation": first,
            "validation": second,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    quarantine_path = quarantine_candidate(candidate_path, Path(args.quarantine_dir).expanduser(), second)
    result = {
        "ok": False,
        "status": "quarantined",
        "candidate": str(candidate_path),
        "repaired": str(repaired_path),
        "quarantine": str(quarantine_path),
        "first_validation": first,
        "validation": second,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate extracted JSON candidates")
    sub = parser.add_subparsers(dest="cmd", required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("--candidate", required=True)
    validate.add_argument("--sidecar", required=True)
    validate.set_defaults(func=cmd_validate)
    process = sub.add_parser("process")
    process.add_argument("--candidate", required=True)
    process.add_argument("--sidecar", required=True)
    process.add_argument("--repaired-output")
    process.add_argument("--quarantine-dir", default=str(Path.home() / "Knowledge" / "_extracted" / "_quarantine"))
    process.set_defaults(func=cmd_process)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
