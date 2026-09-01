#!/usr/bin/env bash
# lib/state-mapper.sh — Canonical State Mapper (S1, Coordinator Control Plane v2)
#
# Exports:
#   map_canonical_state <sid>              → JSON on stdout, exit 0
#   validate_transition <from> <to> <event> → exit 0=allow / 1=deny / 2=unknown
#
# Rules:
#   - Pure read-only: never writes to sprint files
#   - Fail-open: unrecognised combos → lifecycle_state=unknown
#   - Parse errors → lifecycle_state=corrupt, exit 0 (not exception)
#   - stderr silent; diagnostics only via mapped_at + error_hint fields

set -euo pipefail

HARNESS_DIR="${HARNESS_DIR:-${SOLAR_HARNESS_DIR:-$HOME/.solar/harness}}"
STATE_MACHINE_JSON="$HARNESS_DIR/config/coordinator-state-machine.json"
SPRINTS_DIR="$HARNESS_DIR/sprints"

# ── internal: read field from status.json via python3 (jq fallback) ──────────

_sm_read_json() {
    local file="$1"
    python3 -c "
import json, sys
try:
    d = json.load(open('$file'))
    sys.stdout.write(json.dumps(d))
except Exception as e:
    sys.stdout.write(json.dumps({'_parse_error': str(e)}))
" 2>/dev/null
}

_sm_get_field() {
    local json="$1" field="$2"
    python3 -c "
import json, sys
try:
    d = json.loads(sys.argv[1])
    v = d.get(sys.argv[2], '')
    print(v if v is not None else '', end='')
except Exception:
    print('', end='')
" "$json" "$field" 2>/dev/null
}

_sm_task_graph_valid() {
    local sid="$1"
    local graph="${SPRINTS_DIR}/${sid}.task_graph.json"
    local typed_graph="${SPRINTS_DIR}/${sid}/planning/runtime/${sid}.task_graph.json"
    python3 - "$graph" "$typed_graph" "$sid" <<'PY' 2>/dev/null
import json
import sys
from pathlib import Path

legacy, typed, sid = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
for path, kind in ((legacy, "legacy"), (typed, "typed")):
    try:
        graph = json.loads(path.read_text())
    except Exception:
        continue
    if kind == "typed" and (
        graph.get("schema_version") != "solar.scheduler_runtime_projection.v1"
        or graph.get("sprint_id") != sid
    ):
        continue
    nodes = graph.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        continue
    if all(
        isinstance(node, dict)
        and str(node.get("id") or "").strip()
        and "write_scope" in node
        for node in nodes
    ):
        print("1", end="")
        raise SystemExit(0)
print("0", end="")
PY
}

_sm_typed_task_graph_valid() {
    local sid="$1"
    local graph="${SPRINTS_DIR}/${sid}/planning/runtime/${sid}.task_graph.json"
    python3 - "$graph" "$sid" <<'PY' 2>/dev/null
import json, sys
from pathlib import Path

try:
    graph = json.loads(Path(sys.argv[1]).read_text())
except Exception:
    print("0", end="")
    raise SystemExit(0)
nodes = graph.get("nodes")
valid = (
    graph.get("schema_version") == "solar.scheduler_runtime_projection.v1"
    and graph.get("sprint_id") == sys.argv[2]
    and isinstance(nodes, list)
    and bool(nodes)
    and all(
        isinstance(node, dict)
        and str(node.get("id") or "").strip()
        and "write_scope" in node
        for node in nodes
    )
)
print("1" if valid else "0", end="")
PY
}

# ── map_canonical_state ───────────────────────────────────────────────────────
#
# Usage: map_canonical_state <sid>
# Output: JSON {lifecycle_state, lifecycle_role, source_status, source_phase,
#               source_handoff_to, mapped_at, error_hint}

map_canonical_state() {
    local sid="$1"
    local sf="${SPRINTS_DIR}/${sid}.status.json"
    local now
    now=$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo "1970-01-01T00:00:00Z")

    if [[ ! -f "$sf" ]]; then
        python3 -c "
