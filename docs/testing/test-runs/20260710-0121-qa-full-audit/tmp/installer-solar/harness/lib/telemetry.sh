#!/usr/bin/env bash
# lib/telemetry.sh — Sprint telemetry: emit run metrics + topology degrade check
# sprint-20260503-195627: telemetry-driven optimization (RecursiveMAS v3 P2)
[[ -n "${TELEMETRY_LOADED:-}" ]] && return 0
TELEMETRY_LOADED=1

TELEMETRY_DIR="${HARNESS_DIR}/telemetry"
TELEMETRY_FILE="$TELEMETRY_DIR/runs.jsonl"
export TELEMETRY_FILE

_ensure_telemetry_dir() {
  mkdir -p "$TELEMETRY_DIR"
  [[ -f "$TELEMETRY_FILE" ]] || touch "$TELEMETRY_FILE"
}

# telemetry_emit_run <sid> <verdict> [fail_dones_json]
# verdict = passed|failed
# fail_dones_json = JSON array, e.g. '["D2","D5"]'
telemetry_emit_run() {
  local sid="$1" verdict="$2"
  local fail_dones="${3:-[]}"
  local sf="$SPRINTS_DIR/${sid}.status.json"
  [[ -f "$sf" ]] || return 1
  _ensure_telemetry_dir

  python3 - "$sf" "$sid" "$verdict" "$fail_dones" "$TELEMETRY_FILE" <<'PY'
import json, sys, datetime, os
sf, sid, verdict, fail_dones_json, tf = sys.argv[1:]
d = json.load(open(sf))
history = d.get('history', [])
start_entry = next((h for h in history if h.get('event') in ('auto_chain', 'new_sprint')), None)
start_ts = start_entry.get('ts', '') if start_entry else d.get('updated_at', '')
end_ts = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
try:
    dur = (datetime.datetime.fromisoformat(end_ts.replace('Z', '+00:00'))
         - datetime.datetime.fromisoformat(start_ts.replace('Z', '+00:00'))).total_seconds()
except Exception:
    dur = 0
try:
    fd = json.loads(fail_dones_json)
except Exception:
    fd = []
run = {
    "sid": sid,
    "topology": d.get("topology", "standard"),
    "rounds": d.get("round", 0),
    "start_ts": start_ts,
    "end_ts": end_ts,
    "duration_sec": round(dur, 1),
    "verdict": verdict,
    "fail_dones": fd,
    "total_dones": 0,
    "builder_persona": d.get("builder_persona", ""),
    "evaluator_persona": d.get("evaluator_persona", ""),
    "codex_reviewed": False
}
cf_path = sf.replace('.status.json', '.contract.md')
try:
    with open(cf_path) as f:
        run["total_dones"] = sum(1 for l in f if l.strip().startswith('- [ ]'))
except Exception:
    pass
line = json.dumps(run, ensure_ascii=False)
with open(tf, "a") as f:
    f.write(line + "\n")
print(f"telemetry: {sid} {verdict}")
PY
}

# _topology_degrade_check <topology>
# Returns "standard" if topology pass rate < 60% with >= 5 samples in 30 days
# Returns empty (no output) if no degradation needed
_topology_degrade_check() {
  local topo="$1"
  [[ "$topo" == "standard" || "$topo" == "research" ]] && return 0
  [[ -f "$TELEMETRY_FILE" ]] || return 0
  local threshold_days=30 min_samples=5
  local result
  result=$(python3 - "$topo" "$TELEMETRY_FILE" "$threshold_days" "$min_samples" <<'PY'
import json, sys, datetime
topo, tf, days, min_n = sys.argv[1:]
days, min_n = int(days), int(min_n)
cutoff = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)).isoformat()
runs = []
with open(tf) as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            runs.append(json.loads(line))
        except Exception:
            pass
recent = [r for r in runs if r.get("topology") == topo and r.get("start_ts", "") >= cutoff]
if len(recent) < min_n:
    sys.exit(0)
passed = sum(1 for r in recent if r.get("verdict") == "passed")
rate = passed / len(recent) * 100
if rate < 60:
    print("standard")
PY
)
  [[ -n "$result" ]] && echo "$result"
}
