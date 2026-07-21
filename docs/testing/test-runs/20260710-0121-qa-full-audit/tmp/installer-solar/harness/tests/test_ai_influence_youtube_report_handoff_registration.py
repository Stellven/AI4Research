import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from ai_influence_youtube_report.pane_surface import handoff_registration_status  # noqa: E402


def test_handoff_registration_paths() -> None:
    empty = handoff_registration_status("")
    partial = handoff_registration_status("/tmp/handoff.md")
    joined = handoff_registration_status("/tmp/handoff.md", "/tmp/eval.json")

    assert empty["registered"] is False
    assert partial["registered"] is True
    assert partial["join_ready"] is False
    assert joined["join_ready"] is True
