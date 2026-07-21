import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from ai_influence_youtube_report.archive import archive_writer_commit  # noqa: E402
from ai_influence_youtube_report.evidence_map import build_evidence_map  # noqa: E402
from ai_influence_youtube_report.render import render_report_html  # noqa: E402
from ai_influence_youtube_report.validator import validator_run  # noqa: E402


def test_runtime_minimal_report_bundle_passes_and_archives(tmp_path: Path) -> None:
    evidence = build_evidence_map([
        {
            "evidence_ref": "E1",
            "channel": "AI Engineer",
            "title": "Agent Platforms",
            "published_at": "2026-05-25T00:00:00Z",
            "transcript_grade": "T1",
            "citation_span": "agent runtime",
            "group_type": "conference",
        }
    ])
    html = render_report_html("中心判断：Agent 平台化。", evidence, {"title": "Agent 平台"})
    bundle = {
        "run_id": "run-1",
        "report_md": "中心判断：Agent 平台化。",
        "report_html": html,
        "evidence_map": evidence,
        "plan_json": {"trends": [{"chapters": []}]},
    }
    verdict = validator_run(bundle).to_dict()
    manifest = archive_writer_commit({"archive_dir": str(tmp_path / "archive")}, bundle, verdict)

    assert verdict["overall"] == "PASS"
    assert manifest["schema_version"] == "archive_manifest.v1"
