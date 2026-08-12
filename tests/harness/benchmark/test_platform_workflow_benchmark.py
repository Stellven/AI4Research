from __future__ import annotations

import json

from harness.tools import platform_workflow_benchmark as pwb


def _scenario(row: int, name: str, score: int) -> dict:
    return pwb.scenario_result(
        row,
        name,
        {
            "runtime": {
                "ok": score >= 80,
                "points": score,
            }
        },
    )


def test_platform_benchmark_process_pass_is_separate_from_low_target_quality(monkeypatch, tmp_path):
    monkeypatch.setattr(pwb, "bench_remote_migration", lambda evidence_dir: _scenario(18, "remote", 50))
    monkeypatch.setattr(pwb, "bench_mempalace", lambda evidence_dir: _scenario(19, "mempalace", 100))
    monkeypatch.setattr(pwb, "bench_cortex", lambda evidence_dir: _scenario(20, "cortex", 100))
    monkeypatch.setattr(pwb, "bench_tested_sprint", lambda *args, **kwargs: _scenario(args[0], args[1], 100))
    monkeypatch.setattr(pwb, "bench_config_ui", lambda evidence_dir: _scenario(25, "config", 100))

    result = pwb.benchmark(80, tmp_path / "evidence")

    assert result["process_status"] == "completed"
    assert result["benchmark_execution_verdict"] == "PASS"
    assert result["target_quality_verdict"] == "FAIL"
    assert result["ok"] is False


def test_platform_benchmark_repetitions_timing_and_baseline(monkeypatch, tmp_path):
    def sampled_scenarios(evidence_dir):
        scenario = _scenario(18, "remote", 100)
        scenario["duration_seconds"] = 0.01
        return [scenario]

    monkeypatch.setattr(pwb, "_run_scenarios", sampled_scenarios)
    baseline = {
        "benchmark": "solar_platform_workflows",
        "generated_at": "2026-08-12T00:00:00Z",
        "scenarios": [{"row": 18, "name": "remote", "score": 90, "performance": {"median_duration_seconds": 1.0}}],
    }

    result = pwb.benchmark(80, tmp_path / "evidence", repetitions=2, baseline=baseline)

    assert result["protocol"]["repetitions"] == 2
    assert result["performance"]["scenario_executions"] == 2
    assert result["performance"]["scenario_executions_per_second"] > 0
    assert result["performance"]["monetary_cost"]["status"] == "not_measured"
    assert result["performance"]["scalability"]["status"] == "not_measured"
    assert len(result["scenarios"][0]["performance"]["duration_samples_seconds"]) == 2
    assert result["comparison"]["status"] == "completed"
    assert result["comparison"]["scenario_comparisons"][0]["score_delta"] == 10


def test_platform_benchmark_artifact_manifest_rejects_tamper(tmp_path):
    artifact = tmp_path / "result.json"
    artifact.write_text('{"ok": true}\n', encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    payload = pwb.write_artifact_manifest(manifest, "solar_platform_workflows", [artifact])

    ok, failures = pwb.verify_artifact_manifest(manifest)
    assert ok is True
    assert failures == []
    assert payload["artifacts"][0]["sha256"] == pwb.file_sha256(artifact)

    artifact.write_text('{"ok": false}\n', encoding="utf-8")
    ok, failures = pwb.verify_artifact_manifest(manifest)
    assert ok is False
    assert any("mismatch" in failure for failure in failures)


def test_platform_benchmark_manifest_cli_rejects_empty_artifacts(tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({
            "schema": "solar_platform_benchmark_artifact_manifest.v1",
            "status": "completed",
            "benchmark": "solar_platform_workflows",
            "artifacts": [],
        }),
        encoding="utf-8",
    )
    ok, failures = pwb.verify_artifact_manifest(manifest)
    assert ok is False
    assert failures == ["manifest has no artifacts"]


def test_platform_benchmark_rejects_wrong_or_duplicate_baseline_identity():
    current = [_scenario(18, "remote", 100)]
    wrong = {"benchmark": "unrelated", "scenarios": [{"row": 18, "score": 100}]}
    duplicate = {
        "benchmark": "solar_platform_workflows",
        "scenarios": [{"row": 18, "score": 100}, {"row": 18, "score": 100}],
    }

    assert pwb._baseline_comparison(current, wrong)["status"] == "invalid"
    assert pwb._baseline_comparison(current, duplicate)["status"] == "invalid"


def test_platform_benchmark_manifest_rejects_malformed_entry(tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({
            "schema": "solar_platform_benchmark_artifact_manifest.v1",
            "status": "completed",
            "benchmark": "solar_platform_workflows",
            "artifacts": ["not-an-object"],
        }),
        encoding="utf-8",
    )
    ok, failures = pwb.verify_artifact_manifest(manifest)
    assert ok is False
    assert failures == ["manifest artifact entry is not an object"]
