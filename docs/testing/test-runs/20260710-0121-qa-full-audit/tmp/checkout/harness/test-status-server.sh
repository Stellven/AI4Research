#!/usr/bin/env bash
# test-status-server.sh — Smoke tests for lib/symphony/status-server.py
# Sprint: sprint-20260507-symphony3 / S4

set -eu

HARNESS_DIR="${HARNESS_DIR:-$HOME/.solar/harness}"
SS_PY="$HARNESS_DIR/lib/symphony/status-server.py"

# ── Safety guards ──
[[ "${SESSION_NAME:-}" == "solar-harness" ]] && {
  echo "REFUSE: cannot run tests on live solar-harness session"; exit 1
}

# ── Find an available port ──
find_free_port() {
  local port
  for port in $(seq 19001 19020); do
    if ! lsof -i ":$port" -sTCP:LISTEN -t >/dev/null 2>&1; then
      echo "$port"; return 0
    fi
  done
  echo "19001"
}

TEST_PORT=$(find_free_port)

# ── Test isolation: temp harness dir ──
TEST_TMP=$(mktemp -d)
trap 'kill "$SS_PID" 2>/dev/null || true; rm -rf "$TEST_TMP"' EXIT

export HARNESS_DIR="$TEST_TMP"
mkdir -p "$TEST_TMP/events" "$TEST_TMP/sprints" "$TEST_TMP/run"

# Seed a fake active sprint
cat > "$TEST_TMP/sprints/sprint-test-smoke.status.json" <<'EOF'
{"id":"sprint-test-smoke","status":"active","phase":"build","round":1,"title":"Smoke Test Sprint","handoff_to":"evaluator"}
EOF

# Seed a fake event
cat > "$TEST_TMP/events/all.jsonl" <<'EOF'
{"ts":"2026-05-07T12:00:00Z","sprint_id":"sprint-test-smoke","actor":"coordinator","event":"dispatch_sent","severity":"info","payload":{}}
EOF

# ── Override PORT_RANGE in status-server.py by patching dynamically ──
SS_PATCHED="$TEST_TMP/status-server-test.py"
sed "s/PORT_RANGE = range(8765, 8776)/PORT_RANGE = range($TEST_PORT, $((TEST_PORT+2)))/" \
  "$SS_PY" > "$SS_PATCHED"

# Start server
python3 "$SS_PATCHED" &
SS_PID=$!

# Wait up to 5s for server to be ready
BASE_URL="http://127.0.0.1:$TEST_PORT"
for i in $(seq 1 10); do
  if curl -s "$BASE_URL/healthz" >/dev/null 2>&1; then break; fi
  sleep 0.5
done

# ── Test framework ──
PASS=0
FAIL=0

assert() {
  local desc="$1" expr="$2"
  if eval "$expr" 2>/dev/null; then
    echo "  ✅ PASS: $desc"
    (( PASS++ )) || true
  else
    echo "  ❌ FAIL: $desc"
    (( FAIL++ )) || true
  fi
}

echo "=== test-status-server.sh (port=$TEST_PORT) ==="
echo ""

# ── TC1: /healthz ──
echo "TC1: GET /healthz returns 'ok'"
HEALTH=$(curl -s "$BASE_URL/healthz" 2>/dev/null || echo "FAIL")
assert "/healthz returns ok" '[[ "$HEALTH" == "ok" ]]'
echo ""

