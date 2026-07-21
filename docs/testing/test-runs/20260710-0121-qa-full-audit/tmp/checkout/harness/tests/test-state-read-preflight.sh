#!/usr/bin/env bash
set -euo pipefail

REAL_HARNESS="${REAL_HARNESS:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
TMP_HOME="$(mktemp -d)"
trap 'rm -rf "$TMP_HOME"' EXIT

mkdir -p "$TMP_HOME/.solar/harness/sprints"

export HOME="$TMP_HOME"
export COORD_NO_MAIN=1
# shellcheck source=/dev/null
. "$REAL_HARNESS/coordinator.sh"

generate_dispatch "sprint-test" "建设者" "测试派发必须先 Read STATE"
DISPATCH_FILE="$TMP_HOME/.solar/harness/sprints/sprint-test.dispatch.md"
grep -q "SOLAR_STATE_READ_PREFLIGHT" "$DISPATCH_FILE"
grep -q "~/.solar/STATE.md" "$DISPATCH_FILE"

CUSTOM_FILE="$TMP_HOME/.solar/harness/sprints/custom.dispatch.md"
printf '# Custom Dispatch\n' > "$CUSTOM_FILE"
ensure_state_read_preflight "$CUSTOM_FILE"
test "$(grep -c "SOLAR_STATE_READ_PREFLIGHT" "$CUSTOM_FILE")" -eq 1
ensure_state_read_preflight "$CUSTOM_FILE"
test "$(grep -c "SOLAR_STATE_READ_PREFLIGHT" "$CUSTOM_FILE")" -eq 1

touch "$TMP_HOME/.solar/harness/sprints/sprint-finalized.finalized"
gate_check "sprint-finalized" "active"
gate_check "sprint-eval-passed" "eval_passed"

REAL_HARNESS="$REAL_HARNESS" python3 - <<'PY'
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(os.environ["REAL_HARNESS"]) / "lib"))
import graph_node_dispatcher as g

graph = {"sprint_id": "sprint-test"}
node = {
    "id": "n1",
    "goal": "verify preflight",
    "read_scope": [],
    "write_scope": ["/tmp/example"],
    "acceptance": ["dispatch contains preflight"],
}
payload = {"sprint_id": "sprint-test", "node": node, "graph": "/tmp/graph.json"}
builder = g.build_dispatch_text(payload, "solar-harness-lab:0.0")
evaluator = g.build_eval_dispatch_text(graph, "/tmp/graph.json", node, "solar-harness:0.3", "did")
assert "SOLAR_STATE_READ_PREFLIGHT" in builder
assert "~/.solar/STATE.md" in builder
assert "SOLAR_STATE_READ_PREFLIGHT" in evaluator
assert "~/.solar/STATE.md" in evaluator
PY

echo "ok"
