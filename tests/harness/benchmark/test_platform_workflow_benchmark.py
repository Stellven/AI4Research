from __future__ import annotations

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
