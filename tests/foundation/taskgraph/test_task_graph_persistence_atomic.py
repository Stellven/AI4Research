"""Executable Phase 22 atomic gaps for TaskGraph persistence."""
from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[3]
LIB = ROOT / "harness" / "lib"
sys.path.insert(0, str(LIB))

import task_graph_io as tgio


def test_atomic_taskgraph_persistence_lifecycle_management__corrupt(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(tgio, "SPRINTS_DIR", tmp_path)
    sprint_id = "phase22-corrupt-spec"
    tgio.spec_path(sprint_id).write_text("{not-json", encoding="utf-8")

    assert tgio.load_spec(sprint_id) == {}
    assert tgio.spec_valid(sprint_id) == (False, "parse_error")
