from __future__ import annotations

import json
from pathlib import Path

from evidence import JourneyRecorder
from journey_runner import base_env, prepare_isolated_harness, python_executable


def test_p22_j03_platform_benchmark(repo_root: Path, tmp_path: Path) -> None:
    rec = JourneyRecorder(repo_root, "P22-J03")
    sandbox = tmp_path / "p22-j03"
    harness_dir = prepare_isolated_harness(repo_root, sandbox)
    env = base_env(repo_root, sandbox)
    env["HARNESS_DIR"] = str(harness_dir)
    env["SOLAR_DB"] = str(sandbox / "home" / ".solar" / "solar.db")
    out_json = rec.run_dir / "platform-workflow-benchmark.json"
    out_md = rec.run_dir / "platform-workflow-benchmark.md"
    evidence_dir = rec.run_dir / "platform-workflow-evidence"
    proc = rec.run(
        "platform-benchmark",
        [
            python_executable(repo_root),
            str(repo_root / "harness" / "tools" / "platform_workflow_benchmark.py"),
            "--json",
            "--threshold",
            "80",
            "--out-json",
            str(out_json),
            "--out-md",
            str(out_md),
            "--evidence-dir",
            str(evidence_dir),
        ],
        env=env,
        timeout=240,
    )
    rec.add_artifact(out_json, "benchmark_json")
    rec.add_artifact(out_md, "benchmark_markdown")
    rec.add_artifact(evidence_dir / "benchmark.json", "benchmark_evidence_index")
    parsed = out_json.exists() and json.loads(out_json.read_text(encoding="utf-8"))
    json_written = out_json.exists() and out_json.stat().st_size > 0
    markdown_written = out_md.exists() and out_md.stat().st_size > 0
    evidence_written = (evidence_dir / "benchmark.json").exists() and (evidence_dir / "benchmark.json").stat().st_size > 0
    # Exit 0 means the measured target met the threshold. Exit 1 means the
    # benchmark completed successfully but measured a below-threshold target.
    # J03 validates the benchmark process, not the quality of the target.
    benchmark_completed = proc.returncode in {0, 1}
    rec.add_assertion("benchmark_runner_executed", json_written, str(out_json))
    rec.add_assertion("benchmark_markdown_written", markdown_written, str(out_md))
    rec.add_assertion("benchmark_evidence_index_written", evidence_written, str(evidence_dir / "benchmark.json"))
    rec.add_assertion(
        "benchmark_runner_completed",
        benchmark_completed,
        {"exit_code": proc.returncode, "exit_semantics": "0=target met threshold; 1=target below threshold"},
    )
    process_complete = False
    if parsed:
        score = parsed.get("score", {})
        average_score = score.get("average") if isinstance(score, dict) else None
        scenarios = parsed.get("scenarios", [])
        scenario_scores = [item.get("score") for item in scenarios if isinstance(item, dict)]
        recomputed_average = (
            sum(score for score in scenario_scores if isinstance(score, (int, float))) / len(scenario_scores)
            if scenario_scores
            else None
        )
        failed_checks = [
            check
            for scenario in scenarios
            if isinstance(scenario, dict)
            for check in scenario.get("failed_checks", [])
        ]
        verdict_consistent = bool(parsed.get("ok")) == (
            isinstance(average_score, (int, float)) and average_score >= 80
        )
        scenarios_recorded = len(scenarios) > 0 and all(
            isinstance(scenario_score, (int, float)) for scenario_score in scenario_scores
        )
        average_recomputes = (
            isinstance(average_score, (int, float))
            and isinstance(recomputed_average, (int, float))
            and abs(average_score - recomputed_average) < 0.001
        )
        failures_explain_verdict = bool(parsed.get("ok")) or bool(failed_checks)
        framing_recorded = (
            isinstance(parsed.get("threshold"), (int, float))
            and isinstance(parsed.get("weights"), dict)
            and bool(parsed.get("weights"))
            and bool(parsed.get("benchmark"))
        )
        rec.add_assertion(
            "benchmark_quality_verdict_recorded",
            isinstance(parsed.get("ok"), bool) and isinstance(average_score, (int, float)),
            {"target_met_threshold": parsed.get("ok"), "score": score, "threshold": parsed.get("threshold")},
        )
        rec.add_assertion(
            "benchmark_score_consistent_with_threshold",
            verdict_consistent,
            {"ok": parsed.get("ok"), "average": average_score, "threshold": 80},
        )
        rec.add_assertion(
            "benchmark_scenarios_recorded",
            scenarios_recorded,
            {"scenario_count": len(scenarios), "scenario_scores": scenario_scores},
        )
        rec.add_assertion(
            "benchmark_average_recomputes",
            average_recomputes,
            {"reported_average": average_score, "recomputed_average": recomputed_average},
        )
        rec.add_assertion(
            "benchmark_failures_explain_verdict",
            failures_explain_verdict,
            {"ok": parsed.get("ok"), "failed_checks": sorted(set(str(check) for check in failed_checks))},
        )
        rec.add_assertion(
            "benchmark_framing_recorded",
            framing_recorded,
            {"benchmark": parsed.get("benchmark"), "threshold": parsed.get("threshold"), "weights": parsed.get("weights")},
        )
        process_complete = all(
            (
                json_written,
                markdown_written,
                evidence_written,
                benchmark_completed,
                verdict_consistent,
                scenarios_recorded,
                average_recomputes,
                failures_explain_verdict,
                framing_recorded,
            )
        )
        rec.add_l2("Workflow", "Benchmark Framing", "threshold, scoring weights, and named scenarios were recorded; baseline and version-history variants remain outside this run", out_json, "partial")
        rec.add_l2("Workflow", "Benchmark Protocol & Asset Preparation", "isolated harness and explicit JSON/Markdown/evidence output paths were used; repetitions and resource-limit variants remain outside this run", evidence_dir / "benchmark.json", "partial")
        rec.add_l2("Workflow", "Benchmark Execution", "official platform benchmark runner completed and wrote scored evidence even though the measured target was below threshold", out_json, "full")
        rec.add_l2("Workflow", "Metrics & Run Evidence Collection", "per-scenario scores, failed checks, commands, and evidence artifacts were generated; detailed resource consumption was not measured", evidence_dir / "benchmark.json", "partial")
        rec.add_l2("Workflow", "Comparative Result Analysis & Benchmark Result Packaging", "the report consistently packaged the score and failed checks; broader POC-versus-baseline comparisons remain outside this run", out_md, "partial")
        rec.add_l2("Foundation", "Benchmark Asset Construction", "the executable benchmark configuration and durable result assets were demonstrated; authoring new datasets and baselines was not", out_json, "partial")
        rec.add_l2("Foundation", "Performance, Cost & Benchmark Evaluator", "the evaluator computed scenario and aggregate quality results; cost, throughput, and scalability measurements were not exercised", out_json, "partial")
        rec.add_l2("Foundation", "Build Evidence Generation", "benchmark command logs, hashes, and output artifacts were retained; build diff and compile variants were not exercised", rec.run_dir / "commands.json", "partial")
    if process_complete:
        rec.finalize("PASS")
        return
    rec.finalize("FAIL")
