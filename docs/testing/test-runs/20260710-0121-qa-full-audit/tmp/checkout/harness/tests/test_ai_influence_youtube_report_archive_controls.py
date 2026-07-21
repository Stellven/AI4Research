import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from ai_influence_youtube_report.archive_controls import chatgpt_project_archive_request, report_archive_queue_item  # noqa: E402


def test_archive_controls_are_stub_or_dry_run() -> None:
    item = report_archive_queue_item("report-1", "/tmp/archive")
    request = chatgpt_project_archive_request("https://chatgpt.com/c/fake")

    assert item["mode"] == "dry-run"
    assert request["status"] == "stub_only"
    assert request["project"] == "杂项"
