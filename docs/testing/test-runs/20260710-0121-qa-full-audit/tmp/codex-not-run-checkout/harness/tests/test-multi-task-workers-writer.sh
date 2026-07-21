#!/usr/bin/env bash
# Regression: tools/multi_task_workers_writer.py emits a valid
# state/multi-task-workers.json (schema multi_task_screen.workers.v1)
# across 3 scenarios:
#   1. idle           — only autopilot pane ledger, no events tail.
#   2. active-sprint  — events tail names one pane + sprint_id.
#   3. multi-worker   — multiple panes, multiple sprints, bounded tail.
#
# Exits 0 iff every scenario passes the structural and semantic assertions.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WRITER="${ROOT}/tools/multi_task_workers_writer.py"

if [ ! -f "${WRITER}" ]; then
    printf 'FAIL: writer not found at %s\n' "${WRITER}" >&2
    exit 1
fi

TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

PASS=0
FAIL=0

assert_json() {
    local label="$1" path="$2" pyexpr="$3"
    if python3 -c "
import json, sys
data = json.load(open('${path}'))
${pyexpr}
" 2>/tmp/workers_test.err; then
        printf '  PASS  %s\n' "${label}"
        PASS=$((PASS + 1))
    else
        printf '  FAIL  %s\n    %s\n' "${label}" "$(cat /tmp/workers_test.err)" >&2
        FAIL=$((FAIL + 1))
    fi
}

run_scenario() {
    local scenario="$1"
    local state_dir="${TMP}/${scenario}"
    mkdir -p "${state_dir}"
    local out="${state_dir}/multi-task-workers.json"

    python3 "${WRITER}" \
        --state-dir "${state_dir}" \
        --out "${out}" \
        --max-lookback 500 \
        >/dev/null

    if [ ! -s "${out}" ]; then
        printf 'FAIL  %s: writer produced no output\n' "${scenario}" >&2
        FAIL=$((FAIL + 1))
        return 1
    fi

    assert_json "${scenario}: schema_version pinned" "${out}" \
        "assert data['schema_version'] == 'multi_task_screen.workers.v1', data.get('schema_version')"
    assert_json "${scenario}: top-level shape" "${out}" \
        "assert 'workers' in data and isinstance(data['workers'], list)
assert 'generated_at' in data and isinstance(data['generated_at'], str)
assert 'lookback' in data and isinstance(data['lookback'], int) and data['lookback'] <= 500"

    if [ "${scenario}" != "idle-empty" ]; then
        assert_json "${scenario}: every worker has v1 keys" "${out}" \
            "required = {'id', 'role', 'current_sprint', 'last_event_ts', 'low_confidence'}
for w in data['workers']:
    missing = required - set(w.keys())
    assert not missing, f'worker {w} missing keys {missing}'
    assert isinstance(w['id'], str) and w['id']
    assert isinstance(w['role'], str)
    assert isinstance(w['low_confidence'], bool)
    assert w['current_sprint'] is None or isinstance(w['current_sprint'], str)
    assert w['last_event_ts'] is None or isinstance(w['last_event_ts'], str)"
    fi
}

# ----------------------------------------------------------------------
# Scenario 0 (negative): no autopilot + no events → workers=[], schema OK
# ----------------------------------------------------------------------
printf '\n[scenario 0] idle-empty (no autopilot, no events)\n'
run_scenario "idle-empty"
assert_json "idle-empty: workers list is empty" \
    "${TMP}/idle-empty/multi-task-workers.json" \
    "assert data['workers'] == [], data['workers']"

# ----------------------------------------------------------------------
# Scenario 1: idle — 4 panes in autopilot ledger, no events.
# ----------------------------------------------------------------------
printf '\n[scenario 1] idle\n'
mkdir -p "${TMP}/idle"
cat >"${TMP}/idle/autopilot-state.json" <<'JSON'
{
  "pane": {
    "solar-harness:0.0": {"hash": "aaa", "seen_at": 1779000000.0, "role": "pm"},
    "solar-harness:0.1": {"hash": "bbb", "seen_at": 1779000001.0, "role": "planner"},
    "solar-harness:0.2": {"hash": "ccc", "seen_at": 1779000002.0, "role": "builder"},
    "solar-harness:0.3": {"hash": "ddd", "seen_at": 1779000003.0, "role": "evaluator"}
  }
}
JSON
: >"${TMP}/idle/events.jsonl"

run_scenario "idle"
assert_json "idle: exactly 4 workers" \
    "${TMP}/idle/multi-task-workers.json" \
    "assert len(data['workers']) == 4, len(data['workers'])"
assert_json "idle: all panes flagged low_confidence (no event evidence)" \
    "${TMP}/idle/multi-task-workers.json" \
    "assert all(w['low_confidence'] is True for w in data['workers']), [w['low_confidence'] for w in data['workers']]"
