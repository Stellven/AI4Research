from __future__ import annotations

import argparse
import sys
from pathlib import Path


HARNESS_LIB = Path(__file__).resolve().parent.parent / "lib"
sys.path.insert(0, str(HARNESS_LIB))

import multi_task_runner as mtr  # noqa: E402


def test_display_tmux_status_marks_terminal_live_as_idle() -> None:
    assert mtr._display_tmux_status("completed", "live") == "idle"
    assert mtr._display_tmux_status("failed", "live") == "idle"
    assert mtr._display_tmux_status("running", "live") == "live"


def test_tvs_payload_uses_idle_for_terminal_history(monkeypatch) -> None:
    monkeypatch.setattr(mtr, "list_task_rows", lambda: [{
        "id": "mt-hist",
        "work": "hist",
        "effective_status": "completed",
        "status": "completed",
        "tmux_status": "live",
        "data_class": "historical",
        "pane_type": "tmux",
        "operator_id": "N/A",
        "operator_vendor": "N/A",
        "provider": "N/A",
        "sprint_id": "sprint-x",
        "node_id": "N2",
        "age": "10m",
    }])
    monkeypatch.setattr(mtr, "task_inventory", lambda tasks: {
        "live": 0,
        "total": 1,
        "historical": 1,
        "stale": 0,
        "latest_age": "10m",
    })
    monkeypatch.setattr(mtr, "tmux_session_exists", lambda: False)
    monkeypatch.setattr(mtr, "free_memory_gb", lambda: None)
    payload = mtr.tvs_payload({"guard": {}, "capability": {}, "panes": [], "dispatches": []})
    assert payload["root"]["sections"][2]["rows"][0]["state"] == "completed/idle"


def test_reap_parser_accepts_ttl_minutes_alias() -> None:
    parser = mtr.build_parser()
    args = parser.parse_args(["reap", "--ttl-minutes", "60", "--dry-run"])
    assert args.ttl_min == 60
    assert args.dry_run is True
