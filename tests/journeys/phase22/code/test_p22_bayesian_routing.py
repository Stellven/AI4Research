import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def test_p22_bounded_bayesian_routing(repo_root: Path, tmp_path: Path) -> None:
    run_id = "p22-bayesian-routing-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = repo_root / "outputs" / "phase22-real-journeys" / run_id
    output.mkdir(parents=True)
    arms = {
        "base": ({"quality": .2, "speed": .2}, .60, .30, 900),
        "balanced": ({"quality": .7, "speed": .8}, .82, .18, 550),
        "premium": ({"quality": 1.0, "speed": .4}, .88, .80, 450),
    }
    rows = []
    for arm, (config, reward, cost, latency) in arms.items():
        for index in range(3):
            rows.append({"split": "train", "context_id": f"train-{arm}-{index}", "arm": arm, "config": config, "reward": reward + index * .001, "cost_usd": cost, "latency_ms": latency, "success": True})
    for index in range(3):
        for arm, (config, reward, cost, latency) in arms.items():
            rows.append({"split": "holdout", "context_id": f"holdout-{index}", "arm": arm, "config": config, "reward": reward, "cost_usd": cost, "latency_ms": latency, "success": True})
    traces = output / "routing-traces.jsonl"
    traces.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    result_path = output / "bayesian-routing-evaluation.json"
    tool = repo_root / "harness" / "lib" / "routing_bayesian.py"
    command = [sys.executable, str(tool), "evaluate", "--traces", str(traces), "--baseline-arm", "base", "--cost-weight", "1", "--latency-weight", ".1", "--max-mean-cost-usd", ".5", "--beta", ".2", "--max-selected-uncertainty", ".25", "--output", str(result_path)]
    process = subprocess.run(command, text=True, capture_output=True, timeout=30)
    result = json.loads(result_path.read_text(encoding="utf-8"))
    selected = result.get("policy", {}).get("selected_arm")
    assertions = {
        "production_cli_accepted": process.returncode == 0 and result["status"] == "accepted",
        "real_gp_ucb_surrogate": result["algorithm"] == "bounded_gaussian_process_ucb" and result["surrogate"]["kernel"] == "rbf",
        "cost_bounded_candidate_selected": selected == "balanced" and result["training_arm_stats"]["premium"]["within_cost_budget"] is False,
        "uncertainty_quantified_and_bounded": 0 < result["training_arm_stats"][selected]["posterior_stddev"] <= result["surrogate"]["max_selected_posterior_stddev"],
        "paired_holdout_improved": result["holdout"]["paired_contexts"] == 3 and result["holdout"]["mean_utility_delta"] > 0,
        "no_success_regression": not result["holdout"]["success_regressions"],
        "trace_hash_bound": result["source"]["sha256"] == hashlib.sha256(traces.read_bytes()).hexdigest(),
        "rollback_without_auto_deploy": result["rollback"] == "restore routing arm base" and result["policy"]["deployment_authorized"] is False,
    }
    evidence = {
        "schema_version": "phase22.bounded_bayesian_routing.v1",
        "journey_id": "NT-optimization-routing",
        "run_id": run_id,
        "repo_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo_root, text=True).strip(),
        "production_entrypoint": str(tool),
        "command": command,
        "command_exit_code": process.returncode,
        "stdout_tail": process.stdout[-2000:],
        "stderr_tail": process.stderr[-2000:],
        "result": str(result_path),
        "assertions": assertions,
        "status": "PASS_WITH_KNOWN_LIMITATIONS" if all(assertions.values()) else "FAIL",
        "limitations": result.get("limitations", []),
    }
    (output / "journey-result.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    assert all(assertions.values()), output / "journey-result.json"
