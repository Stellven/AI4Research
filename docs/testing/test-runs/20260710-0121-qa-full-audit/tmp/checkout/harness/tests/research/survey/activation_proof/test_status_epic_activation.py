"""Activation proof for status-epic surface."""

from __future__ import annotations

import argparse
import io
from contextlib import redirect_stdout

from cli.cmd_status_epic import run_status_epic
from lib.orchestration.epic_status_view import render_epic_status


def test_render_epic_status_surface_is_callable() -> None:
    rendered = render_epic_status(
        {
            "epic_id": "epic-test",
            "children": [
                {"slice": "requirements", "status": "passed", "depends_on": [], "outcomes_ready": True}
            ],
        }
    )
    assert "epic: epic-test" in rendered
    assert "requirements" in rendered
    assert "passed" in rendered


def test_run_status_epic_importable_and_callable_for_real_epic() -> None:
    args = argparse.Namespace(
        epic="epic-20260516-deepresearch-professor-grade-survey-quality-hardening-build"
    )
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = run_status_epic(args)
    output = buf.getvalue()
    assert rc == 0
    assert "verification-release" in output
    assert "core-runtime" in output

