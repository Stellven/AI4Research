#!/usr/bin/env bash
# tests/test-state-mapper.sh — Canonical State Mapper regression tests
# sprint-20260508-coordinator-control-plane-v2 S1

set -euo pipefail

HARNESS_DIR="${HARNESS_DIR:-$HOME/.solar/harness}"
SPRINTS_DIR="$HARNESS_DIR/sprints"
LIB="$HARNESS_DIR/lib/state-mapper.sh"

# shellcheck source=/dev/null
. "$LIB"

PASS=0
FAIL=0
TMPDIR_FIXTURES=$(mktemp -d)
trap 'rm -rf "$TMPDIR_FIXTURES"' EXIT

# ── helper ────────────────────────────────────────────────────────────────────

make_fixture() {
    local sid="$1" status="$2" phase="${3:-}" handoff_to="${4:-}"
    local sf="$TMPDIR_FIXTURES/${sid}.status.json"
    python3 -c "
import json
d = {'id': '$sid', 'status': '$status'}
if '$phase': d['phase'] = '$phase'
if '$handoff_to': d['handoff_to'] = '$handoff_to'
print(json.dumps(d))
" > "$sf"
    echo "$sf"
}

make_task_graph() {
    local sid="$1"
    cat > "$TMPDIR_FIXTURES/${sid}.task_graph.json" <<'JSON'
{"nodes":[{"id":"N1","title":"fixture","write_scope":["sprints/fixture.handoff.md"]}]}
JSON
}

check() {
    local label="$1" got="$2" want_lc="$3" want_role="$4"
    local got_lc got_role
    got_lc=$(python3 -c "import json,sys; d=json.loads(sys.argv[1]); print(d.get('lifecycle_state',''))" "$got" 2>/dev/null)
    got_role=$(python3 -c "import json,sys; d=json.loads(sys.argv[1]); print(d.get('lifecycle_role',''))" "$got" 2>/dev/null)

    if [[ "$got_lc" == "$want_lc" && "$got_role" == "$want_role" ]]; then
        echo "  ✅ $label → $got_lc / $got_role"
        PASS=$((PASS+1))
    else
        echo "  ❌ $label"
        echo "       want: lifecycle_state=$want_lc lifecycle_role=$want_role"
        echo "        got: lifecycle_state=$got_lc  lifecycle_role=$got_role"
        FAIL=$((FAIL+1))
    fi
}

# Override SPRINTS_DIR so map_canonical_state reads from our tmp fixtures
SPRINTS_DIR="$TMPDIR_FIXTURES"

echo "=== test-state-mapper.sh ==="

# ── Fixture 1: KEY BUG FIX — drafting+prd_ready+planner must → prd_ready ─────
make_fixture "fx1" "drafting" "prd_ready" "planner" >/dev/null
result=$(map_canonical_state "fx1")
check "drafting+prd_ready+handoff_to=planner (KEY BUG FIX)" "$result" "prd_ready" "planner"

# ── Fixture 2: drafting+no phase → intake/pm ──────────────────────────────────
make_fixture "fx2" "drafting" "" "" >/dev/null
result=$(map_canonical_state "fx2")
check "drafting+no_phase → intake/pm" "$result" "intake" "pm"

# ── Fixture 3: drafting+prd_ready (no handoff_to) → prd_ready/planner ────────
make_fixture "fx3" "drafting" "prd_ready" "" >/dev/null
result=$(map_canonical_state "fx3")
check "drafting+prd_ready (no handoff_to) → prd_ready/planner" "$result" "prd_ready" "planner"

# ── Fixture 4: active → planning_complete/builder_main ───────────────────────
make_fixture "fx4" "active" "" "" >/dev/null
make_task_graph "fx4"
result=$(map_canonical_state "fx4")
check "active → planning_complete/builder_main" "$result" "planning_complete" "builder_main"

# ── Fixture 5: reviewing → build_complete/evaluator ──────────────────────────
make_fixture "fx5" "reviewing" "" "" >/dev/null
result=$(map_canonical_state "fx5")
check "reviewing → build_complete/evaluator" "$result" "build_complete" "evaluator"

