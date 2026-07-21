import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from ai_influence_youtube_report.automation_policy import decide_external_action  # noqa: E402


def test_automation_policy_branches() -> None:
    assert decide_external_action(has_secret=False, logged_in=False, dry_run=True)["status"] == "dry-run"
    assert decide_external_action(has_secret=False, logged_in=True, dry_run=False)["status"] == "blocked"
    assert decide_external_action(has_secret=True, logged_in=False, dry_run=False)["reason"] == "browser_agent_not_logged_in"
    assert decide_external_action(has_secret=True, logged_in=True, dry_run=False)["status"] == "ready"
