"""Tests for epic_status_view.render_epic_status()."""

from __future__ import annotations

import pytest

from lib.orchestration.epic_status_view import render_epic_status


def _sample_traceability():
    return {
        "schema_version": "solar.epic.traceability.v1",
        "epic_id": "epic-test-001",
        "children": [
            {
                "slice": "requirements",
                "status": "passed",
                "depends_on": [],
                "outcomes_ready": True,
            },
            {
                "slice": "architecture",
                "status": "active",
                "depends_on": ["requirements"],
                "architecture_ready": False,
            },
            {
                "slice": "core-runtime",
                "status": "queued",
                "depends_on": ["architecture"],
                "core_runtime_ready": True,
            },
            {
                "slice": "orchestration-ui",
                "status": "queued",
                "depends_on": ["architecture"],
                "orchestration_ui_ready": True,
            },
            {
                "slice": "verification-release",
                "status": "queued",
                "depends_on": ["core-runtime", "orchestration-ui"],
            },
        ],
    }


class TestRenderEpicStatus:
    def test_renders_header_and_rows(self):
        result = render_epic_status(_sample_traceability())
        assert "epic: epic-test-001" in result
        assert "requirements" in result
        assert "architecture" in result
        assert "core-runtime" in result
        assert "orchestration-ui" in result
        assert "verification-release" in result

    def test_ready_flag_shows_Y_when_ready_fields_true(self):
        t = _sample_traceability()
        result = render_epic_status(t)
        lines = result.split("\n")
        req_line = [l for l in lines if "requirements" in l][0]
        assert "Y" in req_line

    def test_ready_flag_shows_dash_when_no_ready_fields(self):
        t = _sample_traceability()
        # verification-release has no *_ready fields
        result = render_epic_status(t)
        lines = result.split("\n")
        vr_line = [l for l in lines if "verification-release" in l][0]
        assert " - " in vr_line

    def test_deps_missing_shows_deps(self):
        t = _sample_traceability()
        result = render_epic_status(t)
        lines = result.split("\n")
        arch_line = [l for l in lines if "architecture" in l][0]
        assert "requirements" in arch_line

    def test_deps_missing_shows_dash_for_no_deps(self):
        t = _sample_traceability()
        result = render_epic_status(t)
        lines = result.split("\n")
        req_line = [l for l in lines if "requirements" in l][0]
        # requirements has no deps → should show "-"
        assert req_line.strip().endswith("-")

    def test_empty_children(self):
        t = {"epic_id": "epic-empty", "children": []}
        result = render_epic_status(t)
        assert "epic: epic-empty" in result
        # Should have header but no data rows
        lines = [l for l in result.split("\n") if l.strip() and "epic:" not in l and "slice" not in l and "---" not in l]
        assert len(lines) == 0

    def test_missing_epic_id_defaults_to_question_mark(self):
        t = {"children": [{"slice": "x", "status": "ok", "depends_on": []}]}
        result = render_epic_status(t)
        assert "epic: ?" in result

    def test_status_column_present(self):
        result = render_epic_status(_sample_traceability())
        assert "passed" in result
        assert "active" in result
        assert "queued" in result