assert_json "idle: roles preserved from autopilot ledger" \
    "${TMP}/idle/multi-task-workers.json" \
    "roles = {w['id']: w['role'] for w in data['workers']}
assert roles['solar-harness:0.0'] == 'pm', roles
assert roles['solar-harness:0.2'] == 'builder', roles"
assert_json "idle: last_event_ts derived from autopilot seen_at (ISO-8601)" \
    "${TMP}/idle/multi-task-workers.json" \
    "import re
for w in data['workers']:
    assert isinstance(w['last_event_ts'], str), w
    assert re.match(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\$', w['last_event_ts']), w['last_event_ts']
assert all(w['current_sprint'] is None for w in data['workers'])"

# ----------------------------------------------------------------------
# Scenario 2: active-sprint — events tail flips one pane to active.
# ----------------------------------------------------------------------
printf '\n[scenario 2] active-sprint\n'
mkdir -p "${TMP}/active-sprint"
cat >"${TMP}/active-sprint/autopilot-state.json" <<'JSON'
{
  "pane": {
    "solar-harness:0.0": {"hash": "aaa", "seen_at": 1779000000.0, "role": "pm"},
    "solar-harness:0.2": {"hash": "ccc", "seen_at": 1779000002.0, "role": "builder"}
  }
}
JSON
cat >"${TMP}/active-sprint/events.jsonl" <<'JSONL'
{"ts": "2026-05-21T11:00:00Z", "event": "intent_matched", "actor": "intent-adapter"}
{"ts": "2026-05-21T11:05:00Z", "event": "dispatch_sent", "pane": "solar-harness:0.2", "sprint_id": "sprint-20260520-foo", "role": "builder"}
JSONL

run_scenario "active-sprint"
assert_json "active-sprint: builder pane lifted out of low_confidence" \
    "${TMP}/active-sprint/multi-task-workers.json" \
    "by_id = {w['id']: w for w in data['workers']}
assert by_id['solar-harness:0.2']['low_confidence'] is False, by_id['solar-harness:0.2']
assert by_id['solar-harness:0.2']['current_sprint'] == 'sprint-20260520-foo', by_id['solar-harness:0.2']
assert by_id['solar-harness:0.2']['last_event_ts'] == '2026-05-21T11:05:00Z', by_id['solar-harness:0.2']
assert by_id['solar-harness:0.0']['low_confidence'] is True
assert by_id['solar-harness:0.0']['current_sprint'] is None"

assert_json "active-sprint: pane absent from events keeps autopilot seen_at" \
    "${TMP}/active-sprint/multi-task-workers.json" \
    "by_id = {w['id']: w for w in data['workers']}
import re
assert re.match(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\$', by_id['solar-harness:0.0']['last_event_ts'] or '')"

# ----------------------------------------------------------------------
# Scenario 3: multi-worker — multiple panes, multiple sprints, AND ensure
#   the writer's bounded-tail contract holds (≤500 lines lookback).
# ----------------------------------------------------------------------
printf '\n[scenario 3] multi-worker\n'
mkdir -p "${TMP}/multi-worker"
cat >"${TMP}/multi-worker/autopilot-state.json" <<'JSON'
{
  "pane": {
    "solar-harness:0.0":     {"hash": "h0", "seen_at": 1779100000.0, "role": "pm"},
    "solar-harness:0.1":     {"hash": "h1", "seen_at": 1779100001.0, "role": "planner"},
    "solar-harness:0.2":     {"hash": "h2", "seen_at": 1779100002.0, "role": "builder"},
    "solar-harness:0.3":     {"hash": "h3", "seen_at": 1779100003.0, "role": "evaluator"},
    "solar-harness-lab:0.0": {"hash": "l0", "seen_at": 1779100004.0, "role": "lab"}
  }
}
JSON

# Build a synthetic events.jsonl > 500 lines to prove bounded tail works:
#   - 800 stale lines mentioning pane ':0.9' / sprint 'sprint-OLD-stale' are
#     placed BEFORE the meaningful tail; with max-lookback=10 the writer
#     must drop them and ':0.9' must NOT appear in workers[].
#   - 600 inert noise lines (no pane key) verify the tail is fed without
#     blowing memory or contaminating workers[].
#   - The final 5 meaningful events are the only pane-bearing records inside
#     the bounded window.
python3 - <<PY
from pathlib import Path
p = Path("${TMP}/multi-worker/events.jsonl")
lines = []
# 800 stale pane-bearing lines that MUST fall outside the bounded window.
for i in range(800):
    lines.append('{"ts":"2026-01-01T00:00:00Z","event":"stale","pane":"solar-harness:0.9","sprint_id":"sprint-OLD-stale"}')
# 600 inert noise lines (no pane / no sprint) — within window but irrelevant.
for i in range(600):
    lines.append('{"ts":"2026-05-20T12:00:00Z","event":"intent_matched","actor":"intent-adapter"}')
# Final 5 meaningful events: only these may shape workers[].
lines.append('{"ts":"2026-05-21T10:00:00Z","event":"dispatch_sent","pane":"solar-harness:0.1","sprint_id":"sprint-planner-A","role":"planner"}')
lines.append('{"ts":"2026-05-21T10:05:00Z","event":"dispatch_sent","pane":"solar-harness:0.2","sprint_id":"sprint-builder-B","role":"builder"}')
lines.append('{"ts":"2026-05-21T10:10:00Z","event":"dispatch_sent","pane":"solar-harness:0.3","sprint_id":"sprint-evaluator-C","role":"evaluator"}')
lines.append('{"ts":"2026-05-21T10:15:00Z","event":"dispatch_sent","pane":"solar-harness-lab:0.0","sprint_id":"sprint-lab-D","role":"lab"}')
# Update one pane twice — last write wins per pane.
lines.append('{"ts":"2026-05-21T10:20:00Z","event":"dispatch_sent","pane":"solar-harness:0.2","sprint_id":"sprint-builder-B2","role":"builder"}')
p.write_text("\n".join(lines) + "\n")
PY

run_scenario "multi-worker"
assert_json "multi-worker: 5 workers discovered (4 main + 1 lab)" \
    "${TMP}/multi-worker/multi-task-workers.json" \
    "assert len(data['workers']) == 5, [w['id'] for w in data['workers']]"
assert_json "multi-worker: each pane gets latest sprint (last-write-wins)" \
    "${TMP}/multi-worker/multi-task-workers.json" \
    "by_id = {w['id']: w for w in data['workers']}
assert by_id['solar-harness:0.1']['current_sprint'] == 'sprint-planner-A', by_id['solar-harness:0.1']
assert by_id['solar-harness:0.2']['current_sprint'] == 'sprint-builder-B2', by_id['solar-harness:0.2']
assert by_id['solar-harness:0.3']['current_sprint'] == 'sprint-evaluator-C', by_id['solar-harness:0.3']
assert by_id['solar-harness-lab:0.0']['current_sprint'] == 'sprint-lab-D', by_id['solar-harness-lab:0.0']"
assert_json "multi-worker: bounded tail dropped the 800 stale 'noise' lines" \
    "${TMP}/multi-worker/multi-task-workers.json" \
    "assert all('stale' not in (w['current_sprint'] or '') for w in data['workers']), data['workers']
ids = [w['id'] for w in data['workers']]
assert 'solar-harness:0.9' not in ids, ids"
assert_json "multi-worker: lookback budget reported and ≤ 500" \
    "${TMP}/multi-worker/multi-task-workers.json" \
    "assert data['lookback'] == 500, data['lookback']"
assert_json "multi-worker: panes without events stay low_confidence=true" \
    "${TMP}/multi-worker/multi-task-workers.json" \
    "by_id = {w['id']: w for w in data['workers']}
assert by_id['solar-harness:0.0']['low_confidence'] is True, by_id['solar-harness:0.0']"
assert_json "multi-worker: panes with events lifted to low_confidence=false" \
    "${TMP}/multi-worker/multi-task-workers.json" \
    "by_id = {w['id']: w for w in data['workers']}
for pid in ('solar-harness:0.1','solar-harness:0.2','solar-harness:0.3','solar-harness-lab:0.0'):
    assert by_id[pid]['low_confidence'] is False, (pid, by_id[pid])"

# ----------------------------------------------------------------------
# Hard cap: requesting an oversized lookback must clamp to 500.
# ----------------------------------------------------------------------
printf '\n[scenario 4] lookback hard cap\n'
mkdir -p "${TMP}/cap"
cat >"${TMP}/cap/autopilot-state.json" <<'JSON'
{ "pane": { "solar-harness:0.0": {"hash": "h", "seen_at": 1779100000.0, "role": "pm"} } }
JSON
: >"${TMP}/cap/events.jsonl"
python3 "${WRITER}" \
    --state-dir "${TMP}/cap" \
    --out "${TMP}/cap/multi-task-workers.json" \
    --max-lookback 9999 \
    >/dev/null
assert_json "lookback hard cap: 9999 clamped to 500" \
    "${TMP}/cap/multi-task-workers.json" \
    "assert data['lookback'] == 500, data['lookback']"

# ----------------------------------------------------------------------
# Summary
# ----------------------------------------------------------------------
printf '\n========================================\n'
printf 'multi_task_workers_writer regression\n'
printf '  PASS: %d\n' "${PASS}"
printf '  FAIL: %d\n' "${FAIL}"
printf '========================================\n'

if [ "${FAIL}" -gt 0 ]; then
    exit 1
fi
exit 0
