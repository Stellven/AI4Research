#!/usr/bin/env python3
"""Run the corrected AutoSci literature E2E chain through Solar Harness.

This script is only an orchestrator: every AutoSci action is executed through
`harness/solar-harness.sh autosci '$skill ...'`.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[6]
HARNESS_ROOT = REPO_ROOT / "harness"
OLD_ROOT_REL = "artifacts/autosci/runs/e2e-doc-literature-20260707"
NEW_ROOT_REL = "artifacts/autosci/runs/e2e-doc-literature-20260707-idea-chain"
BATCH_NAME = os.environ.get("AUTOSCI_BATCH_NAME", "corrected_batch")
BATCH_ROOT_REL = f"{NEW_ROOT_REL}/{BATCH_NAME}"
BATCH_ROOT = HARNESS_ROOT / BATCH_ROOT_REL
LOG_ROOT = BATCH_ROOT / "logs"
APPROVAL_REF = "user-request-autosci-e2e-20260707-idea-chain"
GATE_MODE = os.environ.get("AUTOSCI_GATE_MODE", "")
MODEL_COMMAND = (
    "env AUTOSCI_OLLAMA_MODEL=gemma3:4b AUTOSCI_OLLAMA_TIMEOUT=180 "
    f"python3 {NEW_ROOT_REL}/tools/ollama_autosci_model_command.py"
)
REVIEW_COMMAND = (
    "env AUTOSCI_OLLAMA_MODEL=gemma3:4b AUTOSCI_OLLAMA_TIMEOUT=180 "
    f"python3 {NEW_ROOT_REL}/tools/ollama_artifact_review_command.py"
)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def item_sort_key(item_id: str) -> tuple[int, int, str]:
    prefixes = {"cc": 0, "cu": 1, "ghc": 2, "r": 3}
    match = re.match(r"([a-z]+)-?(\d+)$", item_id)
    if not match:
        return (99, 0, item_id)
    prefix, number = match.groups()
    return (prefixes.get(prefix, 50), int(number), item_id)


def discover_items() -> list[str]:
    source_dir = HARNESS_ROOT / OLD_ROOT_REL / "sources"
    return sorted((path.stem for path in source_dir.glob("*.md")), key=item_sort_key)


def rel_to_repo(harness_rel: str) -> Path:
    return HARNESS_ROOT / harness_rel


def run_autosci(step: str, item_id: str, autosci_command: str, *, timeout: int) -> dict[str, Any]:
    LOG_ROOT.mkdir(parents=True, exist_ok=True)
    stdout_path = LOG_ROOT / f"{item_id}.{step}.stdout.txt"
    stderr_path = LOG_ROOT / f"{item_id}.{step}.stderr.txt"
    status_path = LOG_ROOT / f"{item_id}.{step}.status.json"
    env = os.environ.copy()
    env["HARNESS_DIR"] = str(HARNESS_ROOT)
    start = time.time()
    print(f"[{now_iso()}] {item_id} {step} start", flush=True)
    proc = subprocess.run(
        ["bash", "harness/solar-harness.sh", "autosci", autosci_command],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    elapsed = round(time.time() - start, 3)
    stdout_path.write_text(proc.stdout, encoding="utf-8")
    stderr_path.write_text(proc.stderr, encoding="utf-8")
    status = {
        "item_id": item_id,
        "step": step,
        "command": autosci_command,
        "returncode": proc.returncode,
        "elapsed_seconds": elapsed,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "timestamp": now_iso(),
    }
    try:
        status["stdout_json"] = json.loads(proc.stdout)
    except json.JSONDecodeError:
        status["stdout_json"] = None
    write_json(status_path, status)
    print(f"[{now_iso()}] {item_id} {step} done rc={proc.returncode} elapsed={elapsed}s", flush=True)
    return status


def assert_file(path: Path, label: str) -> None:
    if not path.exists():
        raise RuntimeError(f"missing {label}: {path}")


def make_novelty_evidence(item_id: str, meta: dict[str, Any], novelty_rel: str) -> None:
    title = str(meta.get("title") or item_id)
    doc = str(meta.get("doc") or "attached HTML document")
    payload = {
        "schema": "external_novelty_sources.v1",
        "status": "completed",
        "inputs": {
            "query": f"{title} literature-validation-{item_id}",
            "source_mode": "attached_document_source_record",
            "live_url_verification": False,
        },
        "outputs": {
            "sources": [
                {
                    "id": f"attached:{item_id}",
                    "provider": "attached_html_source_record",
                    "title": title,
                    "summary": str(meta.get("summary") or meta.get("note") or title),
                    "source_type": str(meta.get("source_type") or "attached source record"),
                    "source_document": doc,
                    "url_status": str(meta.get("url_status") or "unknown"),
                    "credibility_score": meta.get("credibility"),
                    "relevance_score": meta.get("relevance"),
                    "confidence": str(meta.get("confidence") or "unknown"),
                }
            ]
        },
        "provenance": {
            "operator_id": "codex-corrected-batch-source-record",
            "implementation_package": "run-artifact",
            "timestamp": now_iso(),
        },
        "limitations": [
            "This is supplied novelty/source evidence from the attached HTML-derived source record, not live URL or external provider verification."
        ],
    }
    write_json(rel_to_repo(novelty_rel), payload)


def selected_idea_id(item_id: str, ideate_rel: str) -> str:
    evaluation_path = rel_to_repo(f"{ideate_rel}/idea_evaluation.json")
    assert_file(evaluation_path, "idea evaluation")
    payload = load_json(evaluation_path)
    evaluations = ((payload.get("outputs") or {}).get("evaluations") or [])
    candidates: list[dict[str, Any]] = [item for item in evaluations if isinstance(item, dict)]
    ready = [
        item
        for item in candidates
        if ((item.get("final_acceptance_boundary") or {}).get("final_acceptance_ready") is True)
    ]
    pool = ready or candidates
    if not pool:
        raise RuntimeError(f"{item_id} ideate produced no idea evaluations")
    for item in pool:
        idea_id = str(item.get("idea_id") or "")
        if item_id in idea_id:
            return idea_id
    idea_id = str(pool[0].get("idea_id") or "")
    if not idea_id:
        raise RuntimeError(f"{item_id} first idea evaluation has no idea_id")
    return idea_id


def make_allowlist(item_id: str, idea_id: str, experiment_id: str, allowlist_rel: str) -> str:
    metadata_rel = f"{OLD_ROOT_REL}/metadata/{item_id}.json"
    source_rel = f"{OLD_ROOT_REL}/sources/{item_id}.md"
    command = (
        f"python3 {OLD_ROOT_REL}/tools/validate_literature_item.py "
        f"--metadata {metadata_rel} --source {source_rel} "
        f"--experiment-id {experiment_id} --claim-id {idea_id}"
    )
    payload = {
        "schema": "autosci_command_allowlist.v1",
        "source_id": item_id,
        "idea_id": idea_id,
        "purpose": f"Bounded local validation command for promoted AutoSci idea {idea_id}.",
        "commands": [command],
        "limitations": [
            "No network, email, remote execution, destructive mutation, or credential access is allowed by this allowlist."
        ],
    }
    write_json(rel_to_repo(allowlist_rel), payload)
    return command


def make_idea_claims(item_id: str, idea_id: str, source_rel: str, claims_rel: str, meta: dict[str, Any]) -> None:
    payload = {
        "schema": "research_claims.v1",
        "status": "completed",
        "inputs": {"paper_path": source_rel, "target": idea_id},
        "outputs": {
            "claims": [
                {
                    "claim_id": idea_id,
                    "claim_type": "result",
                    "text": (
                        f"Promoted AutoSci idea `{idea_id}` for literature item `{item_id}` can be evaluated "
                        "by the approved local attached-source validation experiment."
                    ),
                    "source_anchor": f"{item_id}.md#evidence-record",
                    "testability": "testable",
                    "verification_status": "unverified",
                    "evidence_ids": [
                        f"paper-{item_id}",
                        source_rel,
                        f"literature-source:{item_id}",
                        f"attached-doc:{meta.get('doc_slug')}",
                    ],
                }
            ]
        },
        "provenance": {
            "operator_id": "codex-corrected-batch-claim-linker",
            "implementation_package": "run-artifact",
            "timestamp": now_iso(),
        },
        "limitations": [
            "Claim evidence links the promoted idea to the attached source record for local validation; it is not external URL verification."
        ],
    }
    write_json(rel_to_repo(claims_rel), payload)


def make_code_evidence(
    item_id: str,
    idea_id: str,
    experiment_id: str,
    command_run: str,
    code_rel: str,
    runtime_rel: str,
) -> None:
    payload = {
        "schema": "code_evidence_map.v1",
        "task_id": f"task-{item_id}-{idea_id}-code-evidence-map",
        "sprint_id": "e2e-doc-literature-20260707-idea-chain-corrected",
        "node_id": "node-code-evidence-map",
        "status": "completed",
        "inputs": {"claim_id": idea_id, "experiment_id": experiment_id},
        "outputs": {
            "mappings": [
                {
                    "mapping_id": f"map-{idea_id}",
                    "claim_id": idea_id,
                    "repo_or_path": OLD_ROOT_REL,
                    "files": [
                        f"{OLD_ROOT_REL}/tools/validate_literature_item.py",
                        runtime_rel,
                    ],
                    "execution_entrypoint": command_run,
                    "mapping_status": "mapped",
                    "relevance_label": "direct",
                    "relevance_reason": "The allowlisted validator command produced the experiment runtime evidence used for this idea verdict.",
                    "evidence_ids": [idea_id, experiment_id, runtime_rel],
                }
            ]
        },
        "artifacts": [{"type": "code_evidence_map", "path": code_rel}],
        "provenance": {
            "operator_id": "codex-corrected-batch-code-linker",
            "implementation_package": "run-artifact",
            "timestamp": now_iso(),
        },
        "limitations": [
            "Code evidence is limited to the approved local validator and runtime evidence for the attached-source experiment."
        ],
    }
    write_json(rel_to_repo(code_rel), payload)


def summarize_item(item_id: str, corrected_rel: str, statuses: list[dict[str, Any]], meta: dict[str, Any]) -> dict[str, Any]:
    experiment_rel = f"{corrected_rel}/experiment"
    status_rel = f"{corrected_rel}/status"
    summary: dict[str, Any] = {
        "item_id": item_id,
        "title": meta.get("title"),
        "doc_slug": meta.get("doc_slug"),
        "expected_outcome": meta.get("expected_outcome"),
        "steps": {status["step"]: status["returncode"] for status in statuses},
        "status": "completed",
        "artifacts": {
            "ingest": f"{corrected_rel}/ingest/autosci_skill_run.json",
            "research": f"{corrected_rel}/research/autosci_skill_run.json",
            "review": f"{corrected_rel}/review/artifact_review.json",
            "ideate": f"{corrected_rel}/ideate/ideate_pipeline_report.json",
            "exp_design": f"{experiment_rel}/experiment_plan.json",
            "exp_run": f"{experiment_rel}/experiment_result.json",
            "exp_eval": f"{experiment_rel}/claim_verdict.json",
            "exp_status": f"{status_rel}/experiment_status.json",
        },
    }
    try:
        boundary = load_json(rel_to_repo(f"{corrected_rel}/ideate/ideate_final_promotion_boundary.json"))
        summary["ideate_final_promotion_ready"] = boundary.get("final_promotion_ready")
        summary["ideate_boundary_status"] = boundary.get("status")
    except (OSError, json.JSONDecodeError):
        summary["ideate_final_promotion_ready"] = False
    try:
        result = load_json(rel_to_repo(f"{experiment_rel}/experiment_result.json"))
        result_outputs = result.get("outputs") or {}
        run_result = result_outputs.get("result") or {}
        summary["experiment_outcome"] = run_result.get("outcome")
        summary["experiment_exit_code"] = run_result.get("exit_code")
        summary["experiment_id"] = run_result.get("experiment_id")
    except (OSError, json.JSONDecodeError):
        summary["experiment_outcome"] = "missing"
    try:
        verdict = load_json(rel_to_repo(f"{experiment_rel}/claim_verdict.json"))
        first = ((verdict.get("outputs") or {}).get("verdicts") or [{}])[0]
        boundary = first.get("final_verdict_boundary") or {}
        summary["claim_id"] = first.get("claim_id")
        summary["verdict"] = first.get("verdict")
        summary["evidence_outcome"] = first.get("evidence_outcome")
        summary["final_verdict_ready"] = first.get("final_verdict_ready")
        summary["final_verdict_boundary_status"] = boundary.get("status")
        summary["final_verdict_limitations"] = boundary.get("limitations") or []
    except (OSError, json.JSONDecodeError, IndexError):
        summary["verdict"] = "missing"
        summary["final_verdict_ready"] = False
    return summary


def run_item(item_id: str, *, timeout: int) -> dict[str, Any]:
    metadata_rel = f"{OLD_ROOT_REL}/metadata/{item_id}.json"
    source_rel = f"{OLD_ROOT_REL}/sources/{item_id}.md"
    meta = load_json(rel_to_repo(metadata_rel))
    corrected_rel = f"{BATCH_ROOT_REL}/items/{item_id}"
    ingest_rel = f"{corrected_rel}/ingest"
    research_rel = f"{corrected_rel}/research"
    review_rel = f"{corrected_rel}/review"
    novelty_rel = f"{corrected_rel}/novelty/attached_external_novelty_sources.json"
    ideate_rel = f"{corrected_rel}/ideate"
    experiment_rel = f"{corrected_rel}/experiment"
    status_rel = f"{corrected_rel}/status"

    statuses: list[dict[str, Any]] = []
    make_novelty_evidence(item_id, meta, novelty_rel)
    gate = f" --gate-mode {GATE_MODE}" if GATE_MODE else ""

    commands = [
        (
            "ingest",
            f"$ingest --paper {source_rel} --topic literature-validation-{item_id} "
            f"{gate} --work-dir {ingest_rel} --run-id e2e-lit-{item_id}-{BATCH_NAME}-ingest",
        ),
        (
            "research",
            f"$research --paper {source_rel} --topic literature-validation-{item_id} --scheduler-run "
            f"--scheduler-timeout 30{gate} --work-dir {research_rel} "
            f"--run-id e2e-lit-{item_id}-{BATCH_NAME}-research",
        ),
        (
            "review",
            f"$review literature-validation-{item_id} --paper {source_rel} --review --difficulty standard "
            f'--focus evidence --review-llm-command "{REVIEW_COMMAND}" '
            f"{gate} --work-dir {review_rel} --run-id e2e-lit-{item_id}-{BATCH_NAME}-review",
        ),
        (
            "ideate",
            f"$ideate --paper {source_rel} --topic literature-validation-{item_id} "
            f'--model-command "{MODEL_COMMAND}" --novelty-evidence {novelty_rel} '
            f"--review-llm-evidence {review_rel}/artifact_review.json --write "
            f"--approval-ref {APPROVAL_REF} --execute-approved --skip-pilot --max-ideas 5 "
            f"{gate} --work-dir {ideate_rel} --run-id e2e-lit-{item_id}-{BATCH_NAME}-ideate",
        ),
    ]
    for step, command in commands:
        status = run_autosci(step, item_id, command, timeout=timeout)
        statuses.append(status)
        if status["returncode"] != 0:
            raise RuntimeError(f"{item_id} {step} failed with return code {status['returncode']}")

    idea_id = selected_idea_id(item_id, ideate_rel)
    experiment_id = f"exp-{idea_id}"
    allowlist_rel = f"{experiment_rel}/{idea_id}.allowlist.json"
    command_run = make_allowlist(item_id, idea_id, experiment_id, allowlist_rel)

    exp_design = (
        f"$exp-design --paper {source_rel} --target {idea_id} --topic literature-validation-{item_id} "
        f"--review-llm-evidence {review_rel}/artifact_review.json "
        f"{gate} --work-dir {experiment_rel} --run-id e2e-lit-{item_id}-{BATCH_NAME}-exp-design"
    )
    status = run_autosci("exp_design", item_id, exp_design, timeout=timeout)
    statuses.append(status)
    if status["returncode"] != 0:
        raise RuntimeError(f"{item_id} exp-design failed with return code {status['returncode']}")

    exp_run = (
        f"$exp-run --paper {source_rel} --target {idea_id} --env local "
        f"--approval-ref {APPROVAL_REF} --allowlist-evidence {allowlist_rel} "
        f"--before-artifact {source_rel} --execute-approved "
        f"{gate} --work-dir {experiment_rel} --run-id e2e-lit-{item_id}-{BATCH_NAME}-exp-run"
    )
    status = run_autosci("exp_run", item_id, exp_run, timeout=timeout)
    statuses.append(status)
    if status["returncode"] != 0:
        raise RuntimeError(f"{item_id} exp-run failed with return code {status['returncode']}")

    runtime_rel = f"{experiment_rel}/run_experiment_runtime_evidence.json"
    assert_file(rel_to_repo(runtime_rel), "run experiment runtime evidence")
    claims_rel = f"{experiment_rel}/idea_claims.json"
    code_rel = f"{experiment_rel}/code_evidence_map.json"
    make_idea_claims(item_id, idea_id, source_rel, claims_rel, meta)
    make_code_evidence(item_id, idea_id, experiment_id, command_run, code_rel, runtime_rel)

    exp_eval = (
        f"$exp-eval --paper {source_rel} --target {idea_id} "
        f"--claims-evidence {claims_rel} --code-evidence {code_rel} "
        f"--experiment-result-evidence {experiment_rel}/experiment_result.json "
        f"--review-llm-evidence {review_rel}/artifact_review.json --write "
        f"--approval-ref {APPROVAL_REF} --execute-approved "
        f"{gate} --work-dir {experiment_rel} --run-id e2e-lit-{item_id}-{BATCH_NAME}-exp-eval"
    )
    status = run_autosci("exp_eval", item_id, exp_eval, timeout=timeout)
    statuses.append(status)
    if status["returncode"] != 0:
        raise RuntimeError(f"{item_id} exp-eval failed with return code {status['returncode']}")

    exp_status = (
        f"$exp-status --paper {source_rel} --target {idea_id} "
        f"--experiment-result-evidence {experiment_rel}/experiment_result.json "
        f"{gate} --work-dir {status_rel} --run-id e2e-lit-{item_id}-{BATCH_NAME}-exp-status"
    )
    status = run_autosci("exp_status", item_id, exp_status, timeout=timeout)
    statuses.append(status)
    if status["returncode"] != 0:
        raise RuntimeError(f"{item_id} exp-status failed with return code {status['returncode']}")

    summary = summarize_item(item_id, corrected_rel, statuses, meta)
    write_json(rel_to_repo(f"{corrected_rel}/batch_item_summary.json"), summary)
    return summary


def write_batch_status(items: list[dict[str, Any]], failures: list[dict[str, Any]]) -> None:
    verdict_counts: dict[str, int] = {}
    outcome_counts: dict[str, int] = {}
    final_ready_count = 0
    for item in items:
        verdict = str(item.get("verdict") or "missing")
        verdict_counts[verdict] = verdict_counts.get(verdict, 0) + 1
        outcome = str(item.get("experiment_outcome") or "missing")
        outcome_counts[outcome] = outcome_counts.get(outcome, 0) + 1
        if item.get("final_verdict_ready") is True:
            final_ready_count += 1
    payload = {
        "schema": "corrected_autosci_idea_chain_batch.v1",
        "batch_name": BATCH_NAME,
        "gate_mode": GATE_MODE or "default",
        "status": "completed" if not failures else "failed",
        "root": BATCH_ROOT_REL,
        "item_count": len(items) + len(failures),
        "completed_count": len(items),
        "failed_count": len(failures),
        "failed_ids": [failure["item_id"] for failure in failures],
        "final_verdict_ready_count": final_ready_count,
        "verdict_counts": verdict_counts,
        "experiment_outcome_counts": outcome_counts,
        "items": items,
        "failures": failures,
        "timestamp": now_iso(),
    }
    write_json(BATCH_ROOT / "batch_status.json", payload)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ids", help="Comma-separated item ids to run")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--timeout", type=int, default=360)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    BATCH_ROOT.mkdir(parents=True, exist_ok=True)
    item_ids = [item.strip() for item in args.ids.split(",") if item.strip()] if args.ids else discover_items()
    if args.limit:
        item_ids = item_ids[: args.limit]
    completed: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    for index, item_id in enumerate(item_ids, start=1):
        summary_path = BATCH_ROOT / "items" / item_id / "batch_item_summary.json"
        if args.resume and summary_path.exists():
            try:
                existing_summary = load_json(summary_path)
                all_steps_ok = all(code == 0 for code in (existing_summary.get("steps") or {}).values())
                if existing_summary.get("ideate_final_promotion_ready") is True and all_steps_ok:
                    completed.append(existing_summary)
                    write_batch_status(completed, failures)
                    print(f"[{now_iso()}] {item_id} resume-skip ({index}/{len(item_ids)})", flush=True)
                    continue
                print(f"[{now_iso()}] {item_id} resume-rerun: incomplete existing summary", flush=True)
            except (OSError, json.JSONDecodeError):
                pass
        try:
            print(f"[{now_iso()}] item {index}/{len(item_ids)} {item_id} begin", flush=True)
            completed.append(run_item(item_id, timeout=args.timeout))
            print(f"[{now_iso()}] item {index}/{len(item_ids)} {item_id} completed", flush=True)
        except Exception as exc:  # noqa: BLE001
            failure = {"item_id": item_id, "error": str(exc), "timestamp": now_iso()}
            failures.append(failure)
            print(f"[{now_iso()}] item {index}/{len(item_ids)} {item_id} failed: {exc}", flush=True)
        write_batch_status(completed, failures)

    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