# ── TC2: /status returns valid JSON ──
echo "TC2: GET /status returns valid JSON"
STATUS_BODY=$(curl -s "$BASE_URL/status" 2>/dev/null || echo "{}")
assert "/status returns valid JSON" 'python3 -c "import json,sys; json.loads(sys.argv[1])" "$STATUS_BODY"'
assert "/status has current_sprint key" 'python3 -c "import json,sys; d=json.loads(sys.argv[1]); assert \"current_sprint\" in d" "$STATUS_BODY"'
assert "/status has kpi key" 'python3 -c "import json,sys; d=json.loads(sys.argv[1]); assert \"kpi\" in d" "$STATUS_BODY"'
assert "/status has recent_events key" 'python3 -c "import json,sys; d=json.loads(sys.argv[1]); assert \"recent_events\" in d" "$STATUS_BODY"'
assert "/status has main_screen key" 'python3 -c "import json,sys; d=json.loads(sys.argv[1]); assert \"main_screen\" in d and \"panes\" in d[\"main_screen\"]" "$STATUS_BODY"'
assert "/status has lab_screen key" 'python3 -c "import json,sys; d=json.loads(sys.argv[1]); assert \"lab_screen\" in d and \"panes\" in d[\"lab_screen\"]" "$STATUS_BODY"'
assert "main_screen separates runtime/assignment/artifact" 'python3 -c "
import json,sys
d=json.loads(sys.argv[1])
p=d[\"main_screen\"][\"panes\"][0]
assert \"runtime_state\" in p and \"assignment\" in p and \"artifact\" in p
" "$STATUS_BODY"'
echo ""

# ── TC3: /status current_sprint reflects seeded sprint ──
echo "TC3: /status current_sprint matches seeded active sprint"
assert "sprint_id = sprint-test-smoke" 'python3 -c "
import json,sys
d=json.loads(sys.argv[1])
assert d[\"current_sprint\"].get(\"sprint_id\") == \"sprint-test-smoke\"
" "$STATUS_BODY"'
assert "status = active" 'python3 -c "
import json,sys
d=json.loads(sys.argv[1])
assert d[\"current_sprint\"].get(\"status\") == \"active\"
" "$STATUS_BODY"'
echo ""

# ── TC3b: terminal sprint must not masquerade as current work ──
echo "TC3b: /status shows idle when only terminal sprints exist"
cat > "$TEST_TMP/sprints/sprint-test-smoke.status.json" <<'EOF'
{"id":"sprint-test-smoke","status":"passed","phase":"finalized","round":1,"title":"Smoke Test Sprint","handoff_to":"done"}
EOF
STATUS_IDLE_BODY=$(curl -s "$BASE_URL/status" 2>/dev/null || echo "{}")
assert "current_sprint is idle when no active sprint exists" 'python3 -c "
import json,sys
d=json.loads(sys.argv[1])
sp=d[\"current_sprint\"]
assert sp.get(\"sprint_id\") == \"\"
assert sp.get(\"status\") == \"idle\"
assert sp.get(\"phase\") == \"no_active_sprint\"
assert sp.get(\"recent_completed\", {}).get(\"sprint_id\") == \"sprint-test-smoke\"
" "$STATUS_IDLE_BODY"'
echo ""

# ── TC4: /events returns array ──
echo "TC4: GET /events returns JSON array"
EVENTS_BODY=$(curl -s "$BASE_URL/events" 2>/dev/null || echo "[]")
assert "/events returns JSON array" 'python3 -c "import json,sys; d=json.loads(sys.argv[1]); assert isinstance(d,list)" "$EVENTS_BODY"'
assert "/events has at least 1 event" 'python3 -c "import json,sys; d=json.loads(sys.argv[1]); assert len(d)>=1" "$EVENTS_BODY"'
echo ""

# ── TC5: /events?limit=1 honors limit ──
echo "TC5: GET /events?limit=1 returns at most 1 event"
EVENTS_LIMITED=$(curl -s "$BASE_URL/events?limit=1" 2>/dev/null || echo "[]")
assert "limit=1 returns ≤1 events" 'python3 -c "import json,sys; d=json.loads(sys.argv[1]); assert len(d)<=1" "$EVENTS_LIMITED"'
echo ""

# ── TC6: / returns HTML ──
echo "TC6: GET / returns HTML page"
HTML=$(curl -s "$BASE_URL/" 2>/dev/null || echo "")
assert "/ contains DOCTYPE" 'echo "$HTML" | grep -qi "DOCTYPE"'
assert "/ contains Solar Harness Status" 'echo "$HTML" | grep -qi "Solar Harness Status"'
echo ""

# ── TC7: /404 returns 404 ──
echo "TC7: GET /nonexistent returns 404"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/nonexistent" 2>/dev/null || echo "0")
assert "nonexistent path returns 404" '[[ "$HTTP_CODE" == "404" ]]'
echo ""

# ── Summary ──
echo "=== Results: PASS=$PASS FAIL=$FAIL ==="
[[ "$FAIL" -eq 0 ]] && exit 0 || exit 1
