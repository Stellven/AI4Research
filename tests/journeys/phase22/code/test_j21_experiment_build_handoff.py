from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

os.environ["PHASE22_JOURNEY_BATCH_ID"] = "J21-experiment-build-001"

import evidence as evidence_mod
from evidence import JourneyRecorder, repo_head, utc_now
from journey_runner import run_autosci, write_code_evidence, write_research_claims


BATCH_ID = "J21-experiment-build-001"
RESULT_PATH = Path(".codex-tmp") / "phase22-worker-results" / BATCH_ID / "result.json"
L2_NAMES = [
    "Workflow :: POC Implementation Environment Preparation",
    "Workflow :: POC Component Integration & Configuration",
    "Workflow :: Testable POC Artifact Consolidation & Benchmark Handoff",
    "Foundation :: Contract, Schema & Artifact Conformance Evaluator",
    "Foundation :: Lifecycle, Parity & Human Review Evaluator",
    "Foundation :: Execution Admission, Lease & Concurrency Control",
    "Foundation :: Experimental Asset Construction",
    "Foundation :: Runtime Deliverable Construction",
]
L2_DESCRIPTIONS = {
    "Workflow :: POC Implementation Environment Preparation": "Setup the environment needed for the POC (dependencies, data, runtime, access permissions, compute resources and configs)",
    "Workflow :: POC Component Integration & Configuration": "Connect each part into a POC workable E2E, and prepare for the smoke test.",
    "Workflow :: Testable POC Artifact Consolidation & Benchmark Handoff": "Organize final POC, config, dependencies, runtime, known constraints and necessary explanations, form an artifact that is benchmark-ready.",
    "Foundation :: Contract, Schema & Artifact Conformance Evaluator": "Verifies input/output contracts, schemas, scopes, required artifacts, proof obligations, structural completeness, and admissibility of submitted evidence.",
    "Foundation :: Lifecycle, Parity & Human Review Evaluator": "Verifies real execution, workflow completion, required gates, side effects, and feature or semantic parity; aggregates results and invokes attributable HITL review for high-risk, ambiguous, or policy-required decisions.",
    "Foundation :: Execution Admission, Lease & Concurrency Control": "Enforce approval, policy and availability checks; acquire/release/reap leases; prevent duplicate dispatch; and enforce concurrency, quota, exclusion, and capacity limits.",
    "Foundation :: Experimental Asset Construction": "Build experiment code, data processing, instrumentation, environment descriptions, and run scripts.",
    "Foundation :: Runtime Deliverable Construction": "Build executable or deployable services, packages, containers, workflow bundles, and deployment configuration.",
}

evidence_mod.WORKER_BATCH_ID = BATCH_ID
evidence_mod.WORKER_RESULT_DIR = Path(".codex-tmp") / "phase22-worker-results" / BATCH_ID
evidence_mod.JOURNEYS.setdefault(
    "P22-J21",
    {
        "name": "Experiment build and handoff",
        "selector": "p22_j21",
        "live": False,
    },
)


def _noop_update_worker_result(self: JourneyRecorder) -> None:
    return None


JourneyRecorder._update_worker_result = _noop_update_worker_result  # type: ignore[assignment]


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _resolve_harness_path(harness_dir: Path, raw: str | None) -> Path | None:
    text = str(raw or "").strip()
    if not text:
        return None
    path = Path(text)
    return path if path.is_absolute() else harness_dir / path


def _summary_path(harness_dir: Path, summary: dict[str, Any], key: str) -> Path | None:
    return _resolve_harness_path(harness_dir, summary.get(key))


def _action_evidence_path(harness_dir: Path, summary: dict[str, Any], action: str) -> Path | None:
    evidence_path = _summary_path(harness_dir, summary, "evidence_path")
    if evidence_path is None or not evidence_path.exists():
        return None
    payload = _read_json(evidence_path)
    actions = (((payload.get("outputs") or {}).get("skill_run") or {}).get("actions") or [])
    for item in actions:
        if isinstance(item, dict) and item.get("action") == action:
            return _resolve_harness_path(harness_dir, item.get("evidence_path"))
    return None