# ── Fixture 5b: planning_complete status → planning_complete/builder_main ───
make_fixture "fx5b" "planning_complete" "planning_complete" "builder_main" >/dev/null
make_task_graph "fx5b"
result=$(map_canonical_state "fx5b")
check "status=planning_complete → planning_complete/builder_main" "$result" "planning_complete" "builder_main"

# ── Fixture 5c: S0 dispatched should not map back to planning dispatch ───────
make_fixture "fx5c" "active" "s0_dispatched" "builder_main" >/dev/null
result=$(map_canonical_state "fx5c")
check "active+s0_dispatched → building/builder_main" "$result" "building" "builder_main"

# ── Fixture 5c2: G0 pass keeps parent sprint open for later slices ───────────
make_fixture "fx5c2" "active" "g0_passed" "coordinator" >/dev/null
result=$(map_canonical_state "fx5c2")
check "active+g0_passed → building/builder_main" "$result" "building" "builder_main"

# ── Fixture 5c3: slice dispatch phases must not fall back to planning ───────
make_fixture "fx5c3" "active" "s6_dispatched" "builder" >/dev/null
result=$(map_canonical_state "fx5c3")
check "active+s6_dispatched → building/builder_main" "$result" "building" "builder_main"

# ── Fixture 5d: S0 ready for eval routes to evaluator ────────────────────────
make_fixture "fx5d" "active" "s0_ready_for_eval" "evaluator" >/dev/null
result=$(map_canonical_state "fx5d")
check "active+s0_ready_for_eval → build_complete/evaluator" "$result" "build_complete" "evaluator"

# ── Fixture 5e: slice ready-for-eval routes to evaluator ─────────────────────
make_fixture "fx5e" "active" "s6_ready_for_eval" "evaluator" >/dev/null
result=$(map_canonical_state "fx5e")
check "active+s6_ready_for_eval → build_complete/evaluator" "$result" "build_complete" "evaluator"

# ── Fixture 6: passed → done/none ────────────────────────────────────────────
make_fixture "fx6" "passed" "" "" >/dev/null
result=$(map_canonical_state "fx6")
check "passed → done/none" "$result" "done" "none"

# ── Fixture 7: failed → failed/none ──────────────────────────────────────────
make_fixture "fx7" "failed" "" "" >/dev/null
result=$(map_canonical_state "fx7")
check "failed → failed/none" "$result" "failed" "none"

# ── Fixture 8: failed_review (legacy combo) → blocked/builder_main ───────────
make_fixture "fx8" "failed_review" "" "" >/dev/null
result=$(map_canonical_state "fx8")
check "failed_review → blocked/builder_main" "$result" "blocked" "builder_main"

# ── Fixture 8b: blocked → blocked/planner ────────────────────────────────────
make_fixture "fx8b" "blocked" "" "" >/dev/null
result=$(map_canonical_state "fx8b")
check "blocked → blocked/planner" "$result" "blocked" "planner"

# ── Fixture 9: corrupt/missing JSON → corrupt/none ───────────────────────────
echo "NOT VALID JSON{{{{" > "$TMPDIR_FIXTURES/fx9.status.json"
result=$(map_canonical_state "fx9")
check "corrupt JSON → corrupt/none" "$result" "corrupt" "none"

# ── Fixture 10: missing file → corrupt/none ───────────────────────────────────
result=$(map_canonical_state "fx10_does_not_exist")
check "missing file → corrupt/none" "$result" "corrupt" "none"

# ── validate_transition smoke tests ───────────────────────────────────────────
echo ""
echo "--- validate_transition ---"

# planning_complete → build_complete via handoff_present (allowed)
if validate_transition "planning_complete" "build_complete" "handoff_present" >/dev/null 2>&1; then
    echo "  ✅ planning_complete→build_complete via handoff_present: allowed"
    PASS=$((PASS+1))
else
    rc=$?
    if [[ $rc -eq 2 ]]; then
        echo "  ⚠️  planning_complete→build_complete: unknown (not in table)"
    else
        echo "  ❌ planning_complete→build_complete: expected allowed, got denied"
        FAIL=$((FAIL+1))
    fi
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "=== RESULT: PASS=$PASS FAIL=$FAIL ==="
if [[ $FAIL -gt 0 ]]; then
    exit 1
fi