import json, sys
print(json.dumps({
    'lifecycle_state': 'corrupt',
    'lifecycle_role': 'none',
    'source_status': '',
    'source_phase': '',
    'source_handoff_to': '',
    'mapped_at': '$now',
    'error_hint': 'status.json not found: $sf'
}))"
        return 0
    fi

    local raw_json
    raw_json=$(_sm_read_json "$sf")

    # Parse error → corrupt
    if python3 -c "import json,sys; d=json.loads(sys.argv[1]); sys.exit(0 if '_parse_error' not in d else 1)" "$raw_json" 2>/dev/null; then
        : # ok
    else
        local err
        err=$(_sm_get_field "$raw_json" "_parse_error")
        python3 -c "
import json
print(json.dumps({
    'lifecycle_state': 'corrupt',
    'lifecycle_role': 'none',
    'source_status': '',
    'source_phase': '',
    'source_handoff_to': '',
    'mapped_at': '$now',
    'error_hint': 'parse error: $err'
}))"
        return 0
    fi

    local st phase handoff_to graph_valid typed_graph_valid
    st=$(_sm_get_field "$raw_json" "status")
    phase=$(_sm_get_field "$raw_json" "phase")
    handoff_to=$(_sm_get_field "$raw_json" "handoff_to")
    graph_valid=$(_sm_task_graph_valid "$sid")
    typed_graph_valid=$(_sm_typed_task_graph_valid "$sid")

    python3 -c "
import json, sys

raw = json.loads(sys.argv[1])
st = sys.argv[2]
phase = sys.argv[3]
handoff_to = sys.argv[4]
now = sys.argv[5]
graph_valid = sys.argv[6] == '1'
typed_graph_valid = sys.argv[7] == '1'

lc = 'unknown'
role = 'none'
hint = ''

# ── KEY: legacy combo mapping (order matters — most-specific first) ──────────

if st == 'drafting':
    if phase == 'prd_ready' and handoff_to == 'planner':
        lc = 'prd_ready'
        role = 'planner'
        hint = 'legacy fix: drafting+prd_ready+planner was mis-routed to PM'
    elif phase in ('planning_complete',):
        if graph_valid:
            lc = 'planning_complete'
            role = 'builder_main'
        else:
            lc = 'planner_blocked_missing_task_graph'
            role = 'planner'
            hint = 'planning_complete requires valid task_graph.json before builder route'
    elif phase in ('prd_ready',):
        lc = 'prd_ready'
        role = 'planner'
    else:
        lc = 'intake'
        role = 'pm'

elif st == 'active':
    if typed_graph_valid and phase in ('planning_complete', 'graph_dispatch_active'):
        lc = 'building' if phase == 'graph_dispatch_active' else 'planning_complete'
        role = 'scheduler'
    elif phase in ('planning_complete', 'planner_plan', 'plan_reviewed'):
        if graph_valid:
            lc = 'planning_complete'
        else:
            lc = 'planner_blocked_missing_task_graph'
            role = 'planner'
            hint = 'active/planning_complete requires valid task_graph.json before builder route'
    elif phase in ('g0_passed',):
        lc = 'building'
    elif phase in ('slices_dispatched', 's1_dispatched', 's2_dispatched', 's6_dispatched'):
        lc = 'building'
    elif phase in ('s0_dispatched', 's0_in_progress'):
        lc = 'building'
    elif phase in ('s0_ready_for_eval', 's1_ready_for_eval', 's2_ready_for_eval',
                   's3_ready_for_eval', 's4_ready_for_eval', 's5_ready_for_eval',
                   's6_ready_for_eval', 's7_ready_for_eval'):
        lc = 'build_complete'
        role = 'evaluator'
    elif phase in ('building', 'build_complete'):
        lc = 'building'
    else:
        # default: active with plan expected
        if graph_valid:
            lc = 'planning_complete'
        else:
            lc = 'planner_blocked_missing_task_graph'
            role = 'planner'
            hint = 'active default route requires valid task_graph.json before builder route'
    if role == 'none':
        role = 'builder_main'

elif st == 'planning':
    lc = 'planning'
    role = 'evaluator'

