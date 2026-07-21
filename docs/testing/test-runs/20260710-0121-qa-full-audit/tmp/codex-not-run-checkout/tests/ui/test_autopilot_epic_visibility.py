"""Test solar-autopilot-monitor --epic-status-matrix subcommand.

Mocks only file IO via tmp_path; does not mock epic_status_matrix internals.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Load the module directly (it's a script, not a package)
_MONITOR_PATH = Path(__file__).parent.parent.parent / "harness" / "tools" / "solar-autopilot-monitor.py"


def _load_monitor():
    spec = importlib.util.spec_from_file_location("solar_autopilot_monitor", _MONITOR_PATH)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _write_status(directory: Path, sid: str, data: dict) -> None:
    (directory / f"{sid}.status.json").write_text(json.dumps(data), encoding="utf-8")


class TestEpicStatusMatrix:
    """--epic-status-matrix must output ≥5 columns per row and be jq-parsable."""

    @pytest.fixture()
    def monitor(self):
        return _load_monitor()

    @pytest.fixture()
    def populated_sprints(self, tmp_path: Path):
        _write_status(tmp_path, "sprint-A", {
            "sprint_id": "sprint-A",
            "epic_id": "epic-test",
            "status": "active",
            "phase": "planning_complete",
            "handoff_to": "builder_main",
            "history": [{"ts": "2026-05-18T10:00:00Z", "blocked_by": ["sprint-B"]}],
        })
        _write_status(tmp_path, "sprint-B", {
            "sprint_id": "sprint-B",
            "epic_id": "epic-test",
            "status": "passed",
            "phase": "finalized",
            "handoff_to": "",
            "history": [],
        })
        _write_status(tmp_path, "sprint-C", {
            "sprint_id": "sprint-C",
            "epic_id": "epic-other",
            "status": "active",
            "phase": "spec",
            "handoff_to": "pm",
            "history": [],
        })
        return tmp_path

    def test_json_output_parsable(self, monitor, populated_sprints: Path) -> None:
        output_lines: list[str] = []
        with (
            patch.object(monitor, "SPRINTS", populated_sprints),
            patch("builtins.print", side_effect=lambda *a, **k: output_lines.append(str(a[0]))),
        ):
            rc = monitor.epic_status_matrix(epic_id="", output_json=True)
        assert rc == 0
        combined = "\n".join(output_lines)
        parsed = json.loads(combined)
        assert parsed["ok"] is True
        assert parsed["count"] >= 3
        assert isinstance(parsed["rows"], list)

    def test_each_row_has_5_columns(self, monitor, populated_sprints: Path) -> None:
        output_lines: list[str] = []
        with (
            patch.object(monitor, "SPRINTS", populated_sprints),
            patch("builtins.print", side_effect=lambda *a, **k: output_lines.append(str(a[0]))),
        ):
            monitor.epic_status_matrix(epic_id="", output_json=True)
        combined = "\n".join(output_lines)
        parsed = json.loads(combined)
        for row in parsed["rows"]:
            present = [k for k in ("sprint_id", "status", "phase", "handoff_to", "blocked_by", "capability") if k in row]
            assert len(present) >= 5, f"row missing columns: {row}"

    def test_epic_filter(self, monitor, populated_sprints: Path) -> None:
        output_lines: list[str] = []
        with (
            patch.object(monitor, "SPRINTS", populated_sprints),
            patch("builtins.print", side_effect=lambda *a, **k: output_lines.append(str(a[0]))),
        ):
            monitor.epic_status_matrix(epic_id="epic-test", output_json=True)
        combined = "\n".join(output_lines)
        parsed = json.loads(combined)
        for row in parsed["rows"]:
            assert row["epic_id"] == "epic-test"

    def test_blocked_by_extracted(self, monitor, populated_sprints: Path) -> None:
        output_lines: list[str] = []
        with (
            patch.object(monitor, "SPRINTS", populated_sprints),
            patch("builtins.print", side_effect=lambda *a, **k: output_lines.append(str(a[0]))),
        ):
            monitor.epic_status_matrix(epic_id="epic-test", output_json=True)
        combined = "\n".join(output_lines)
        parsed = json.loads(combined)
        sprint_a = next((r for r in parsed["rows"] if r["sprint_id"] == "sprint-A"), None)
        assert sprint_a is not None
        assert "sprint-B" in sprint_a["blocked_by"]
