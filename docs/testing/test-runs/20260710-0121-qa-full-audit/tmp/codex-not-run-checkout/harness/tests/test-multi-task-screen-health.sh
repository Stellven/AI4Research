#!/usr/bin/env bash
# tests/test-multi-task-screen-health.sh — S04 N3 regression tests
# Covers three scenarios: all-green, one-degraded, missing-input.
# Acceptance:
#   - state enum from multi_task_screen.health.v1
#   - capsules[].marker is a single ASCII char (len == 1)
#   - missing input → capsule.state=idle with explicit reason (not error)

set -euo pipefail

HARNESS_DIR="${HARNESS_DIR:-$HOME/.solar/harness}"
TOOL="$HARNESS_DIR/tools/multi_task_screen_health.py"

if [[ ! -f "$TOOL" ]]; then
    echo "FATAL: tool not found at $TOOL" >&2
    exit 99
fi

PASS=0
FAIL=0

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

OUT="$TMP_DIR/screen-health.json"

# ---- pass/fail helper ------------------------------------------------------

assert_ok() {
    local label="$1"
    local rc="$2"
    if [[ "$rc" -eq 0 ]]; then
        echo "  PASS  $label"
        PASS=$((PASS+1))
    else
        echo "  FAIL  $label  (rc=$rc)"
        FAIL=$((FAIL+1))
    fi
}

# Run a python assertion expression against $OUT.
# Usage: py_assert "<label>" "<expression that should be truthy>"
py_assert() {
    local label="$1"; shift
    local expr="$1"; shift
    local rc=0
    python3 - "$OUT" <<PY || rc=$?
import json, sys, re
d = json.loads(open(sys.argv[1]).read())
VALID_STATES = {"ok","warn","error","idle","active","blocked","dry_run","ready","working","pending"}
ok = bool(${expr})
sys.exit(0 if ok else 1)
PY
    assert_ok "$label" "$rc"
}

# Write a minimal model-registry-doctor-health.json
write_models() {
    local path="$1" ok="$2" status="$3"
    python3 - "$path" "$ok" "$status" <<'PY'
import json, sys
path, ok, status = sys.argv[1], sys.argv[2], sys.argv[3]
ok_bool = ok.lower() == "true"
json.dump({
    "ok": ok_bool,
    "status": status,
    "reason": "synthetic",
    "returncode": 0 if ok_bool else 1,
    "checked_at": "2026-05-21T00:00:00Z",
    "checked_at_epoch": 1779321600.0,
}, open(path, "w"), indent=2)
PY
}

write_knowledge() {
    local path="$1" ok="$2" status="$3"
    python3 - "$path" "$ok" "$status" <<'PY'
import json, sys
path, ok, status = sys.argv[1], sys.argv[2], sys.argv[3]
ok_bool = ok.lower() == "true"
json.dump({
    "ok": ok_bool,
    "status": status,
    "reason": "synthetic",
    "returncode": 0 if ok_bool else 1,
    "probes_passed": 9 if ok_bool else 1,
    "probes_failed": 0 if ok_bool else 9,
    "checked_at": "2026-05-21T00:00:00Z",
    "checked_at_epoch": 1779321600.0,
}, open(path, "w"), indent=2)
PY
}

write_integrations() {
    local path="$1" ok_count="$2" warn_count="$3" error_count="$4"
    python3 - "$path" "$ok_count" "$warn_count" "$error_count" <<'PY'
import json, sys
path, ok_n, warn_n, error_n = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
total = ok_n + warn_n + error_n
json.dump({
    "generated_at": "2026-05-21T00:00:00Z",
    "summary": {
        "ok": ok_n,
        "warn": warn_n,
        "error": error_n,
        "missing": 0,
        "total": total,
    },
    "integrations": [],
}, open(path, "w"), indent=2)
PY
}

run_aggregator() {
    python3 "$TOOL" --once --state-dir "$TMP_DIR" --output "$OUT" >/dev/null
}