elif st == 'planning_complete':
    if graph_valid:
        lc = 'planning_complete'
        role = 'scheduler' if typed_graph_valid else 'builder_main'
    else:
        lc = 'planner_blocked_missing_task_graph'
        role = 'planner'
        hint = 'status=planning_complete requires valid task_graph.json before builder route'

elif st == 'approved':
    lc = 'planning_complete'
    role = 'builder_main'

elif st in ('reviewing', 'ready_for_review', 'architect_reviewing'):
    lc = 'build_complete'
    role = 'evaluator'

elif st in ('failed_review', 'architect_failed'):
    lc = 'blocked'
    role = 'builder_main'

elif st == 'building_parallel':
    lc = 'building'
    role = 'builder_main'

elif st == 'needs_human_review':
    lc = 'blocked'
    role = 'planner'

elif st in ('passed', 'done', 'eval_pass', 'finalized', 'superseded'):
    lc = 'done'
    role = 'none'

elif st == 'failed':
    lc = 'failed'
    role = 'none'

elif st == 'cancelled':
    lc = 'failed'
    role = 'none'

elif st == 'blocked':
    lc = 'blocked'
    role = 'planner'

elif st == 'queued':
    if handoff_to == 'evaluator':
        lc = 'build_complete'
        role = 'evaluator'
    elif phase in ('prd_ready',) or handoff_to == 'planner':
        lc = 'planning'
        role = 'planner'
    else:
        # contract_ready and legacy handoff_to=builder must still enter PM
        # intake unless workflow_guard proves PRD+Planner artifacts exist.
        lc = 'intake'
        role = 'pm'

else:
    lc = 'unknown'
    role = 'none'
    hint = f'unrecognised status: {st!r}'

out = {
    'lifecycle_state': lc,
    'lifecycle_role': role,
    'source_status': st,
    'source_phase': phase,
    'source_handoff_to': handoff_to,
    'mapped_at': now,
}
if hint:
    out['error_hint'] = hint

print(json.dumps(out))
" "$raw_json" "$st" "$phase" "$handoff_to" "$now" "$graph_valid" "$typed_graph_valid"
    return 0
}

# ── validate_transition ───────────────────────────────────────────────────────
#
# Usage: validate_transition <from_state> <to_state> <event>
# Exit:  0 = transition allowed
#        1 = transition denied (reason on stdout)
#        2 = transition unknown (not in table)
# Output: JSON {allowed, reason}

validate_transition() {
    local from_state="$1" to_state="$2" event="$3"

    python3 -c "
import json, sys

with open('$STATE_MACHINE_JSON') as f:
    sm = json.load(f)

from_state = sys.argv[1]
to_state   = sys.argv[2]
event      = sys.argv[3]

transitions = sm.get('transitions', [])
matched = []
for t in transitions:
    t_from = t.get('from', '')
    t_to   = t.get('to', '')
    t_ev   = t.get('event', '')
    if (t_from == '*' or t_from == from_state) and (not t_to or t_to == to_state):
        if not t_ev or t_ev == event or event in t_ev.split('|'):
            matched.append(t)

if not matched:
    # Check if reverse direction is known (deny explicitly)
    deny_check = [t for t in transitions if t.get('from') == to_state and t.get('to') == from_state]
    if deny_check:
        print(json.dumps({'allowed': False, 'reason': f'reverse transition {from_state}->{to_state} not in table; only {to_state}->{from_state} is known'}))
        sys.exit(1)
    print(json.dumps({'allowed': None, 'reason': f'no rule for {from_state}->{to_state} via {event}'}))
    sys.exit(2)

# Any match = allowed
t = matched[0]
print(json.dumps({'allowed': True, 'reason': f'matched rule {t.get(\"id\",\"?\")}', 'rule': t}))
sys.exit(0)
" "$from_state" "$to_state" "$event"
    return $?
}

# ── is_terminal_state ─────────────────────────────────────────────────────────
is_terminal_state() {
    local state="$1"
    case "$state" in
        done|failed|quarantined|superseded) return 0 ;;
        *) return 1 ;;
    esac
}

# ── is_corrupt_state ──────────────────────────────────────────────────────────
is_corrupt_state() {
    local state="$1"
    [[ "$state" == "corrupt" ]]
}
