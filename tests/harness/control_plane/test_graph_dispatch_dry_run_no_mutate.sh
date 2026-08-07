#!/usr/bin/env bash
# Regression: graph dispatch dry-run must not enqueue, lease, or mark nodes dispatched.
set -euo pipefail

HARNESS_DIR_REAL="${HARNESS_DIR:-$HOME/.solar/harness}"
TMPDIR_TEST="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_TEST"' EXIT

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

cat > "$TMPDIR_TEST/graph.json" <<'JSON'
{
  "sprint_id": "sprint-dry-run-no-mutate",
  "title": "Dry Run No Mutate",
  "version": 1,
  "required_gates": ["g1"],
  "nodes": [
    {
      "id": "R0",
      "goal": "dry-run test",
      "depends_on": [],
      "write_scope": ["/tmp/solar-dry-run-no-mutate.txt"],
      "read_scope": [],
      "required_skills": ["python"],
      "preferred_model": "glm",
      "gate": "g1",
      "acceptance": ["ok"]
    }
  ],
  "node_results": {},
  "gate_results": {}
}
JSON

python3 - "$HARNESS_DIR_REAL" "$TMPDIR_TEST/graph.json" <<'PY'
import json
import sys
from pathlib import Path

harness = Path(sys.argv[1])
graph_path = Path(sys.argv[2])
sys.path.insert(0, str(harness / "lib"))
from graph_scheduler import enqueue_ready  # noqa: E402

graph = json.loads(graph_path.read_text(encoding="utf-8"))
workers = [{
    "pane": "solar-harness-lab:0.0",
    "models": ["glm", "glm-5.1"],
    "skills": ["python", "bash", "testing"],
    "capabilities": [],
    "busy": False,
}]
result = enqueue_ready(graph, str(graph_path), workers, max_parallel=1, lease=False, dry_run=True)
assert result["ok"], result
assert result["dry_run"] is True, result
assert result["enqueued"], result
node = graph["nodes"][0]
assert node.get("status") != "dispatched", node
assert node.get("dispatch_id") is None, node
assert result["enqueued"][0]["queue"]["result"] == "dry_run", result
print("python_dry_run_ok")
PY

before_sha="$(shasum -a 256 "$TMPDIR_TEST/graph.json" | awk '{print $1}')"
SOLAR_GRAPH_DISPATCH_FAKE_WORKERS=1 python3 "$HARNESS_DIR_REAL/lib/graph_node_dispatcher.py" dispatch-ready --graph "$TMPDIR_TEST/graph.json" --dry-run >/tmp/graph-dispatch-dry-run.json
after_sha="$(shasum -a 256 "$TMPDIR_TEST/graph.json" | awk '{print $1}')"
[[ "$before_sha" == "$after_sha" ]] || fail "graph-dispatch --dry-run mutated graph file"

python3 - /tmp/graph-dispatch-dry-run.json <<'PY'
import json
import sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
assert d["ok"], d
assert d["enqueue"]["dry_run"] is True, d
assert d["drain"]["processed"] == 1, d
assert d["drain"]["results"][0]["dry_run"] is True, d
assert d["drain"]["results"][0]["graph_updated"] is False, d
print("dispatcher_dry_run_ok")
PY

echo "PASS graph dispatch dry-run no mutate"
