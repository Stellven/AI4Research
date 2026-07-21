#!/usr/bin/env bash
# Regression: dependency_policy.blocks_until may contain dict entries.
set -euo pipefail

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

mkdir -p "$TMP/sprints"

cat > "$TMP/sprints/upstream.status.json" <<'JSON'
{"sprint_id":"upstream","status":"passed","phase":"completed"}
JSON

cat > "$TMP/sprints/child.task_graph.json" <<'JSON'
{
  "sprint_id": "child",
  "dependency_policy": {
    "blocks_until": [
      {"sprint_id": "upstream", "required_status": "passed"}
    ]
  },
  "nodes": []
}
JSON

REAL_HARNESS_DIR="${REAL_HARNESS_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
HARNESS_DIR="$TMP" REAL_HARNESS_DIR="$REAL_HARNESS_DIR" python3 - <<'PY'
import importlib.util
import os
from pathlib import Path

module_path = Path(os.environ["REAL_HARNESS_DIR"]) / "tools" / "solar-autopilot-monitor.py"
spec = importlib.util.spec_from_file_location("autopilot_monitor", module_path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

blocks = mod.child_graph_external_prerequisite_blocks("child")
assert blocks == [], blocks

from pathlib import Path as _Path
lib_dir = _Path(os.environ["REAL_HARNESS_DIR"]) / "lib"
for name in ["workflow_guard", "graph_scheduler", "epic_decomposer"]:
    spec = importlib.util.spec_from_file_location(name, lib_dir / f"{name}.py")
    lib = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lib)
    if name == "workflow_guard":
        assert lib._blocked_external_prerequisites(_Path(os.environ["HARNESS_DIR"]) / "sprints" / "child.task_graph.json") == []
    elif name == "graph_scheduler":
        graph = __import__("json").loads((_Path(os.environ["HARNESS_DIR"]) / "sprints" / "child.task_graph.json").read_text())
        assert lib.blocked_external_prerequisites(graph) == []
    else:
        assert lib.blocked_child_graph_prerequisites("child") == []

(Path(__import__("os").environ["HARNESS_DIR"]) / "sprints" / "upstream.status.json").write_text(
    '{"sprint_id":"upstream","status":"active","phase":"planning_complete"}'
)
blocks = mod.child_graph_external_prerequisite_blocks("child")
assert len(blocks) == 1, blocks
assert blocks[0]["sprint_id"] == "upstream", blocks
assert blocks[0]["required"] == "passed", blocks
assert blocks[0]["reason"] == "status_not_satisfied", blocks
assert not blocks[0]["sprint_id"].startswith("{"), blocks

for name in ["workflow_guard", "graph_scheduler", "epic_decomposer"]:
    spec = importlib.util.spec_from_file_location(name, lib_dir / f"{name}.py")
    lib = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lib)
    if name == "workflow_guard":
        blocks = lib._blocked_external_prerequisites(_Path(os.environ["HARNESS_DIR"]) / "sprints" / "child.task_graph.json")
    elif name == "graph_scheduler":
        graph = __import__("json").loads((_Path(os.environ["HARNESS_DIR"]) / "sprints" / "child.task_graph.json").read_text())
        blocks = lib.blocked_external_prerequisites(graph)
    else:
        blocks = lib.blocked_child_graph_prerequisites("child")
    assert len(blocks) == 1, (name, blocks)
    assert blocks[0]["sprint_id"] == "upstream", (name, blocks)
    assert blocks[0]["required"] == "passed", (name, blocks)
    assert not blocks[0]["sprint_id"].startswith("{"), (name, blocks)

child_graph = _Path(os.environ["HARNESS_DIR"]) / "sprints" / "child.task_graph.json"
child_graph.write_text('''{
  "sprint_id": "child",
  "dependency_policy": {
    "blocks_until": [
      {"sprint_id": "upstream", "required_status": "planning_complete"}
    ]
  },
  "nodes": []
}''')
(_Path(os.environ["HARNESS_DIR"]) / "sprints" / "upstream.status.json").write_text(
    '{"sprint_id":"upstream","status":"passed","phase":"finalized"}'
)
assert mod.child_graph_external_prerequisite_blocks("child") == []

for name in ["workflow_guard", "graph_scheduler", "epic_decomposer"]:
    spec = importlib.util.spec_from_file_location(name, lib_dir / f"{name}.py")
    lib = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lib)
    if name == "workflow_guard":
        blocks = lib._blocked_external_prerequisites(child_graph)
    elif name == "graph_scheduler":
        graph = __import__("json").loads(child_graph.read_text())
        blocks = lib.blocked_external_prerequisites(graph)
    else:
        blocks = lib.blocked_child_graph_prerequisites("child")
    assert blocks == [], (name, blocks)
PY

echo "PASS: autopilot dict prerequisites normalize to real sprint_id"
