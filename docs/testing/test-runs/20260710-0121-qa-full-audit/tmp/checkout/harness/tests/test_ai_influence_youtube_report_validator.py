import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from ai_influence_youtube_report.validator import validator_run  # noqa: E402


def _bundle():
    return {
        "run_id": "run-1",
        "report_md": "中心判断：Agent 平台化正在发生。",
        "report_html": "<html><body><svg></svg></body></html>",
        "evidence_map": {
            "entries": [
                {
                    "evidence_ref": "E1",
                    "channel": "AI Engineer",
                    "title": "Agent Platforms",
                    "published_at": "2026-05-25T00:00:00Z",
                    "transcript_grade": "T1",
                }
            ]
        },
        "plan_json": {"trends": []},
    }


def test_validator_outputs_eight_checks_and_passes_clean_bundle() -> None:
    report = validator_run(_bundle())

    assert report.overall == "PASS"
    assert len(report.checks) == 8


def test_validator_fails_any_internal_token() -> None:
    bundle = _bundle()
    bundle["report_md"] = "内部字段 video_id 泄漏"

    report = validator_run(bundle)

    assert report.overall == "FAIL"
    assert any(check.status == "FAIL" for check in report.checks)
