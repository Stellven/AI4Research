"""Closeout for compiled requirement-compiler sprints with review artifacts."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _extract_title(contract_path: Path, handoff_path: Path, sprint_id: str) -> str:
    for candidate in (contract_path, handoff_path):
        if not candidate.exists():
            continue
        text = candidate.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("#"):
                cleaned = re.sub(r"^#+\s*", "", stripped)
                cleaned = re.sub(r"^(Compiled Contract|Contract|Handoff)\s*[—-]\s*", "", cleaned)
                return cleaned.strip() or sprint_id
    return sprint_id


def _ensure_status(status_path: Path, sprint_id: str, title: str) -> Path:
    if status_path.exists():
        return status_path
    payload = {
        "id": sprint_id,
        "sprint_id": sprint_id,
        "title": title,
        "status": "reviewing",
        "phase": "handoff_ready",
        "handoff_to": "evaluator",
        "target_role": "evaluator",
        "created_at": _now(),
        "updated_at": _now(),
        "history": [
            {
                "ts": _now(),
                "event": "compiled_sprint_status_bootstrapped",
                "by": "compiled_sprint_review_closeout",
            }
        ],
    }
    _write_json(status_path, payload)
    return status_path


def build_eval_payload(*, sprint_id: str, contract: str, acceptance_verdict: dict[str, Any], coverage_report: dict[str, Any], handoff_path: Path) -> dict[str, Any]:
    verdict = str(acceptance_verdict.get("verdict") or "FAIL").upper()
    coverage = (coverage_report.get("summary") or {}).get("coverage_ratio", 0.0)
    return {
        "sprint_id": sprint_id,
        "round": 1,
        "verdict": verdict,
        "checked_at": _now(),
        "passed_conditions": [] if verdict != "PASS" else ["acceptance_verdict_passed"],
        "failed_conditions": list(acceptance_verdict.get("reasons") or []) if verdict != "PASS" else [],
        "warnings": [],
        "evidence": {
            "contract_md": contract,
            "handoff_md": str(handoff_path),
            "coverage_ratio": coverage,
            "coverage_report": str(handoff_path.with_name(f"{sprint_id}.coverage_report.json")),
            "acceptance_verdict": str(handoff_path.with_name(f"{sprint_id}.acceptance_verdict.json")),
        },
        "summary": f"Compiled sprint review derived from acceptance_verdict={verdict} coverage_ratio={coverage}.",
    }


def closeout_compiled_sprint(runtime_root: Path, sprint_id: str) -> dict[str, Any]:
    sprint_root = runtime_root / "sprints"
    handoff = sprint_root / f"{sprint_id}.handoff.md"
    contract = sprint_root / f"{sprint_id}.contract.md"
    acceptance = sprint_root / f"{sprint_id}.acceptance_verdict.json"
    coverage = sprint_root / f"{sprint_id}.coverage_report.json"
    status_path = sprint_root / f"{sprint_id}.status.json"
    eval_path = sprint_root / f"{sprint_id}.eval.json"

    acceptance_payload = _load_json(acceptance)
    coverage_payload = _load_json(coverage)
    _ensure_status(status_path, sprint_id, title=_extract_title(contract, handoff, sprint_id))
    eval_payload = build_eval_payload(
        sprint_id=sprint_id,
        contract=str(contract),
        acceptance_verdict=acceptance_payload,
        coverage_report=coverage_payload,
        handoff_path=handoff,
    )
    _write_json(eval_path, eval_payload)

    from runtime_status import transition_status  # noqa: WPS433

    verdict = str(eval_payload.get("verdict") or "FAIL").upper()
    new_status = "passed" if verdict == "PASS" else "failed_review"
    updated, message = transition_status(
        status_path,
        new_status,
        "compiled_sprint_review_closeout",
        "compiled_sprint_review_closeout",
        extra={
            "eval_json": str(eval_path),
            "status_fields": {
                "stage": "completed" if verdict == "PASS" else "reviewed_failed",
                "active_node": None,
                "handoff_to": "" if verdict == "PASS" else "planner",
                "target_role": "" if verdict == "PASS" else "planner",
            },
        },
    )
    return {
        "ok": True,
        "sprint_id": sprint_id,
        "status": updated,
        "message": message,
        "eval_json": str(eval_path),
    }
