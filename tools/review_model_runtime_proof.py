#!/usr/bin/env python3
"""Write parity runtime proof for completed Review LLM/model evidence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from autosci_runtime_proof import utc_now, write_runtime_proof_manifest

SCHEMA = "autosci_review_model_runtime_proof_cli.v1"


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("evidence JSON must be an object")
    return payload


def payload_timestamp(payload: dict[str, Any]) -> str:
    provenance = payload.get("provenance") if isinstance(payload.get("provenance"), dict) else {}
    for value in (
        payload.get("generated_at"),
        payload.get("captured_at"),
        provenance.get("timestamp"),
        provenance.get("captured_at"),
    ):
        text = str(value or "").strip()
        if text:
            return text
    return utc_now()


def non_empty_strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item or "").strip()]


def completed_review_llm(payload: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    if str(payload.get("schema") or "") != "artifact_review.v1":
        return None, "not artifact_review.v1"
    outputs = payload.get("outputs") if isinstance(payload.get("outputs"), dict) else {}
    review = outputs.get("review") if isinstance(outputs.get("review"), dict) else {}
    review_llm = review.get("review_llm") if isinstance(review.get("review_llm"), dict) else {}
    mode = str(review.get("review_mode") or review_llm.get("review_mode") or "")
    evidence_ids = non_empty_strings(review.get("evidence_ids")) or non_empty_strings(review_llm.get("evidence_ids"))
    if str(payload.get("status") or "") != "completed":
        return None, "artifact_review.v1 status must be completed"
    if mode not in {"review_llm", "llm_review", "external_review"}:
        return None, "review_mode must be review_llm, llm_review, or external_review"
    if review.get("review_available") is not True and review_llm.get("review_available") is not True:
        return None, "review_available must be true"
    if not evidence_ids:
        return None, "Review LLM evidence_ids are required"
    provider = str(review_llm.get("provider") or review.get("provider") or "").strip()
    model = str(review_llm.get("model") or review.get("model") or "").strip()
    provenance = payload.get("provenance") if isinstance(payload.get("provenance"), dict) else {}
    source = provider or model or str(provenance.get("operator_id") or "").strip() or "review_llm_evidence"
    return {
        "evidence_kind": "artifact_review",
        "source": source,
        "artifact_kind": "artifact_review",
        "evidence_ids": evidence_ids,
    }, ""


def completed_model_response(payload: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    if str(payload.get("schema") or "") != "autosci_model_response.v1":
        return None, "not autosci_model_response.v1"
    outputs = payload.get("outputs") if isinstance(payload.get("outputs"), dict) else {}
    evidence_ids = non_empty_strings(outputs.get("evidence_ids")) or non_empty_strings(payload.get("evidence_ids"))
    answer = str(outputs.get("answer") or payload.get("answer") or "").strip()
    ideas = outputs.get("ideas") if isinstance(outputs.get("ideas"), list) else payload.get("ideas")
    if str(payload.get("status") or "") != "completed":
        return None, "autosci_model_response.v1 status must be completed"
    if not evidence_ids:
        return None, "model evidence_ids are required"
    if not answer and not ideas:
        return None, "model response requires answer or ideas"
    provider = str(outputs.get("provider") or payload.get("provider") or "").strip()
    model = str(outputs.get("model") or payload.get("model") or "").strip()
    source = provider or model or "model_evidence"
    return {
        "evidence_kind": "model_response",
        "source": source,
        "artifact_kind": "model_response",
        "evidence_ids": evidence_ids,
    }, ""


def evidence_summary(payload: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    for checker in (completed_review_llm, completed_model_response):
        summary, reason = checker(payload)
        if summary is not None:
            return summary, ""
        if reason.startswith("not "):
            continue
        return None, reason
    return None, "evidence must be artifact_review.v1 or autosci_model_response.v1"


def cmd_from_evidence(args: argparse.Namespace) -> int:
    evidence_path = Path(args.evidence_json)
    try:
        payload = load_json(evidence_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        out = {"schema": SCHEMA, "status": "failed", "ok": False, "reason": str(exc)}
        print(json.dumps(out, indent=2, sort_keys=True))
        return 2

    summary, reason = evidence_summary(payload)
    if summary is None:
        out = {
            "schema": SCHEMA,
            "status": "inconclusive",
            "ok": False,
            "reason": reason,
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

    out: dict[str, Any] = {
        "schema": SCHEMA,
        "status": "completed",
        "ok": True,
        "evidence_kind": summary["evidence_kind"],
        "evidence_ids": summary["evidence_ids"],
        "evidence_path": str(evidence_path),
        "runtime_proof_manifest_status": "not_requested",
    }
    if args.runtime_proof_out:
        manifest_path = write_runtime_proof_manifest(
            path_text=args.runtime_proof_out,
            native_skill=args.native_skill,
            categories=["review_llm_or_model_evidence"],
            collection_mode=args.collection_mode,
            source=str(summary["source"]),
            artifact_kind=str(summary["artifact_kind"]),
            command=" ".join(sys.argv),
            evidence_paths=[evidence_path],
            description=f"Completed {summary['evidence_kind']} evidence for AutoSci parity.",
            generated_at=payload_timestamp(payload),
        )
        out["runtime_proof_manifest"] = str(manifest_path)
        out["runtime_proof_manifest_status"] = "written"
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    command = sub.add_parser("from-evidence")
    command.add_argument("evidence_json")
    command.add_argument("--native-skill", default="")
    command.add_argument("--runtime-proof-out", default="")
    command.add_argument("--collection-mode", default="manual_review")
    command.set_defaults(func=cmd_from_evidence)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
