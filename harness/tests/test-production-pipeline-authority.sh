#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

python3 - "$ROOT" <<'PY'
from pathlib import Path
import sys

root = Path(sys.argv[1])
intake = (root / "solar-harness.sh").read_text(encoding="utf-8")
gateway = (root / "lib" / "intent_gateway.py").read_text(encoding="utf-8")
adapter = (root / "tools" / "elastic_planner_adapter.py").read_text(encoding="utf-8")

region = intake[intake.index("intake_request()") : intake.index("new_sprint()")]
assert 'SOLAR_INTAKE_COMPAT_MODE:-}" == "legacy"' in region
assert 'production intake refused: LLM Intent Compiler did not produce an accepted IntentIR' in region
assert 'python3 "$HARNESS_DIR/lib/intent_consumer.py" consume' in region
assert '&& ! should_epic_decompose_request "$req"' not in region
assert '"cli_intake"' in gateway
assert "run_elastic_planning_request(" in adapter
assert "prepare_runtime_graph(" in adapter
PY

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/sprints"
python3 - "$TMP/sprints" <<'PY'
import json
from pathlib import Path
import sys

root = Path(sys.argv[1])
for sid, created in (("sprint-old", 99), ("sprint-new", 100)):
    (root / f"{sid}.status.json").write_text(
        json.dumps({"sprint_id": sid, "id": sid, "status": "drafting", "created_ts": created}) + "\n",
        encoding="utf-8",
    )
PY

COORD_NO_MAIN=1 \
HARNESS_DIR="$TMP" \
SOLAR_HARNESS_DIR="$TMP" \
SOLAR_COORDINATOR_ADMISSION_EPOCH=100 \
  source "$ROOT/coordinator.sh"

if coordinator_sprint_admitted "$TMP/sprints/sprint-old.status.json"; then
  echo "FAIL: historical sprint was admitted without permission" >&2
  exit 1
fi
coordinator_sprint_admitted "$TMP/sprints/sprint-new.status.json"
mkdir -p "$TMP/run/pane-leases"
python3 - "$TMP/run/pane-leases/live.json" <<'PY'
import json
from pathlib import Path
import sys
Path(sys.argv[1]).write_text(
    json.dumps({"sprint_id": "sprint-old", "dispatch_id": "live-1", "expires_at": "2999-01-01T00:00:00Z"}) + "\n",
    encoding="utf-8",
)
PY
coordinator_sprint_admitted "$TMP/sprints/sprint-old.status.json"
rm -f "$TMP/run/pane-leases/live.json"
SOLAR_COORDINATOR_ADMITTED_SPRINTS=sprint-old \
  coordinator_sprint_admitted "$TMP/sprints/sprint-old.status.json"

python3 - "$ROOT" "$TMP" <<'PY'
import importlib.util
import json
from pathlib import Path
import sys

root, temp = map(Path, sys.argv[1:3])
sys.path.insert(0, str(root / "lib"))
spec = importlib.util.spec_from_file_location("dispatch_ack_acceptance_test", root / "lib" / "graph_node_dispatcher.py")
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

module.HARNESS_DIR = temp
module.SPRINTS_DIR = temp / "sprints"
ack_dir = temp / "sprints" / "graph-acks"
ack_dir.mkdir(parents=True, exist_ok=True)
sid, node_id, pane, dispatch_id = "sprint-ack", "N0", "solar-harness:0.1", "dispatch-1"
(ack_dir / f"{sid}.{node_id}-submit-ack.json").write_text(
    json.dumps({"dispatch_id": dispatch_id, "submitted_at": "2026-08-28T00:00:00Z"}),
    encoding="utf-8",
)

stubs = {
    "_operator_terminal_result_closeout": lambda *args: None,
    "_pane_title": lambda *args: "",
    "_pane_tail": lambda *args: "",
    "_pane_dispatch_prompt_reason": lambda *args: "",
    "_pane_cooldown_reason": lambda *args: "",
    "_pane_runtime_unavailable_reason": lambda *args: "",
    "_pane_unavailable_reason": lambda *args: "",
    "_pane_tui_busy": lambda *args: False,
    "read_lease": lambda *args: None,
    "release_lease": lambda *args, **kwargs: {},
    "_append_dispatch_ledger": lambda *args, **kwargs: None,
    "_append_event": lambda *args, **kwargs: None,
    "_ledger_transition": lambda *args, **kwargs: None,
    "_record_node_runstate": lambda *args, **kwargs: None,
}
for name, value in stubs.items():
    setattr(module, name, value)

graph = {
    "sprint_id": sid,
    "nodes": [{"id": node_id, "status": "dispatched", "assigned_to": pane, "dispatch_id": dispatch_id, "depends_on": []}],
    "node_results": {node_id: {"status": "dispatched", "assigned_to": pane, "dispatch_id": dispatch_id}},
}
repairs = module._reconcile_existing_dispatches(graph, temp / "sprints" / f"{sid}.task_graph.json")
assert repairs and repairs[0]["reason"] == "stale_submit_ack_without_live_lease", repairs
assert graph["nodes"][0]["status"] == "pending", graph
assert "assigned_to" not in graph["nodes"][0]
assert "dispatch_id" not in graph["nodes"][0]

queue_path = module._queue_file(sid)
queue_path.write_text(
    json.dumps({
        "id": "queue-1",
        "sprint_id": sid,
        "intent": "graph_node|node_id=N0",
        "priority": 80,
        "enqueued_at": "2026-08-28T00:00:00Z",
        "consumed": False,
        "payload": {"node": {"id": "N0"}},
    }) + "\n",
    encoding="utf-8",
)
first_claim = module._pop_graph_queue_item(sid)
assert first_claim and first_claim.get("claim"), first_claim
stored = json.loads(queue_path.read_text(encoding="utf-8"))
assert stored["consumed"] is False and stored.get("claim"), stored
assert module._complete_graph_queue_claim(sid, first_claim, consumed=False)
released = json.loads(queue_path.read_text(encoding="utf-8"))
assert released["consumed"] is False and "claim" not in released, released
second_claim = module._pop_graph_queue_item(sid)
assert second_claim and second_claim["claim"]["id"] != first_claim["claim"]["id"]
assert module._complete_graph_queue_claim(sid, second_claim, consumed=True)
completed = json.loads(queue_path.read_text(encoding="utf-8"))
assert completed["consumed"] is True and "claim" not in completed, completed
PY

echo "PASS: production pipeline authority, session admission, and dispatch acceptance"
