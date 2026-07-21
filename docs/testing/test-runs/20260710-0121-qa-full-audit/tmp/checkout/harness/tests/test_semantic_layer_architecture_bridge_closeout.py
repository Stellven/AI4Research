from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from semantic_layer_architecture_bridge_closeout import verify  # noqa: E402


def test_verify_bridge_success(tmp_path: Path) -> None:
    runtime_root = tmp_path
    sprints = runtime_root / "sprints"
    sprints.mkdir(parents=True)

    graph = {
        "nodes": [
            {"id": "P1"},
            {"id": "P2"},
            {"id": "P3"},
            {"id": "B1", "depends_on": [], "write_scope": ["a"], "acceptance": ["x"], "gate": "GB1"},
            {"id": "B2", "depends_on": ["B1"], "write_scope": ["a"], "acceptance": ["x"], "gate": "GB2"},
            {"id": "B3", "depends_on": ["B1"], "write_scope": ["a"], "acceptance": ["x"], "gate": "GB3"},
            {"id": "B4", "depends_on": ["B1"], "write_scope": ["a"], "acceptance": ["x"], "gate": "GB4"},
            {"id": "B5", "depends_on": ["B2"], "write_scope": ["a"], "acceptance": ["x"], "gate": "GB5"},
            {"id": "B6", "depends_on": ["B3", "B4"], "write_scope": [], "acceptance": ["x"], "gate": "GB6"},
        ]
    }
    (sprints / "sprint-20260524-141723.task_graph.json").write_text(json.dumps(graph), encoding="utf-8")
    (sprints / "sprint-20260524-141723.status.json").write_text(
        json.dumps({"handoff_to": "builder_parallel", "target_role": "builder_parallel"}),
        encoding="utf-8",
    )
    (sprints / "sprint-20260524-141723.planning.html").write_text("builder_parallel", encoding="utf-8")
    (sprints / "sprint-20260524-141723.P2-handoff.md").write_text("ok\n", encoding="utf-8")
    (sprints / "sprint-20260524-141723.P3-handoff.md").write_text("ok\n", encoding="utf-8")
    (sprints / "sprint-20260524-p0-knowledge-wide-thunderomlx-semantic-layer-scope-all-kn-s03-core-runtime.status.json").write_text(
        json.dumps({"status": "passed"}),
        encoding="utf-8",
    )

    result = verify(runtime_root)
    assert result["ok"] is True
    assert result["bridge_node_count"] == 6
    assert Path(result["traceability_path"]).exists()
