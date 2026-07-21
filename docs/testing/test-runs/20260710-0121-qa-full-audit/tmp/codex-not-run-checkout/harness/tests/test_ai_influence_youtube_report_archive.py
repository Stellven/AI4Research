import json
import pytest
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from ai_influence_youtube_report.archive import archive_writer_commit  # noqa: E402


def test_archive_writer_commits_four_required_artifacts_on_pass(tmp_path: Path) -> None:
    archive_dir = tmp_path / "report"
    manifest = archive_writer_commit(
        {"archive_dir": str(archive_dir), "chatgpt_session_url": "https://chatgpt.com/c/fake"},
        {
            "report_md": "# Report",
            "report_html": "<html><svg></svg></html>",
            "plan_json": {"trends": []},
            "evidence_map": {"entries": []},
        },
        {"overall": "PASS"},
    )

    assert (archive_dir / "report.md").exists()
    assert (archive_dir / "report.html").exists()
    assert (archive_dir / "plan.json").exists()
    assert (archive_dir / "evidence_map.json").exists()
    assert json.loads((archive_dir / "archive_manifest.json").read_text())["schema_version"] == "archive_manifest.v1"
    assert manifest["archive_dir"] == str(archive_dir)


def test_archive_writer_refuses_failed_validator(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="refuse"):
        archive_writer_commit({"archive_dir": str(tmp_path / "report")}, {}, {"overall": "FAIL"})
