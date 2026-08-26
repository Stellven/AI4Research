#!/usr/bin/env python3
"""Run the 25 canonical prompts through the live Intent/Requirement pipeline."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
HARNESS = HERE.parents[2]
REPO = HARNESS.parent
CATALOG = (
    HARNESS
    / "metadata"
    / "2-intent compiler output"
    / "requirement-compiler-input-fixtures"
    / "fixture_catalog.json"
)
STAGE1 = HARNESS / "metadata" / "1-input normalizer output" / "live-25-prompt-pipeline-20260826"
STAGE2 = HERE
STAGE3 = HARNESS / "metadata" / "3-requirements compiler output" / "live-25-prompt-pipeline-20260826"


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _copy_if_present(source: Path, destination: Path) -> bool:
    if not source.is_file():
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return True


def _case_terminal_status(case_id: str) -> tuple[str, bool] | None:
    intent = STAGE2 / case_id / "intent_ir.json"
    requirement = STAGE3 / case_id / "requirement_ir.json"
    result = STAGE2 / case_id / "pipeline_result.json"
    if not (intent.is_file() and result.is_file()):
        return None
    try:
        payload = json.loads(result.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    status = str(payload.get("readiness_status") or "")
    ready = bool(payload.get("ready"))
    if status == "accepted" and ready and requirement.is_file():
        return status, ready
    if status == "needs_clarification" and not ready:
        return status, ready
    return None


def _next_intent_id(work_root: Path, case_id: str) -> str:
    """Return a fresh gateway id without deleting evidence from failed attempts."""
    if not (work_root / case_id).exists():
        return case_id
    attempt = 1
    while (work_root / f"{case_id}-retry-{attempt:02d}").exists():
        attempt += 1
    return f"{case_id}-retry-{attempt:02d}"


def _collect_case(case: dict[str, Any], work_root: Path, env: dict[str, str]) -> dict[str, Any]:
    case_id = str(case["case_id"])
    terminal = _case_terminal_status(case_id)
    if terminal is not None:
        status, ready = terminal
        print(f"SKIP {case_id}: terminal status={status}", flush=True)
        return {"case_id": case_id, "status": status, "ready": ready, "resumed": True}

    intent_id = _next_intent_id(work_root, case_id)

    command = [
        sys.executable,
        str(HARNESS / "lib" / "intent_gateway.py"),
        "capture",
        "--text",
        str(case["prompt"]),
        "--intent-id",
        intent_id,
        "--source-channel",
        "pipeline_contract_test",
        "--source-trust",
        "pipeline_contract_test",
        "--no-autodispatch",
        "--json",
    ]
    process = subprocess.run(
        command,
        cwd=REPO,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    try:
        result = json.loads(process.stdout)
    except ValueError:
        result = {
            "ok": False,
            "ready": False,
            "readiness_status": "invalid_gateway_output",
        }
    result.update(
        {
            "case_id": case_id,
            "intent_id": intent_id,
            "category": case.get("category"),
            "prompt": case.get("prompt"),
            "gateway_exit_code": process.returncode,
            "stderr_tail": process.stderr[-4000:],
        }
    )

    source = work_root / intent_id
    stage1_case = STAGE1 / case_id
    stage2_case = STAGE2 / case_id
    stage3_case = STAGE3 / case_id
    _copy_if_present(source / "raw_intent.json", stage1_case / "raw_intent.json")
    for name in (
        "intent_ir.json",
        "intent_validation.json",
        "intent_fidelity.json",
        "intent_acceptance.json",
        "repair_record.json",
    ):
        _copy_if_present(source / "intent" / name, stage2_case / name)
    receipts = []
    for receipt in sorted((source / "intent").glob("generation-*/**/model_call_receipt.json")):
        try:
            receipt_payload = json.loads(receipt.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        receipts.append({"path": str(receipt.relative_to(source / "intent")), **receipt_payload})
    if receipts:
        _write_json(stage2_case / "model_call_receipts.json", {"calls": receipts})
    for name in (
        "requirement_ir.json",
        "requirement_format_evaluation.json",
        "requirement_trace.json",
    ):
        _copy_if_present(source / name, stage3_case / name)
    _write_json(stage2_case / "pipeline_result.json", result)

    status = str(result.get("readiness_status") or "unknown")
    print(
        f"DONE {case_id}: exit={process.returncode} ready={bool(result.get('ready'))} status={status}",
        flush=True,
    )
    return {
        "case_id": case_id,
        "status": status,
        "ready": bool(result.get("ready")),
        "exit_code": process.returncode,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--case", action="append", default=[])
    parser.add_argument("--compiler-model", default="gpt-5.3-codex-spark")
    parser.add_argument("--reviewer-model", default="gpt-5.3-codex-spark")
    args = parser.parse_args()

    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    selected = [
        case
        for case in catalog["cases"]
        if not args.case or str(case["case_id"]) in set(args.case)
    ]
    if not selected:
        raise SystemExit("no cases selected")

    work_root = Path(tempfile.gettempdir()) / "solar-live-25-prompt-pipeline-20260826"
    work_root.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(
        {
            "PYTHONUTF8": "1",
            "HARNESS_DIR": str(HARNESS),
            "SOLAR_HARNESS_DIR": str(HARNESS),
            "SOLAR_INTENT_GATEWAY_DIR": str(work_root),
            "SOLAR_INTENT_COMPILER_PROVIDER": "codex",
            "SOLAR_INTENT_COMPILER_MODEL": args.compiler_model,
            "SOLAR_INTENT_REVIEWER_MODEL": args.reviewer_model,
            "SOLAR_INTENT_MODEL_TIMEOUT_SEC": "360",
        }
    )

    results: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = [pool.submit(_collect_case, case, work_root, env) for case in selected]
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())

    results.sort(key=lambda item: item["case_id"])
    observed_models: set[str] = set()
    for case in selected:
        receipt_path = STAGE2 / str(case["case_id"]) / "model_call_receipts.json"
        if not receipt_path.is_file():
            continue
        try:
            receipt_payload = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for call in receipt_payload.get("calls", []):
            model = str(call.get("model") or "").strip() if isinstance(call, dict) else ""
            if model:
                observed_models.add(model)
    summary = {
        "schema_version": "solar.live_compiler_pipeline_run.v1",
        "case_count": len(results),
        "accepted_count": sum(item.get("status") == "accepted" for item in results),
        "clarification_count": sum(
            item.get("status") == "needs_clarification" for item in results
        ),
        "terminal_count": sum(
            item.get("status") in {"accepted", "needs_clarification"} for item in results
        ),
        "ready_count": sum(bool(item.get("ready")) for item in results),
        "default_compiler_model_for_new_attempts": args.compiler_model,
        "default_reviewer_model_for_new_attempts": args.reviewer_model,
        "models_observed_in_case_receipts": sorted(observed_models),
        "cases": results,
    }
    _write_json(STAGE1 / "run_manifest.json", summary)
    _write_json(STAGE2 / "run_manifest.json", summary)
    _write_json(STAGE3 / "run_manifest.json", summary)
    print(json.dumps(summary, indent=2, ensure_ascii=False), flush=True)
    return 0 if summary["terminal_count"] == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
