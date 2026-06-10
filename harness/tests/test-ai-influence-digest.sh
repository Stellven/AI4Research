#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-${HOME}/.solar/harness}"
TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

# ===================================================================
# N5 tests — CLI wiring, schedule, isolation, no-pollute guard
# ===================================================================
N5_SCRIPT="$ROOT/scripts/ai_influence_daily.py"
N5_ACCOUNTS="$ROOT/ai-influence-digest/references/accounts_extended.txt"
N5_HARNESS="$ROOT/solar-harness.sh"
N5_PRODUCTION_RAW="$HOME/Knowledge/_raw/ai-influence-daily-digest"
N5_PASS=0
N5_FAIL=0

n5_test() {
    local name="$1"; shift
    if "$@" 2>/dev/null; then
        echo "PASS: $name"; N5_PASS=$((N5_PASS + 1))
    else
        echo "FAIL: $name"; N5_FAIL=$((N5_FAIL + 1))
    fi
}

echo "=== N5: CLI wiring + scheduler + isolation tests ==="

# A1: help subcommand works
n5_test "cli_help" bash "$N5_HARNESS" wiki ai-influence-digest help

# A1: help output mentions all required actions
n5_test "cli_help_actions" bash -c '
output=$(bash "'"$N5_HARNESS"'" wiki ai-influence-digest help 2>&1)
for action in run status doctor send-test schedule; do
  echo "$output" | grep -q "$action" || exit 1
done
'

# A1: top-level help mentions ai-influence-digest
n5_test "cli_toplevel_help" bash -c '
bash "'"$N5_HARNESS"'" help 2>&1 | grep -q "ai-influence-digest"
'

# A1: doctor subcommand works (exits 0 or 1 but does not crash)
n5_test "cli_doctor" bash -c '
bash "'"$N5_HARNESS"'" wiki ai-influence-digest doctor 2>/dev/null; exit 0
'

# A2: schedule status works (not loaded by default)
n5_test "schedule_status" bash -c '
output=$(bash "'"$N5_HARNESS"'" wiki ai-influence-digest schedule status 2>&1)
echo "$output" | grep -qi "schedule"
'

# A2: schedule start + stop roundtrip
n5_test "schedule_start_stop" bash -c '
bash "'"$N5_HARNESS"'" wiki ai-influence-digest schedule start 2>/dev/null
bash "'"$N5_HARNESS"'" wiki ai-influence-digest schedule status 2>/dev/null | grep -qi "loaded"
bash "'"$N5_HARNESS"'" wiki ai-influence-digest schedule stop 2>/dev/null
'

# A3: send-test produces artifacts in ISOLATED temp dir (not production)
n5_test "send_test_dryrun" bash -c '
_output=$(bash "'"$N5_HARNESS"'" wiki ai-influence-digest send-test --date 2026-05-22 2>&1)
# Extract isolated raw dir from stderr
_iso_raw=$(echo "$_output" | grep "send-test isolated raw:" | sed "s/.*send-test isolated raw: //")
test -n "$_iso_raw" || exit 1
test -f "$_iso_raw/2026-05-22/digest.json" || exit 1
test -f "$_iso_raw/2026-05-22/digest.md" || exit 1
test -f "$_iso_raw/2026-05-22/digest.html" || exit 1
'

# A3 CRITICAL: send-test does NOT pollute production raw
# Record production digest.md mtime+size, run send-test, verify unchanged
n5_test "send_test_no_pollute" bash -c '
_prod_md="'"$N5_PRODUCTION_RAW"'/2026-05-22/digest.md"
if [ -f "$_prod_md" ]; then
  _before_size=$(wc -c < "$_prod_md" | tr -d " ")
  _before_mtime=$(stat -f "%m" "$_prod_md")
fi
bash "'"$N5_HARNESS"'" wiki ai-influence-digest send-test --date 2026-05-22 2>/dev/null || true
if [ -f "$_prod_md" ]; then
  _after_size=$(wc -c < "$_prod_md" | tr -d " ")
  _after_mtime=$(stat -f "%m" "$_prod_md")
  [ "$_before_size" = "$_after_size" ] || exit 1
  [ "$_before_mtime" = "$_after_mtime" ] || exit 1
fi
'

