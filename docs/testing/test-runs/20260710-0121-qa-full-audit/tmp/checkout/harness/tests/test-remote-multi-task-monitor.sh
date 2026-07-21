#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MONITOR="$ROOT/harness/lib/remote_multi_task_monitor.py"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

assert_json_expr() {
  local file="$1"
  local expr="$2"
  python3 - "$file" "$expr" <<'PY'
import json, sys
path, expr = sys.argv[1:3]
data = json.load(open(path, encoding="utf-8"))
if not eval(expr, {"data": data}):
    raise SystemExit(f"assertion failed: {expr}\n{json.dumps(data, ensure_ascii=False, indent=2)[:2000]}")
PY
}

write_completed_fixture() {
  local dir="$1"
  mkdir -p "$dir/run/multi-task/mt-ok" "$dir/sprints"
  cat >"$dir/run/multi-task/mt-ok/status.json" <<'JSON'
{"id":"mt-ok","status":"completed","sprint_id":"sprint-ok","node_id":"N1","graph":"FIXTURE_GRAPH","window":"mt-ok","updated_at":"2026-05-20T11:58:00Z"}
JSON
  cat >"$dir/run/multi-task/mt-ok/output.log" <<'LOG'
completed
LOG
  cat >"$dir/sprints/sprint-ok.task_graph.json" <<'JSON'
{"sprint_id":"sprint-ok","nodes":[{"id":"N1","status":"reviewing","depends_on":[],"goal":"smoke"}],"node_results":{"N1":{"status":"reviewing"}}}
JSON
  python3 - "$dir" <<'PY'
import json, pathlib, sys
root = pathlib.Path(sys.argv[1])
status = root / "run/multi-task/mt-ok/status.json"
graph = root / "sprints/sprint-ok.task_graph.json"
data = json.loads(status.read_text())
data["graph"] = str(graph)
status.write_text(json.dumps(data, ensure_ascii=False) + "\n")
(root / "tmux_windows.json").write_text(json.dumps(["mt-ok"]) + "\n")
PY
}

write_stale_fixture() {
  local dir="$1"
  mkdir -p "$dir/run/multi-task/mt-stale" "$dir/sprints"
  cat >"$dir/run/multi-task/mt-stale/status.json" <<'JSON'
{"id":"mt-stale","status":"running","sprint_id":"sprint-stale","node_id":"N1","graph":"FIXTURE_GRAPH","window":"mt-stale","started_at":"2026-05-20T10:00:00Z","updated_at":"2026-05-20T10:10:00Z"}
JSON
  cat >"$dir/run/multi-task/mt-stale/output.log" <<'LOG'
working before stall
LOG
  touch -t 202605201010 "$dir/run/multi-task/mt-stale/output.log"
  cat >"$dir/sprints/sprint-stale.task_graph.json" <<'JSON'
{"sprint_id":"sprint-stale","nodes":[{"id":"N1","status":"running","depends_on":[],"goal":"stale node"}],"node_results":{"N1":{"status":"running"}}}
JSON
  python3 - "$dir" <<'PY'
import json, pathlib, sys
root = pathlib.Path(sys.argv[1])
status = root / "run/multi-task/mt-stale/status.json"
graph = root / "sprints/sprint-stale.task_graph.json"
data = json.loads(status.read_text())
data["graph"] = str(graph)
status.write_text(json.dumps(data, ensure_ascii=False) + "\n")
(root / "tmux_windows.json").write_text("[]\n")
PY
}

write_ready_idle_fixture() {
  local dir="$1"
  mkdir -p "$dir/run/multi-task" "$dir/sprints"
  cat >"$dir/sprints/sprint-ready.task_graph.json" <<'JSON'
{"sprint_id":"sprint-ready","nodes":[{"id":"N1","depends_on":[],"goal":"ready"}],"node_results":{}}
JSON
}

write_drift_fixture() {
  local dir="$1"
  mkdir -p "$dir/run/multi-task" "$dir/sprints"
  cat >"$dir/sprints/sprint-drift.task_graph.json" <<'JSON'
{"sprint_id":"sprint-drift","nodes":[{"id":"N1","status":"pending","depends_on":[],"goal":"drift"}],"node_results":{"N1":{"status":"passed"}}}
JSON
}

completed="$TMP/completed"
write_completed_fixture "$completed"
python3 "$MONITOR" --fixture-dir "$completed" --local-harness-dir "$TMP/local-ok" --now 2026-05-20T12:00:00Z --json >"$TMP/completed.json"
assert_json_expr "$TMP/completed.json" "data['ok'] is True and data['findings'] == [] and data['actions'] == []"

stale="$TMP/stale"
write_stale_fixture "$stale"
python3 "$MONITOR" --fixture-dir "$stale" --local-harness-dir "$TMP/local-stale" --now 2026-05-20T12:00:00Z --json >"$TMP/stale.json" || true
assert_json_expr "$TMP/stale.json" "data['ok'] is False and any(f['type']=='stale_task' for f in data['findings']) and data['artifacts'].get('report')"
test -f "$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["artifacts"]["report"])' "$TMP/stale.json")"
test -f "$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["artifacts"]["task_graph"])' "$TMP/stale.json")"

ready="$TMP/ready"
write_ready_idle_fixture "$ready"
python3 "$MONITOR" --fixture-dir "$ready" --local-harness-dir "$TMP/local-ready" --now 2026-05-20T12:00:00Z --apply --dry-run --json >"$TMP/ready.json"
assert_json_expr "$TMP/ready.json" "any(a['type']=='start_ready_graph' and a['dry_run'] for a in data['actions'])"

drift="$TMP/drift"
write_drift_fixture "$drift"
python3 "$MONITOR" --fixture-dir "$drift" --local-harness-dir "$TMP/local-drift" --now 2026-05-20T12:00:00Z --apply --dry-run --json >"$TMP/drift.json"
assert_json_expr "$TMP/drift.json" "any(a['type']=='repair_graph_drift' and a['dry_run'] for a in data['actions'])"

echo "remote_multi_task_monitor tests passed"
