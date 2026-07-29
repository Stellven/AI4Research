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
    rec.add_assertion("benchmark_runner_executed", out_json.exists(), str(out_json))
    rec.add_assertion("benchmark_markdown_written", out_md.exists() and out_md.stat().st_size > 0, str(out_md))
    rec.add_assertion("benchmark_exit_zero", proc.returncode == 0, proc.returncode)
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
        rec.add_assertion("benchmark_threshold_met", bool(parsed.get("ok")), score)
        rec.add_assertion(
            "benchmark_score_consistent_with_threshold",
            bool(parsed.get("ok")) == (isinstance(average_score, (int, float)) and average_score >= 80),
            {"ok": parsed.get("ok"), "average": average_score, "threshold": 80},
        )
        rec.add_assertion(
            "benchmark_scenarios_recorded",
            len(scenarios) > 0 and all(isinstance(score, (int, float)) for score in scenario_scores),
            {"scenario_count": len(scenarios), "scenario_scores": scenario_scores},
        )
        rec.add_assertion(
            "benchmark_average_recomputes",
            isinstance(average_score, (int, float))
            and isinstance(recomputed_average, (int, float))
            and abs(average_score - recomputed_average) < 0.001,
            {"reported_average": average_score, "recomputed_average": recomputed_average},
        )
        rec.add_assertion(
            "benchmark_failures_explain_verdict",
            bool(parsed.get("ok")) or bool(failed_checks),
            {"ok": parsed.get("ok"), "failed_checks": sorted(set(str(check) for check in failed_checks))},
        )
        rec.add_l2("Workflow", "Benchmark Framing", "threshold, scoring weights, and named scenarios were recorded by the benchmark run", out_json, "partial")
        rec.add_l2("Workflow", "Benchmark Protocol & Asset Preparation", "isolated harness and explicit JSON/Markdown/evidence output paths were used", evidence_dir / "benchmark.json", "partial")
        rec.add_l2("Workflow", "Benchmark Execution", "official platform benchmark runner executed and wrote scored evidence", out_json, "partial")
        rec.add_l2("Workflow", "Metrics & Run Evidence Collection", "per-scenario scores, failed checks, and evidence directory were generated", evidence_dir / "benchmark.json", "partial")
        rec.add_l2("Workflow", "Comparative Result Analysis & Benchmark Result Packaging", "overall verdict follows the threshold and hard-fail evidence rather than report existence", out_md, "partial")
        rec.add_l2("Foundation", "Benchmark Asset Construction", "benchmark assets were produced as durable JSON, Markdown, and evidence index artifacts", out_json, "partial")
        rec.add_l2("Foundation", "Performance, Cost & Benchmark Evaluator", "benchmark evaluator computed average/minimum scores and failing checks", out_json, "partial")
        rec.add_l2("Foundation", "Build Evidence Generation", "benchmark command logs and output artifacts were retained for audit", rec.run_dir / "commands.json", "partial")
    if proc.returncode == 0 and parsed and parsed.get("ok"):
        rec.finalize("PASS")
        return
    if parsed and out_md.exists():
        rec.finalize(
            "FAIL",
            limitations=[
                "The official benchmark runner executed and wrote evidence, but the current isolated harness scored below the Phase 22 threshold."
            ],
        )
        return
    rec.finalize("FAIL")
