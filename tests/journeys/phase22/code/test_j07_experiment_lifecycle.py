from __future__ import annotations

import json
from pathlib import Path

from evidence import JourneyRecorder
from journey_runner import (
    action_evidence,
    load_json,
    run_autosci,
    runtime_evidence,
    write_code_evidence,
    write_experiment_assets,
    write_research_claims,
)


def _recompute_metrics(payload: dict) -> dict:
    details = payload.get("details") or []
    metrics: dict[str, dict[str, float]] = {}
    for mode in ("baseline", "variant"):
        rows = [row for row in details if row.get("mode") == mode]
        if not rows:
            continue
        correct = sum(1 for row in rows if row.get("label") == row.get("prediction"))
        latencies = sorted(float(row.get("latency_ms", 0)) for row in rows)
        mid = len(latencies) // 2
        median = (latencies[mid] if len(latencies) % 2 else (latencies[mid - 1] + latencies[mid]) / 2) if latencies else 0
        metrics[mode] = {"accuracy": correct / len(rows), "median_latency_ms": median}
    if "baseline" in metrics and "variant" in metrics:
        metrics["accuracy_uplift"] = metrics["variant"]["accuracy"] - metrics["baseline"]["accuracy"]  # type: ignore[assignment]
    return metrics


def test_p22_j07_experiment_lifecycle(repo_root: Path, tmp_path: Path, phase22_python: str) -> None:
    rec = JourneyRecorder(repo_root, "P22-J07")
    sandbox = tmp_path / "p22-j07"
    assets = write_experiment_assets(sandbox / "experiment", phase22_python)
    plan, _ = run_autosci(
        rec,
        sandbox,
        "exp-design",
        ["--target", "normalization improves exact-match accuracy", "--run-id", "p22-j07-exp-design"],
        timeout=90,
    )
    plan_ev = action_evidence(plan, "design_experiment")
    experiment_proc = rec.run(
        "local-python-experiment",
        [phase22_python, str(assets["runner"]), str(assets["data"]), str(assets["result"])],
        cwd=repo_root,
        timeout=60,
    )
    result_payload = json.loads(assets["result"].read_text(encoding="utf-8")) if assets["result"].exists() else {}
    runtime_path = runtime_evidence(sandbox / "experiment" / "runtime-evidence.json", experiment_proc.args, assets["result"], result_payload)
    exp_run, _ = run_autosci(
        rec,
        sandbox,
        "exp-run",
        [
            "phase22-j07-local",
            "--review",
            "--env",
            "local",
            "--approval-ref",
            "phase22-local-approval",
            "--allowlist-evidence",
            str(assets["allowlist"]),
            "--runtime-evidence",
            str(runtime_path),
            "--before-artifact",
            str(assets["data"]),
            "--after-artifact",
            str(assets["result"]),
            "--run-id",
            "p22-j07-exp-run",
        ],
        timeout=90,
    )
    exp_result_ev = action_evidence(exp_run, "run_experiment")
    status_summary, _ = run_autosci(
        rec,
        sandbox,
        "exp-status",
        [
            "phase22-j07-local",
            "--env",
            "local",
            "--collect",
            "--runtime-evidence",
            str(runtime_path),
            "--after-artifact",
            str(assets["result"]),
            "--run-id",
            "p22-j07-exp-status",
        ],
        timeout=90,
    )
    exp_status_ev = action_evidence(status_summary, "monitor_experiment")
    claims = write_research_claims(
        sandbox / "claims.json",
        [
            {
                "claim_id": "claim-j07-threshold",
                "text": "The normalization variant improves exact-match accuracy by at least 20 percentage points on the local dataset.",
                "source_anchor": "phase22-local-experiment#results",
                "testability": "testable",
                "verification_status": "unverified",
                "evidence_ids": ["claim:phase22-j07-threshold"],
            }
        ],
        task_id="phase22-j07-claims",
    )
    code_ev = write_code_evidence(sandbox / "code-evidence.json", claim_id="claim-j07-threshold", files=[str(assets["runner"])])
    eval_summary, _ = run_autosci(
        rec,
        sandbox,
        "exp-eval",
        [
            "claim-j07-threshold",
            "--experiment-result-evidence",
            str(exp_result_ev),
            "--claims-evidence",
            str(claims),
            "--code-evidence",
            str(code_ev),
            "--run-id",
            "p22-j07-exp-eval",
        ],
        timeout=90,
    )
    exp_eval_ev = action_evidence(eval_summary, "verify_claim")
    if exp_result_ev:
        rec.add_artifact(exp_result_ev, "autosci_experiment_result")
    if exp_status_ev:
        rec.add_artifact(exp_status_ev, "autosci_experiment_status")
    if exp_eval_ev:
        rec.add_artifact(exp_eval_ev, "autosci_experiment_eval")
    rec.add_artifact(claims, "schema_valid_research_claims")
    rec.add_artifact(code_ev, "code_evidence")
    rec.add_artifact(assets["result"], "raw_local_experiment_result")
    rec.add_artifact(runtime_path, "runtime_evidence")
    recomputed = _recompute_metrics(result_payload)
    expected_uplift = recomputed.get("accuracy_uplift")
    status_payload = load_json(exp_status_ev) if exp_status_ev else {}
    status_report = status_payload.get("outputs", {}).get("status_report", {})
    terminal_state = status_report.get("state")
    eval_payload = load_json(exp_eval_ev) if exp_eval_ev else {}
    eval_verdict = eval_payload.get("outputs", {}).get("verdicts", [{}])[0].get("verdict")
    plan_payload = load_json(plan_ev) if plan_ev else {}
    plan_outputs = plan_payload.get("outputs", {}) if isinstance(plan_payload.get("outputs"), dict) else {}
    experiment_plan = plan_outputs.get("experiment_plan", {}) if isinstance(plan_outputs.get("experiment_plan"), dict) else {}
    poc_design_ready = bool(experiment_plan.get("command_allowlist")) and bool(experiment_plan.get("expected_artifacts")) and bool(experiment_plan.get("success_criteria"))
    rec.add_assertion("exp_design_completed", not plan.get("_error"), plan.get("_error"))
    rec.add_assertion("local_subprocess_exit_zero", experiment_proc.returncode == 0, experiment_proc.returncode)
    rec.add_assertion(
        "raw_metrics_recomputed_from_samples",
        isinstance(expected_uplift, (int, float))
        and abs(float(expected_uplift) - float(result_payload.get("accuracy_uplift", -999))) < 1e-9,
        {"reported": result_payload.get("accuracy_uplift"), "recomputed": recomputed},
    )
    rec.add_assertion("accuracy_uplift_at_least_20pp", result_payload.get("accuracy_uplift", 0) >= 0.2, result_payload)
    rec.add_assertion("variant_latency_under_20ms", result_payload.get("variant", {}).get("median_latency_ms", 999) < 20, result_payload)
    rec.add_assertion("autosci_exp_run_completed", exp_result_ev is not None, exp_run.get("_error"))
    rec.add_assertion("autosci_exp_status_completed", exp_status_ev is not None, status_summary.get("_error"))
    rec.add_assertion(
        "exp_status_reached_terminal_state",
        terminal_state in {"completed", "failed"},
        status_report or status_summary.get("_error"),
    )
    rec.add_assertion("autosci_exp_eval_completed", exp_eval_ev is not None, eval_summary.get("_error"))
    rec.add_assertion("exp_eval_verdict_matches_declared_threshold", eval_verdict == "supported", eval_verdict)
    rec.add_l2(
        "Workflow",
        "Verification-Ready POC Design",
        "AutoSci exp-design generated command allowlist, expected artifacts, and success criteria for the local POC path",
        Path(plan_ev or plan.get("evidence_path", rec.run_dir)),
        "partial" if poc_design_ready else False,
    )
    rec.add_l2("Foundation", "Runtime Control Loop & Run Lifecycle Management", "real local Python subprocess produced runtime evidence consumed by exp-run", runtime_path, True)
    rec.add_l2("Workflow", "Experiment Status & Evaluation", "exp-status and exp-eval were invoked against the local experiment evidence", exp_status_ev or rec.run_dir, "partial")
    core_assertions = {
        "exp_design_completed",
        "local_subprocess_exit_zero",
        "raw_metrics_recomputed_from_samples",
        "accuracy_uplift_at_least_20pp",
        "variant_latency_under_20ms",
        "autosci_exp_run_completed",
    }
    core_passed = all(item["passed"] for item in rec.assertions if item["name"] in core_assertions)
    limitations = []
    if not all(item["passed"] for item in rec.assertions):
        failed = [item["name"] for item in rec.assertions if not item["passed"]]
        if core_passed:
            limitations.append(f"Core local experiment completed, but lifecycle status/eval/audit checks remain incomplete: {failed}.")
    status = "PASS" if all(item["passed"] for item in rec.assertions) else "PASS_WITH_KNOWN_LIMITATIONS" if core_passed else "FAIL"
    rec.finalize(status, limitations=limitations)