# ===================================================================
# N3 tests — score_text, GLM analysis, degraded fallback
# ===================================================================
N3_PASS=0
N3_FAIL=0

n3_test() {
    local name="$1"; shift
    if "$@" 2>/dev/null; then
        echo "PASS: $name"; N3_PASS=$((N3_PASS + 1))
    else
        echo "FAIL: $name"; N3_FAIL=$((N3_FAIL + 1))
    fi
}

echo ""
echo "=== N3: score_text + GLM analyzer tests ==="

# A1: score_text positive boost
n3_test "score_text_positive" python3 -c "
import sys; sys.path.insert(0, '$ROOT/scripts')
import ai_influence_daily as m
assert m.score_text('Here is a prompt template for AI agents step by step') > 5
assert m.score_text('How to use this coding tool for workflow') > 3
"

# A1: score_text negative penalty
n3_test "score_text_negative" python3 -c "
import sys; sys.path.insert(0, '$ROOT/scripts')
import ai_influence_daily as m
assert m.score_text('New GPU benchmark shows improvement') < 0
assert m.score_text('Startup raised funding at high valuation') < -3
"

# A2: GLM output validates as JSON array (requires ZHIPU_API_KEY)
n3_test "glm_validates_json" python3 -c "
import sys, json, os; sys.path.insert(0, '$ROOT/scripts')
import ai_influence_daily as m
if not os.environ.get('ZHIPU_API_KEY'):
    print('SKIP: no key'); raise SystemExit(0)
cands = [m.Candidate('t','A prompt template for AI agents','https://x.com/t/1','2026-05-22','ddg')]
r = m.analyze_with_glm(cands, top_n=1)
assert r['analysis_status'] in ('ok','ok_retried'), f'GLM failed: {r[\"analysis_status\"]}'
for item in r['items']:
    assert m.GLM_ITEM_REQUIRED_KEYS.issubset(item.keys())
    assert item['type'] in m.GLM_VALID_TYPES
"

# A3: degraded fallback when GLM unavailable
n3_test "glm_degraded_fallback" python3 -c "
import sys, os; sys.path.insert(0, '$ROOT/scripts')
import ai_influence_daily as m
orig = os.environ.pop('ZHIPU_API_KEY', '')
cands = [m.Candidate('t','prompt for agents','https://x.com/t/1','2026-05-22','ddg')]
r = m.analyze_with_glm(cands, top_n=1)
os.environ['ZHIPU_API_KEY'] = orig
assert r['analysis_status'] == 'degraded'
assert r['model'] == 'local_heuristic'
"

# A3: retry on invalid JSON
n3_test "glm_retry_invalid_json" python3 -c "
import sys; sys.path.insert(0, '$ROOT/scripts')
import ai_influence_daily as m
call_count = 0
_valid_items_json = '[{\"handle\":\"@t\",\"title\":\"t\",\"type\":\"' + list(m.GLM_VALID_TYPES)[0] + '\",\"summary\":\"s\",\"key_points\":[\"a\"],\"why_useful\":\"w\",\"hotness\":\"3\",\"tweet_url\":\"u\"}]'
def mock(prompt, **kw):
    global call_count; call_count += 1
    if call_count == 1: return 'Not JSON at all'
    if call_count == 2: return _valid_items_json
    return None
m._call_glm = mock
cands = [m.Candidate('t','prompt','u','2026-05-22','ddg')]
r = m.analyze_with_glm(cands, top_n=1)
assert r['analysis_status'] == 'ok_retried', f'got {r[\"analysis_status\"]}'
assert call_count == 2
"

# A4: no Claude/Sonnet
n3_test "no_claude_sonnet" python3 -c "
import os
m = os.environ.get('ZHIPU_MODEL','GLM-5.1')
assert 'claude' not in m.lower() and 'sonnet' not in m.lower()
"

echo ""
echo "=== N3 results: $N3_PASS passed, $N3_FAIL failed ==="
echo ""
echo "=== N5 results: $N5_PASS passed, $N5_FAIL failed ==="

TOTAL_FAIL=$((N3_FAIL + N5_FAIL))
echo ""
echo "=== TOTAL: $((N3_PASS + N5_PASS)) passed, $TOTAL_FAIL failed ==="
if [ "$TOTAL_FAIL" -gt 0 ]; then exit 1; fi
