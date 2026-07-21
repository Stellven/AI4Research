from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from epic_projection_closeout import close_epic_projection  # noqa: E402


def test_close_epic_projection_marks_passed_and_creates_status(tmp_path):
    sprints = tmp_path / "sprints"
    sprints.mkdir(parents=True)
    epic_id = "epic-test"
    graph = {
        "epic_id": epic_id,
        "nodes": [
            {"id": "S01", "status": "passed", "child_sprint_id": "child-1"},
            {"id": "S02", "status": "pending", "child_sprint_id": "child-2"},
        ],
    }
    (sprints / f"{epic_id}.task_graph.json").write_text(json.dumps(graph), encoding="utf-8")
    (sprints / f"{epic_id}.epic.json").write_text(json.dumps({"epic_id": epic_id, "title": "Epic Test"}), encoding="utf-8")
    (sprints / "child-1.status.json").write_text(json.dumps({"status": "passed"}), encoding="utf-8")
    (sprints / "child-2.status.json").write_text(json.dumps({"status": "passed"}), encoding="utf-8")

    result = close_epic_projection(tmp_path, epic_id)

    assert result["ok"] is True
    status = json.loads((sprints / f"{epic_id}.status.json").read_text())
    assert status["status"] == "passed"
    assert status["task_graph_status"] == "passed"
