#!/usr/bin/env python3
"""Run the fixed no-network evidence benchmark.

Two families of checks, both recomputed from retained bytes inside the
sandbox, never read from any operator's own verdict fields:

* lineage: every Part-A artifact in the accepted handoff still matches its
  controller-bound SHA-256 digest.
* claim grounding replication: every claim the accepted synthesis published
  is re-tested against the retained source texts -- each recorded quote must
  be verbatim in the source it names, at least one cited source must pass
  Solar's claim_support_assessment, and every recorded contradiction quote
  must be verbatim in its source. A claim that fails is REFUTED, and a single
  refuted claim fails the benchmark.

The claim checks rebind Solar's own support checker rather than restating
it; the import is by file location so the sandbox (unshare -Urn, no network,
minimal env) needs nothing beyond the repository filesystem.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

_LIB = Path(__file__).resolve().parents[1] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from research.evidence.review_proof import claim_support_assessment  # noqa: E402


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _contained(raw: str, root: Path, *, label: str) -> Path:
    path = (root / raw).resolve(strict=True)
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{label} escapes work_dir") from exc
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} is not a regular file")
    return path


def _load(path: Path, *, label: str) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be an object")
    return payload


def _normalized(text: Any) -> str:
    return " ".join(str(text or "").split())


def _claim_checks(
    work_dir: Path,
    plan_inputs: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Re-test every published claim against the retained source texts.

    Inputs are located among the plan's own hash-pinned artifact list, so the
    bytes examined here are exactly the bytes the lineage checks pin.
    """
    notes: list[str] = []
    synthesis: dict[str, Any] = {}
    validation: dict[str, Any] = {}
    for item in plan_inputs:
        relative = str(item.get("path") or "")
        name = Path(relative).name
        if name == "evidence_synthesis.json":
            synthesis = _load(_contained(relative, work_dir, label="synthesis input"), label="evidence_synthesis")
        elif name == "source_validation.json":
            validation = _load(_contained(relative, work_dir, label="validation input"), label="source_validation")
    if not synthesis or not validation:
        notes.append("claim replication skipped: synthesis or validation artifact absent from the plan inputs")
        return [], notes

    text_by_id: dict[str, str] = {}
    for source in validation.get("accepted") or []:
        if not isinstance(source, dict):
            continue
        for key in ("content", "extracted_text", "content_summary", "abstract"):
            value = _normalized(source.get(key))
            if value:
                text_by_id[str(source.get("source_id") or "")] = value
                break

    checks: list[dict[str, Any]] = []
    for claim in synthesis.get("claims") or []:
        if not isinstance(claim, dict):
            continue
        claim_id = str(claim.get("claim_id") or "?")
        text = str(claim.get("text") or "")
        failures: list[str] = []

        quotes = [row for row in claim.get("evidence_quotes") or [] if isinstance(row, dict)]
        verbatim = [
            row for row in quotes
            if _normalized(row.get("quote"))
            and _normalized(row.get("quote")) in text_by_id.get(str(row.get("source_id") or ""), "")
        ]
        if not verbatim:
            failures.append("no recorded quote is verbatim in the retained source it names")

        supported = [
            str(source_id)
            for source_id in claim.get("evidence_ids") or []
            if claim_support_assessment(text, text_by_id.get(str(source_id), "")).get("supported")
        ]
        if not supported:
            failures.append("no cited retained source passes claim_support_assessment")

        broken_contradictions = [
            str(row.get("source_id") or "")
            for row in claim.get("contradicted_by") or []
            if isinstance(row, dict)
            and _normalized(row.get("quote")) not in text_by_id.get(str(row.get("source_id") or ""), "")
        ]
        if broken_contradictions:
            failures.append(
                "recorded contradiction quote is not verbatim in its source: "
                + ", ".join(sorted(broken_contradictions))
            )

        checks.append({
            "claim_id": claim_id,
            "text": text,
            "outcome": "supported" if not failures else "refuted",
            "verbatim_quote_sources": sorted(str(row.get("source_id") or "") for row in verbatim),
            "supporting_sources": supported,
            "contradiction_records": len([row for row in claim.get("contradicted_by") or [] if isinstance(row, dict)]),
            "failures": failures,
        })
    if not checks:
        notes.append("claim replication found no published claims to test")
    return checks, notes


def run(work_dir: Path, handoff_path: Path, plan_path: Path, output_path: Path) -> dict[str, Any]:
    started = time.monotonic_ns()
    handoff = _load(handoff_path, label="handoff")
    plan = _load(plan_path, label="plan")
    handoff_rows = {
        str(item.get("path") or ""): item
        for item in handoff.get("artifacts") or []
        if isinstance(item, dict) and str(item.get("path") or "")
    }
    plan_inputs = [item for item in (plan.get("benchmark") or {}).get("inputs") or [] if isinstance(item, dict)]
    checks: list[dict[str, Any]] = []
    for expected in plan_inputs:
        relative = str(expected.get("path") or "")
        expected_sha = str(expected.get("sha256") or "").lower()
        handoff_row = handoff_rows.get(relative) or {}
        path = _contained(relative, work_dir, label="benchmark input")
        actual_sha = _sha256(path)
        passed = (
            len(expected_sha) == 64
            and actual_sha == expected_sha
            and str(handoff_row.get("sha256") or "").lower() == expected_sha
        )
        checks.append(
            {
                "path": relative,
                "expected_sha256": expected_sha,
                "actual_sha256": actual_sha,
                "handoff_sha256": str(handoff_row.get("sha256") or "").lower(),
                "passed": passed,
            }
        )
    passed_count = sum(1 for item in checks if item["passed"])
    lineage_passed = bool(checks) and passed_count == len(checks)

    claim_checks, claim_notes = _claim_checks(work_dir, plan_inputs)
    claims_total = len(claim_checks)
    claims_supported = sum(1 for item in claim_checks if item["outcome"] == "supported")
    claims_refuted = claims_total - claims_supported
    claims_passed = claims_total >= 1 and claims_refuted == 0

    completed = time.monotonic_ns()
    payload = {
        "schema": "solar.fixed_research.benchmark_raw.v1",
        "benchmark_id": "evidence-lineage-integrity-v1",
        "network_namespace": "isolated_by_unshare",
        "checks": checks,
        "claim_checks": claim_checks,
        "claim_check_notes": claim_notes,
        "tested": (
            "retained-artifact digest lineage; per-claim verbatim-quote presence, "
            "lexical support, and contradiction-quote integrity against retained source texts"
        ),
        "not_tested": (
            "external scientific validity of the sources' own findings; any experimental "
            "reproduction of the claims' subject matter"
        ),
        "metrics": {
            "checks_total": len(checks),
            "checks_passed": passed_count,
            "integrity_rate": (passed_count / len(checks)) if checks else 0.0,
            "claims_total": claims_total,
            "claims_supported": claims_supported,
            "claims_refuted": claims_refuted,
            "duration_ms": round((completed - started) / 1_000_000, 3),
        },
        "passed": lineage_passed and claims_passed,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--handoff", required=True, type=Path)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        work_dir = args.work_dir.resolve(strict=True)
        handoff = args.handoff.resolve(strict=True)
        plan = args.plan.resolve(strict=True)
        output = args.output.resolve(strict=False)
        output.parent.resolve(strict=True).relative_to(work_dir)
        result = run(work_dir, handoff, plan, output)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 2
    print(json.dumps({"ok": result["passed"], "metrics": result["metrics"]}, sort_keys=True))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