# ---------------------------------------------------------------------------
# Scenario 1: all-green
# ---------------------------------------------------------------------------
echo
echo "Scenario 1 — all-green"
write_models "$TMP_DIR/model-registry-doctor-health.json" true ok
write_knowledge "$TMP_DIR/knowledge-probe-health.json" true ok
write_integrations "$TMP_DIR/external-integrations-last-probe.json" 23 0 0
run_aggregator

py_assert "schema_version == multi_task_screen.health.v1" \
    "d['schema_version']=='multi_task_screen.health.v1'"
py_assert "capsules length >= 3" "len(d['capsules'])>=3"
py_assert "verdict == ok" "d['verdict']=='ok'"
py_assert "every capsule.state in VALID_STATES" \
    "all(c['state'] in VALID_STATES for c in d['capsules'])"
py_assert "every capsule.marker is single ASCII char" \
    "all(isinstance(c['marker'],str) and len(c['marker'])==1 and ord(c['marker'])<128 for c in d['capsules'])"
py_assert "every capsule has {id,label,state,marker,mtime}" \
    "all(all(k in c for k in ('id','label','state','marker','mtime')) for c in d['capsules'])"
py_assert "all three capsule states == ok" \
    "[c['state'] for c in d['capsules']]==['ok','ok','ok']"

# ---------------------------------------------------------------------------
# Scenario 2: one-degraded (knowledge ok=false / status=warn → capsule state=warn)
# ---------------------------------------------------------------------------
echo
echo "Scenario 2 — one-degraded"
write_models "$TMP_DIR/model-registry-doctor-health.json" true ok
write_knowledge "$TMP_DIR/knowledge-probe-health.json" false warn
write_integrations "$TMP_DIR/external-integrations-last-probe.json" 22 1 0
run_aggregator

py_assert "models capsule still ok" \
    "next(c for c in d['capsules'] if c['id']=='models')['state']=='ok'"
py_assert "knowledge capsule state in {warn,error}" \
    "next(c for c in d['capsules'] if c['id']=='knowledge')['state'] in ('warn','error')"
py_assert "integrations capsule state == warn" \
    "next(c for c in d['capsules'] if c['id']=='integrations')['state']=='warn'"
py_assert "verdict in {warn,error}" \
    "d['verdict'] in ('warn','error')"
py_assert "every capsule.marker still single ASCII char" \
    "all(len(c['marker'])==1 and ord(c['marker'])<128 for c in d['capsules'])"

# ---------------------------------------------------------------------------
# Scenario 3: missing-input (delete models file → capsule state=idle + reason)
# ---------------------------------------------------------------------------
echo
echo "Scenario 3 — missing-input"
rm -f "$TMP_DIR/model-registry-doctor-health.json"
# keep the other two valid + green so we can isolate the idle behaviour
write_knowledge "$TMP_DIR/knowledge-probe-health.json" true ok
write_integrations "$TMP_DIR/external-integrations-last-probe.json" 23 0 0
run_aggregator

py_assert "models capsule state == idle" \
    "next(c for c in d['capsules'] if c['id']=='models')['state']=='idle'"
py_assert "models capsule reason contains 'file missing'" \
    "'file missing' in next(c for c in d['capsules'] if c['id']=='models').get('reason','')"
py_assert "models capsule mtime is null" \
    "next(c for c in d['capsules'] if c['id']=='models')['mtime'] is None"
py_assert "missing did NOT escalate to error (state != error)" \
    "next(c for c in d['capsules'] if c['id']=='models')['state']!='error'"
py_assert "verdict reflects idle escalation but not error" \
    "d['verdict'] in ('ok','idle')"

# ---------------------------------------------------------------------------
# Wrap up
# ---------------------------------------------------------------------------
echo
echo "Results: PASS=$PASS FAIL=$FAIL"
if [[ $FAIL -gt 0 ]]; then
    exit 1
fi
exit 0
