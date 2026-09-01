from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[3] / "harness" / "tools" / "solar-autopilot-monitor.py"


def _load():
    spec = importlib.util.spec_from_file_location("autopilot_elastic_owner", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_legacy_planner_suppression_requires_exact_owner_receipt(tmp_path: Path) -> None:
    monitor = _load()
    monitor.SPRINTS = tmp_path / "sprints"
    sid = "sprint-elastic-owned"
    owner = monitor.SPRINTS / sid / "elastic-planner" / "owner.json"
    owner.parent.mkdir(parents=True)
    owner.write_text(
        json.dumps(
            {
                "schema_version": "solar.elastic_planner_owner.v1",
                "artifact_role": "control_plane_receipt",
                "sprint_id": sid,
                "state": "submitted",
            }
        ),
        encoding="utf-8",
    )

    assert monitor.elastic_planner_owns_sprint(sid) is True
    assert monitor.elastic_planner_owns_sprint("sprint-unowned") is False
    owner.write_text(json.dumps({"schema_version": "wrong", "sprint_id": sid, "state": "submitted"}), encoding="utf-8")
    assert monitor.elastic_planner_owns_sprint(sid) is False