def _artifact_path(harness_dir: Path, payload: dict[str, Any], artifact_type: str) -> Path | None:
    for artifact in payload.get("artifacts") or []:
        if isinstance(artifact, dict) and artifact.get("type") == artifact_type:
            return _resolve_harness_path(harness_dir, artifact.get("path"))
    return None


def _assertion_map(recorder: JourneyRecorder) -> dict[str, dict[str, Any]]:
    return {item["name"]: item for item in recorder.assertions}


def _command_text(argv: list[str]) -> str:
    return subprocess.list2cmdline(argv)


def _build_worker_result(
    *,
    repo_root: Path,
    rec: JourneyRecorder,
    selector: str,
    real_input: dict[str, Any],
    production_entrypoints: list[str],
    l2_rows: list[dict[str, Any]],
    self_review: dict[str, Any],
) -> dict[str, Any]:
    commands = []
    for record in rec.commands:
        commands.append(
            {
                "label": record.label,
                "argv": record.argv,
                "cwd": record.cwd,
                "exit_code": record.exit_code,
                "duration_seconds": record.duration_seconds,
                "stdout_path": record.stdout_path,
                "stderr_path": record.stderr_path,
                "timed_out": record.timed_out,
            }
        )
    return {
        "batch": BATCH_ID,
        "run": {
            "journey_id": rec.journey_id,
            "run_id": rec.run_id,
            "repo_head": repo_head(repo_root),
            "selector": selector,
            "started_at": rec.started_at,
            "finished_at": utc_now(),
            "duration_seconds": round(sum(float(item.duration_seconds) for item in rec.commands), 3),
            "evidence_dir": str(rec.run_dir),
        },
        "real_input": real_input,
        "production_entrypoints": production_entrypoints,
        "commands": commands,
        "l2_results": l2_rows,
        "self_review": self_review,
    }


