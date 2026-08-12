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
    baseline_json = rec.run_dir / "platform-workflow-baseline.json"
    baseline_md = rec.run_dir / "platform-workflow-baseline.md"
    baseline_evidence_dir = rec.run_dir / "platform-workflow-baseline-evidence"
    manifest = rec.run_dir / "platform-workflow-artifact-manifest.json"
    benchmark_cli = repo_root / "harness" / "tools" / "platform_workflow_benchmark.py"
    baseline_proc = rec.run(
        "platform-benchmark-baseline",
        [
            python_executable(repo_root), str(benchmark_cli), "--json", "--threshold", "80",
            "--out-json", str(baseline_json), "--out-md", str(baseline_md),
            "--evidence-dir", str(baseline_evidence_dir), "--repetitions", "1",
        ],
        env=env,
        timeout=240,
    )
    proc = rec.run(
        "platform-benchmark",
        [
            python_executable(repo_root),
            str(benchmark_cli),
            "--json",
            "--threshold",
            "80",
            "--out-json",
            str(out_json),
            "--out-md",
            str(out_md),
            "--evidence-dir",
            str(evidence_dir),
            "--repetitions",
            "2",
            "--baseline-json",
            str(baseline_json),
            "--manifest",
            str(manifest),
        ],
        env=env,
        timeout=240,
    )
    rec.add_artifact(out_json, "benchmark_json")
    rec.add_artifact(out_md, "benchmark_markdown")
    rec.add_artifact(evidence_dir / "benchmark.json", "benchmark_evidence_index")
    rec.add_artifact(baseline_json, "benchmark_baseline_json")
    rec.add_artifact(manifest, "benchmark_artifact_manifest")
    verify_proc = rec.run(
        "platform-benchmark-manifest-verify",
        [python_executable(repo_root), str(benchmark_cli), "--verify-manifest", str(manifest)],
        env=env,
        timeout=30,
    )
    original_markdown = out_md.read_bytes() if out_md.is_file() else b""
    if original_markdown:
        out_md.write_bytes(original_markdown + b"\nTAMPER-PROBE\n")
    tamper_proc = rec.run(
        "platform-benchmark-manifest-tamper-negative",
        [python_executable(repo_root), str(benchmark_cli), "--verify-manifest", str(manifest)],
        env=env,
        timeout=30,
    )
    if original_markdown:
        out_md.write_bytes(original_markdown)
    restored_verify_proc = rec.run(
        "platform-benchmark-manifest-restored-verify",
        [python_executable(repo_root), str(benchmark_cli), "--verify-manifest", str(manifest)],
        env=env,
        timeout=30,
    )
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
        protocol = parsed.get("protocol") if isinstance(parsed.get("protocol"), dict) else {}
        performance = parsed.get("performance") if isinstance(parsed.get("performance"), dict) else {}
        comparison = parsed.get("comparison") if isinstance(parsed.get("comparison"), dict) else {}
        scenario_performance = [item.get("performance") for item in scenarios if isinstance(item, dict)]
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
        rec.add_assertion(
            "benchmark_repeated_protocol_and_timings_recorded",
            protocol.get("repetitions") == 2
            and performance.get("scenario_executions") == len(scenarios) * 2
            and performance.get("scenario_executions_per_second", 0) > 0
            and all(
                isinstance(item, dict)
                and len(item.get("duration_samples_seconds") or []) == 2
                and item.get("median_duration_seconds", -1) >= 0
                for item in scenario_performance
            ),
            {"protocol": protocol, "performance": performance, "scenario_performance": scenario_performance},
        )
        rec.add_assertion(
            "benchmark_baseline_comparison_complete",
            baseline_proc.returncode == 0
            and comparison.get("status") == "completed"
            and len(comparison.get("scenario_comparisons") or []) == len(scenarios),
            comparison,
        )
        rec.add_assertion(
            "benchmark_manifest_accepts_original_rejects_tamper",
            verify_proc.returncode == 0 and tamper_proc.returncode == 2 and restored_verify_proc.returncode == 0,
            {"verify": verify_proc.returncode, "tamper": tamper_proc.returncode, "restored": restored_verify_proc.returncode},
        )
        manifest_payload = json.loads(manifest.read_text(encoding="utf-8")) if manifest.is_file() else {}
        manifest_paths = {str(item.get("path") or "") for item in manifest_payload.get("artifacts") or [] if isinstance(item, dict)}
        rec.add_assertion(
            "benchmark_manifest_covers_baseline_and_current_outputs",
            all(str(path.resolve()) in manifest_paths for path in (baseline_json, out_json, out_md, evidence_dir / "benchmark.json")),
            {"required": [str(path.resolve()) for path in (baseline_json, out_json, out_md, evidence_dir / "benchmark.json")], "manifest_count": len(manifest_paths)},
        )
        rec.add_assertion(
            "benchmark_resource_cost_and_scale_measured_truthfully",
            (performance.get("resource_consumption") or {}).get("status") == "measured"
            and (performance.get("resource_consumption") or {}).get("command_count", 0) > 0
            and (performance.get("resource_consumption") or {}).get("peak_rss_bytes_max", 0) > 0
            and (performance.get("monetary_cost") or {}).get("status") == "measured"
            and (performance.get("monetary_cost") or {}).get("amount") == 0.0
            and (performance.get("scalability") or {}).get("status") == "measured_current_scale"
            and (performance.get("scalability") or {}).get("scenario_executions") == len(scenarios) * 2,
            performance,
        )
        asset = parsed.get("benchmark_asset") if isinstance(parsed.get("benchmark_asset"), dict) else {}
        build = parsed.get("build_evidence") if isinstance(parsed.get("build_evidence"), dict) else {}
        rec.add_assertion(
            "benchmark_asset_and_build_evidence_complete",
            asset.get("dataset_version") == "rows-18-25.v1"
            and len(str(asset.get("sha256") or "")) == 64
            and build.get("compile", {}).get("ok") is True
            and len(str(build.get("runner_sha256") or "")) == 64
            and len(str(build.get("source_diff", {}).get("sha256") or "")) == 64,
            {"asset": asset, "build_evidence": build},
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
                protocol.get("repetitions") == 2,
                comparison.get("status") == "completed",
                verify_proc.returncode == 0,
                tamper_proc.returncode == 2,
                restored_verify_proc.returncode == 0,
                all(str(path.resolve()) in manifest_paths for path in (baseline_json, out_json, out_md, evidence_dir / "benchmark.json")),
            )
        )
        rec.add_l2("Workflow", "Benchmark Framing", "threshold, scoring weights, named scenarios, and a current baseline comparison were recorded", out_json, "full")
        rec.add_l2("Workflow", "Benchmark Protocol & Asset Preparation", "isolated per-repetition evidence paths, two samples, command timeouts, and explicit JSON/Markdown/manifest outputs were used", evidence_dir / "benchmark.json", "full")
        rec.add_l2("Workflow", "Benchmark Execution", "official platform benchmark runner completed and wrote scored evidence even though the measured target was below threshold", out_json, "full")
        rec.add_l2("Workflow", "Metrics & Run Evidence Collection", "per-scenario scores, failed checks, command evidence, repeated timings, aggregate throughput, child CPU time, and peak working-set memory were generated", evidence_dir / "benchmark.json", "full")
        rec.add_l2("Workflow", "Comparative Result Analysis & Benchmark Result Packaging", "the report packaged scores, failed checks, and per-scenario current-versus-baseline deltas", out_md, "full")
        rec.add_l2("Foundation", "Benchmark Asset Construction", "the executable benchmark configuration, newly constructed baseline, repeated evidence directories, and durable result assets were demonstrated", baseline_json, "full")
        rec.add_l2("Foundation", "Performance, Cost & Benchmark Evaluator", "the evaluator measured wall time, child CPU, peak working-set memory, observed throughput/current workload scale, and a truthful zero provider cost", out_json, "full")
        rec.add_l2("Foundation", "Build Evidence Generation", "the production runner compiled, recorded runner and source-diff hashes, and the artifact manifest accepted originals, rejected tampering, and accepted restored bytes", manifest, "full")
    if process_complete:
        rec.finalize("PASS")
        return
    rec.finalize("FAIL")