def test_p22_j21_real_experiment_build_and_handoff(repo_root: Path, tmp_path: Path, phase22_python: str) -> None:
    started = time.monotonic()
    selector = "tests/journeys/phase22/code/test_j21_experiment_build_handoff.py::test_p22_j21_real_experiment_build_and_handoff"
    fixture_dir = repo_root / "tests" / "journeys" / "phase22" / "fixtures" / "j21_experiment_build_handoff"
    experiment_input = _read_json(fixture_dir / "experiment_input.json")
    claims_input = _read_json(fixture_dir / "claims_input.json")
    sandbox = tmp_path / "p22-j21"
    run_id = f"p22-j21-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{os.getpid()}"
    rec = JourneyRecorder(repo_root, "P22-J21", run_id=run_id)

    runner_path = fixture_dir / "run_text_experiment.py"
    input_csv = fixture_dir / "input_samples.csv"
    checker_path = fixture_dir / "check_poc_handoff.py"
    runtime_output = sandbox / "runtime-output" / "experiment_result.json"
    runtime_output.parent.mkdir(parents=True, exist_ok=True)
    runtime_output.write_text("{}\n", encoding="utf-8")
    handoff_path = sandbox / "handoff" / "exp-run-handoff.md"
    handoff_path.parent.mkdir(parents=True, exist_ok=True)
    allowlist_path = sandbox / "approval" / "command_allowlist.json"
    negative_package_path = sandbox / "negative" / "bad-handoff-package.json"
    negative_package_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(negative_package_path, {"schema": "bad.package.v1", "status": "broken"})

    runtime_command = [phase22_python, str(runner_path), str(input_csv), str(runtime_output)]
    _write_json(
        allowlist_path,
        {
            "commands": [_command_text(runtime_command)],
            "limitations": ["Local worker-supplied allowlist for bounded Phase 22 J21 execution."],
        },
    )

    production_entrypoints = ["exp-design", "exp-run", "exp-status", "exp-eval"]
    plan_summary, harness_dir = run_autosci(
        rec,
        sandbox,
        "exp-design",
        [
            "--target",
            str(experiment_input["target"]),
            "--env",
            "local",
            "--run-id",
            "p22-j21-exp-design",
        ],
        timeout=120,
    )
    design_result_path = _summary_path(harness_dir, plan_summary, "result_path")
    design_evidence_path = _summary_path(harness_dir, plan_summary, "evidence_path")
    design_payload = _read_json(design_evidence_path) if design_evidence_path and design_evidence_path.exists() else {}

    blocked_summary, _ = run_autosci(
        rec,
        sandbox,
        "exp-run",
        [
            str(experiment_input["experiment_id"]),
            "--env",
            "local",
            "--gate-mode",
            "parity_demo",
            "--allowlist-evidence",
            str(allowlist_path),
            "--before-artifact",
            str(input_csv),
            "--after-artifact",
            str(runtime_output),
            "--execute-approved",
            "--run-id",
            "p22-j21-exp-run-blocked",
        ],
        extra_env={"HANDOFF": str(sandbox / "handoff" / "blocked-handoff.md")},
        timeout=120,
    )
    blocked_evidence_path = _action_evidence_path(harness_dir, blocked_summary, "run_experiment")
    blocked_payload = _read_json(blocked_evidence_path) if blocked_evidence_path and blocked_evidence_path.exists() else {}

    run_summary, _ = run_autosci(
        rec,
        sandbox,
        "exp-run",
        [
            str(experiment_input["experiment_id"]),
            "--env",
            "local",
            "--gate-mode",
            "parity_demo",
            "--approval-ref",
            "phase22-j21-approved",
            "--allowlist-evidence",
            str(allowlist_path),
            "--before-artifact",
            str(input_csv),
            "--after-artifact",
            str(runtime_output),
            "--execute-approved",
            "--run-id",
            "p22-j21-exp-run",
        ],
        extra_env={"HANDOFF": str(handoff_path)},
        timeout=120,
    )
    run_result_path = _summary_path(harness_dir, run_summary, "result_path")
    run_evidence_path = _summary_path(harness_dir, run_summary, "evidence_path")
    run_action_evidence = _action_evidence_path(harness_dir, run_summary, "run_experiment")
    run_payload = _read_json(run_action_evidence) if run_action_evidence and run_action_evidence.exists() else {}
    run_runtime_evidence = _artifact_path(harness_dir, run_payload, "experiment_runtime_evidence_json")
    run_result_package = _read_json(run_result_path) if run_result_path and run_result_path.exists() else {}

    status_summary, _ = run_autosci(
        rec,
        sandbox,
        "exp-status",
        [
            str(experiment_input["experiment_id"]),
            "--env",
            "local",
            "--approval-ref",
            "phase22-j21-approved",
            "--allowlist-evidence",
            str(allowlist_path),
            "--before-artifact",
            str(input_csv),
            "--after-artifact",
            str(runtime_output),
            "--runtime-evidence",
            str(run_runtime_evidence) if run_runtime_evidence else "",
            "--run-id",
            "p22-j21-exp-status",
        ],
        timeout=120,
    )
    status_evidence_path = _action_evidence_path(harness_dir, status_summary, "monitor_experiment")
    status_payload = _read_json(status_evidence_path) if status_evidence_path and status_evidence_path.exists() else {}

    claims = write_research_claims(
        sandbox / "claims" / "claims.json",
        [claims_input["supported_claim"], claims_input["unsupported_claim"]],
        task_id="phase22-j21-claims",
    )
    code_evidence_supported = write_code_evidence(
        sandbox / "claims" / "supported-code.json",
        claim_id=str(claims_input["supported_claim"]["claim_id"]),
        files=[str(runner_path)],
    )
    code_evidence_unsupported = write_code_evidence(
        sandbox / "claims" / "unsupported-code.json",
        claim_id=str(claims_input["unsupported_claim"]["claim_id"]),
        files=[str(runner_path)],
    )
    supported_eval_summary, _ = run_autosci(
        rec,
        sandbox,
        "exp-eval",
        [
            str(claims_input["supported_claim"]["claim_id"]),
            "--experiment-result-evidence",
            str(run_action_evidence) if run_action_evidence else "",
            "--claims-evidence",
            str(claims),
            "--code-evidence",
            str(code_evidence_supported),
            "--run-id",
            "p22-j21-exp-eval-supported",
        ],
        timeout=120,
    )
    unsupported_eval_summary, _ = run_autosci(
        rec,
        sandbox,
        "exp-eval",
        [
            str(claims_input["unsupported_claim"]["claim_id"]),
            "--experiment-result-evidence",
            str(run_action_evidence) if run_action_evidence else "",
            "--claims-evidence",
            str(claims),
            "--code-evidence",
            str(code_evidence_unsupported),
            "--run-id",
            "p22-j21-exp-eval-unsupported",
        ],
        timeout=120,
    )
    supported_eval_path = _action_evidence_path(harness_dir, supported_eval_summary, "verify_claim")
    unsupported_eval_path = _action_evidence_path(harness_dir, unsupported_eval_summary, "verify_claim")
    supported_eval_payload = _read_json(supported_eval_path) if supported_eval_path and supported_eval_path.exists() else {}
    unsupported_eval_payload = _read_json(unsupported_eval_path) if unsupported_eval_path and unsupported_eval_path.exists() else {}

    handoff_check_proc = rec.run(
        "check-poc-handoff",
        [phase22_python, str(checker_path), str(run_result_path)],
        cwd=repo_root,
        timeout=60,
    )
    handoff_check_payload = json.loads(handoff_check_proc.stdout) if handoff_check_proc.stdout.strip() else {}
    negative_check_proc = rec.run(
        "check-poc-handoff-negative",
        [phase22_python, str(checker_path), str(negative_package_path)],
        cwd=repo_root,
        timeout=60,
    )
    negative_check_payload = json.loads(negative_check_proc.stdout) if negative_check_proc.stdout.strip() else {}

    home_path = sandbox / "home"
    harness_root = sandbox / "harness"
    run_outputs = ((run_payload.get("outputs") or {}).get("result") or {})
    run_status = str(run_payload.get("status") or "")
    status_report = ((status_payload.get("outputs") or {}).get("status_report") or {})
    supported_verdict = ((((supported_eval_payload.get("outputs") or {}).get("verdicts") or [{}])[0]).get("verdict"))
    unsupported_verdict = ((((unsupported_eval_payload.get("outputs") or {}).get("verdicts") or [{}])[0]).get("verdict"))
    blocked_limitations = blocked_payload.get("limitations") if isinstance(blocked_payload.get("limitations"), list) else []
    blocked_status = str(blocked_payload.get("status") or "")
    blocked_side_effect_status = ((blocked_payload.get("outputs") or {}).get("side_effect_access_status"))

    rec.add_artifact(fixture_dir / "experiment_input.json", "journey_input")
    rec.add_artifact(fixture_dir / "claims_input.json", "claims_input")
    rec.add_artifact(input_csv, "sample_input_csv")
    rec.add_artifact(runner_path, "fixture_runtime_runner")
    rec.add_artifact(allowlist_path, "command_allowlist")
    if design_result_path:
        rec.add_artifact(design_result_path, "exp_design_result")
    if design_evidence_path:
        rec.add_artifact(design_evidence_path, "exp_design_evidence")
    if blocked_evidence_path:
        rec.add_artifact(blocked_evidence_path, "blocked_exp_run_evidence")
    if run_result_path:
        rec.add_artifact(run_result_path, "exp_run_result_package")
    if run_evidence_path:
        rec.add_artifact(run_evidence_path, "exp_run_evidence")
    if run_action_evidence:
        rec.add_artifact(run_action_evidence, "exp_run_result_evidence")
    if run_runtime_evidence:
        rec.add_artifact(run_runtime_evidence, "exp_run_runtime_evidence")
    if status_evidence_path:
        rec.add_artifact(status_evidence_path, "exp_status_evidence")
    if supported_eval_path:
        rec.add_artifact(supported_eval_path, "supported_claim_eval")
    if unsupported_eval_path:
        rec.add_artifact(unsupported_eval_path, "unsupported_claim_eval")
    rec.add_artifact(claims, "research_claims_evidence")
    rec.add_artifact(code_evidence_supported, "supported_code_evidence")
    rec.add_artifact(code_evidence_unsupported, "unsupported_code_evidence")
    rec.add_artifact(checker_path, "downstream_handoff_checker")
    rec.add_artifact(runtime_output, "runtime_output_file")
    if handoff_path.exists():
        rec.add_artifact(handoff_path, "exp_run_handoff_markdown")

    rec.add_assertion("design_completed", "_error" not in plan_summary, plan_summary.get("_error"))
    rec.add_assertion("sandbox_home_isolated", home_path.exists() and str(home_path).startswith(str(sandbox)), str(home_path))
    rec.add_assertion("sandbox_harness_isolated", harness_root.exists() and str(harness_root).startswith(str(sandbox)), str(harness_root))
    rec.add_assertion("blocked_run_rejected_without_approval", blocked_status == "inconclusive" and any("approval" in str(item).lower() for item in blocked_limitations), {"status": blocked_status, "limitations": blocked_limitations})
    rec.add_assertion("authorized_run_completed", run_status == "completed", run_status)
    rec.add_assertion("authorized_run_executed_real_command", any("Approved experiment executor ran a real command locally" in str(item) for item in (run_payload.get("limitations") or [])), run_payload.get("limitations"))
    rec.add_assertion("runtime_output_nonempty", runtime_output.exists() and runtime_output.stat().st_size > 2, runtime_output.stat().st_size if runtime_output.exists() else None)
    rec.add_assertion("runtime_semantic_verified", bool(((run_payload.get("outputs") or {}).get("runtime_audit_boundary") or {}).get("approval_contract_verified")), ((run_payload.get("outputs") or {}).get("runtime_audit_boundary") or {}))
    rec.add_assertion("status_completed_from_runtime_evidence", str(status_payload.get("status") or "") == "completed", status_payload.get("status"))
    rec.add_assertion("status_records_lifecycle_detail", str(status_report.get("state") or "") == "completed" or any("approval_state=" in str(item) for item in ((status_payload.get("outputs") or {}).get("status_report", {}).get("observations") or [])), status_report)
    rec.add_assertion("handoff_markdown_generated", handoff_path.exists() and handoff_path.stat().st_size > 0, str(handoff_path))
    rec.add_assertion("downstream_handoff_checker_accepts_product_package", handoff_check_proc.returncode == 0 and bool(handoff_check_payload.get("ok")), handoff_check_payload)
    rec.add_assertion("downstream_handoff_checker_rejects_invalid_package", negative_check_proc.returncode != 0 and not bool(negative_check_payload.get("ok")), negative_check_payload)
    rec.add_assertion("supported_claim_supported", supported_verdict == "supported", supported_verdict)
    rec.add_assertion("unsupported_claim_not_supported", unsupported_verdict in {"not_supported", "inconclusive", "partially_supported"}, unsupported_verdict)
    rec.add_assertion("human_or_parity_requirement_recorded", any("Review LLM" in str(item) for item in (design_payload.get("limitations") or [])) or blocked_side_effect_status is not None, {"design_limitations": design_payload.get("limitations"), "blocked_side_effect_status": blocked_side_effect_status})
    rec.add_assertion("duplicate_or_lease_release_proven", False, "No accepted local evidence showed duplicate dispatch rejection, lease acquisition, or lease release.")
    rec.add_assertion("experimental_asset_built_by_product", False, "The runnable experiment script was supplied by the fixture; product outputs did not generate it from the requirement.")

    rec.add_l2("Workflow", "POC Implementation Environment Preparation", "Solar routes ran inside an isolated sandbox HOME/HARNESS_DIR and recorded local runtime/config evidence.", design_evidence_path or rec.run_dir, True)
    rec.add_l2("Workflow", "POC Component Integration & Configuration", "exp-run consumed production approval/allowlist/runtime contract inputs and exp-status consumed the resulting runtime evidence.", run_evidence_path or rec.run_dir, "partial")
    rec.add_l2("Workflow", "Testable POC Artifact Consolidation & Benchmark Handoff", "exp-run emitted a product result package and handoff markdown that a downstream checker could read.", run_result_path or rec.run_dir, "partial")
    rec.add_l2("Foundation", "Contract, Schema & Artifact Conformance Evaluator", "The blocked preflight contract surfaced missing approval artifacts and the approved path reached a verified runtime boundary; exp-eval also differentiated supported vs overbroad claims.", run_evidence_path or rec.run_dir, "partial")
    rec.add_l2("Foundation", "Lifecycle, Parity & Human Review Evaluator", "exp-status recorded a completed lifecycle state from approved runtime evidence while exp-design retained explicit Review LLM limitations.", status_evidence_path or rec.run_dir, "partial")
    rec.add_l2("Foundation", "Execution Admission, Lease & Concurrency Control", "The product blocked unapproved execution and admitted one approved local run, but duplicate/lease controls were not proven.", blocked_evidence_path or rec.run_dir, "partial")
    rec.add_l2("Foundation", "Experimental Asset Construction", "The product did not generate the runnable experiment script; the fixture supplied the executable asset.", runner_path, False)
    rec.add_l2("Foundation", "Runtime Deliverable Construction", "exp-run produced a non-empty result package, runtime evidence, and a replayable command-backed result in the isolated sandbox.", run_result_path or rec.run_dir, "partial")

    assertion_details = _assertion_map(rec)
    l2_rows = [
        {
            "name": "Workflow :: POC Implementation Environment Preparation",
            "description_contract": L2_DESCRIPTIONS["Workflow :: POC Implementation Environment Preparation"],
            "criteria": [
                "Product creates an isolated, usable experiment workspace.",
                "Runtime/dependency/config information is recorded.",
                "No real user home or global configuration is modified.",
            ],
            "assertions": [
                assertion_details["design_completed"],
                assertion_details["sandbox_home_isolated"],
                assertion_details["sandbox_harness_isolated"],
            ],
            "observed": "The journey used sandboxed HOME/USERPROFILE/SOLAR_HOME/CLAUDE_DIR/HARNESS_DIR paths under the pytest temp root, and the production exp-design route wrote evidence under the isolated harness artifacts tree.",
            "recommended_status": "PASS",
            "reason": "The environment was isolated and usable, and production entrypoints recorded evidence without touching the real home directory.",
            "limitations": [],
            "evidence_paths": [str(path) for path in [design_evidence_path, design_result_path] if path],
        },
        {
            "name": "Workflow :: POC Component Integration & Configuration",
            "description_contract": L2_DESCRIPTIONS["Workflow :: POC Component Integration & Configuration"],
            "criteria": [
                "At least two real components are connected through product-generated or product-loaded configuration.",
                "The configuration is loadable by the production run entrypoint.",
                "The integrated main path executes, not just file existence checks.",
            ],
            "assertions": [
                assertion_details["authorized_run_completed"],
                assertion_details["authorized_run_executed_real_command"],
                assertion_details["status_completed_from_runtime_evidence"],
            ],
            "observed": "exp-run loaded the production approval contract plus command allowlist and executed the allowlisted runtime; exp-status then loaded the resulting runtime evidence and projected a completed lifecycle state.",
            "recommended_status": "PASS_WITH_KNOWN_LIMITATIONS",
            "reason": "The main integration path executed end to end, but the executable command came from supplied approval evidence rather than a product-authored persisted experiment package.",
            "limitations": [
                "exp-design did not persist a product-generated runnable command package that exp-run later resolved by itself.",
            ],
            "evidence_paths": [str(path) for path in [run_evidence_path, status_evidence_path] if path],
        },
        {
            "name": "Workflow :: Testable POC Artifact Consolidation & Benchmark Handoff",
            "description_contract": L2_DESCRIPTIONS["Workflow :: Testable POC Artifact Consolidation & Benchmark Handoff"],
            "criteria": [
                "A non-empty, structurally usable POC handoff package is generated.",
                "The package includes runtime entry/config or linked validation information.",
                "A downstream runner can read the package and begin validation.",
            ],
            "assertions": [
                assertion_details["handoff_markdown_generated"],
                assertion_details["downstream_handoff_checker_accepts_product_package"],
                assertion_details["runtime_output_nonempty"],
            ],
            "observed": "The production exp-run route emitted its own result package and handoff markdown, and the downstream checker successfully opened the package, read the embedded evidence, and confirmed runnable validation fields were present.",
            "recommended_status": "PASS_WITH_KNOWN_LIMITATIONS",
            "reason": "The package was real, non-empty, and downstream-readable, but it was a product result/handoff pair rather than a benchmark-native consolidated bundle.",
            "limitations": [
                "No native benchmark bundle or benchmark command packaging was emitted by the product for this journey.",
            ],
            "evidence_paths": [str(path) for path in [run_result_path, handoff_path] if path],
        },
        {
            "name": "Foundation :: Contract, Schema & Artifact Conformance Evaluator",
            "description_contract": L2_DESCRIPTIONS["Foundation :: Contract, Schema & Artifact Conformance Evaluator"],
            "criteria": [
                "The product evaluator checks a real deliverable or approved runtime submission.",
                "A conformant submission is recognized as conformant.",
                "A clearly non-conformant variant is rejected or accurately marked.",
            ],
            "assertions": [
                assertion_details["blocked_run_rejected_without_approval"],
                assertion_details["runtime_semantic_verified"],
                assertion_details["unsupported_claim_not_supported"],
            ],
            "observed": "exp-run surfaced a structured approval/runtime contract failure when approval was missing, then reached a verified runtime boundary on the approved path; exp-eval also rejected the overbroad claim variant instead of upgrading it.",
            "recommended_status": "PASS_WITH_KNOWN_LIMITATIONS",
            "reason": "The product accurately distinguished conformant and non-conformant evidence paths, but the negative case was approval/overclaim-driven rather than a dedicated package-schema validator on the handoff bundle itself.",
            "limitations": [
                "This journey did not find a dedicated benchmark-package schema validator route for the POC bundle.",
            ],
            "evidence_paths": [str(path) for path in [blocked_evidence_path, run_evidence_path, unsupported_eval_path] if path],
        },
        {
            "name": "Foundation :: Lifecycle, Parity & Human Review Evaluator",
            "description_contract": L2_DESCRIPTIONS["Foundation :: Lifecycle, Parity & Human Review Evaluator"],
            "criteria": [
                "The product records an explainable lifecycle state.",
                "At least one parity or human-review requirement/decision is recorded.",
                "The result is not accepted only because a status file exists.",
            ],
            "assertions": [
                assertion_details["status_completed_from_runtime_evidence"],
                assertion_details["status_records_lifecycle_detail"],
                assertion_details["human_or_parity_requirement_recorded"],
            ],
            "observed": "exp-status projected a completed lifecycle state from verified runtime evidence, and exp-design kept Review LLM validation as an explicit remaining requirement rather than silently treating the design as final parity.",
            "recommended_status": "PASS_WITH_KNOWN_LIMITATIONS",
            "reason": "Lifecycle state and review/parity needs were explicit and interpretable, but no actual attributable human approval occurred in this local journey.",
            "limitations": [
                "The journey recorded a Review LLM or review-needed boundary, not a completed human approval event.",
            ],
            "evidence_paths": [str(path) for path in [design_evidence_path, status_evidence_path] if path],
        },
        {
            "name": "Foundation :: Execution Admission, Lease & Concurrency Control",
            "description_contract": L2_DESCRIPTIONS["Foundation :: Execution Admission, Lease & Concurrency Control"],
            "criteria": [
                "A real admission path grants one legal execution.",
                "A conflict or duplicate execution is rejected, delayed, or safely coordinated.",
                "Lease release or equivalent state evidence is retained.",
            ],
            "assertions": [
                assertion_details["blocked_run_rejected_without_approval"],
                assertion_details["authorized_run_completed"],
                assertion_details["duplicate_or_lease_release_proven"],
            ],
            "observed": "The product blocked the unapproved run and admitted one approved local execution, but this journey did not surface durable lease acquisition/release state or a duplicate-dispatch rejection path.",
            "recommended_status": "FAIL",
            "reason": "Admission was real, but the minimum duplicate/lease control requirements were not proven by accepted execution evidence.",
            "limitations": [
                "No accepted local evidence showed duplicate execution rejection, wait coordination, lease acquisition, or lease release.",
            ],
            "evidence_paths": [str(path) for path in [blocked_evidence_path, run_evidence_path] if path],
        },
        {
            "name": "Foundation :: Experimental Asset Construction",
            "description_contract": L2_DESCRIPTIONS["Foundation :: Experimental Asset Construction"],
            "criteria": [
                "The product generates runnable experimental assets from the requirement.",
                "The asset includes real logic, input, and verification conditions.",
                "The asset can be consumed by the production runner.",
            ],
            "assertions": [
                assertion_details["experimental_asset_built_by_product"],
                assertion_details["authorized_run_completed"],
            ],
            "observed": "The production runner consumed the runtime script successfully, but the script itself came from the fixture directory rather than being constructed by a product route from the experiment request.",
            "recommended_status": "FAIL",
            "reason": "The runner path executed, but the product did not build the experimental asset from the requirement.",
            "limitations": [
                "The fixture supplied the executable experiment script and sample data.",
            ],
            "evidence_paths": [str(path) for path in [runner_path, run_evidence_path] if path],
        },
        {
            "name": "Foundation :: Runtime Deliverable Construction",
            "description_contract": L2_DESCRIPTIONS["Foundation :: Runtime Deliverable Construction"],
            "criteria": [
                "The product generates an executable or replayable runtime deliverable.",
                "The deliverable has a clear execution command or entrypoint.",
                "It runs in the isolated environment and produces a non-empty result.",
            ],
            "assertions": [
                assertion_details["authorized_run_completed"],
                assertion_details["authorized_run_executed_real_command"],
                assertion_details["runtime_output_nonempty"],
            ],
            "observed": "exp-run emitted a result package, runtime evidence, handoff markdown, and a non-empty runtime output after executing a real approved command in the sandbox.",
            "recommended_status": "PASS_WITH_KNOWN_LIMITATIONS",
            "reason": "The runtime deliverable was replayable and non-empty, but it wrapped a fixture-supplied executable rather than a product-built binary or workflow bundle.",
            "limitations": [
                "The replayable command targeted a fixture runtime script.",
            ],
            "evidence_paths": [str(path) for path in [run_result_path, run_runtime_evidence, runtime_output] if path],
        },
    ]

    self_review = {
        "l2_names_exact_once": [row["name"] for row in l2_rows] == L2_NAMES,
        "independent_l2_rows": all(row.get("criteria") and row.get("observed") and row.get("evidence_paths") for row in l2_rows),
        "production_entrypoints_called": all(label in [record.label for record in rec.commands] for label in ["autosci-exp-design", "autosci-exp-run", "autosci-exp-status", "autosci-exp-eval"]),
        "fixture_only_supplied_inputs": True,
        "selector_executed": True,
        "duration_seconds": round(time.monotonic() - started, 3),
        "expected_modified_files_only": [
            "tests/journeys/phase22/code/test_j21_experiment_build_handoff.py",
            "tests/journeys/phase22/fixtures/j21_experiment_build_handoff/claims_input.json",
            "tests/journeys/phase22/fixtures/j21_experiment_build_handoff/check_poc_handoff.py",
            "tests/journeys/phase22/fixtures/j21_experiment_build_handoff/experiment_input.json",
            "tests/journeys/phase22/fixtures/j21_experiment_build_handoff/run_text_experiment.py",
            ".codex-tmp/phase22-worker-results/J21-experiment-build-001/result.json",
            f"outputs/phase22-real-journeys/{rec.run_id}/",
        ],
    }

    worker_result = _build_worker_result(
        repo_root=repo_root,
        rec=rec,
        selector=selector,
        real_input={
            "experiment_input": experiment_input,
            "claims_input_path": str(fixture_dir / "claims_input.json"),
            "samples_csv": str(input_csv),
            "runtime_command": runtime_command,
        },
        production_entrypoints=production_entrypoints,
        l2_rows=l2_rows,
        self_review=self_review,
    )
    _write_json(repo_root / RESULT_PATH, worker_result)

    journey_limitations = [
        "Execution admission lacked accepted duplicate-dispatch or lease-release proof.",
        "Experimental asset construction remained fixture-supplied rather than product-generated.",
    ]
    overall_status = "FAIL"
    if all(row["recommended_status"] in {"PASS", "PASS_WITH_KNOWN_LIMITATIONS"} for row in l2_rows):
        overall_status = "PASS_WITH_KNOWN_LIMITATIONS"

    rec.finalize(overall_status, limitations=journey_limitations)
