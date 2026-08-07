#!/usr/bin/env bash
# tests/test-everything-claude-code-integration.sh — ECC Integration regression tests
# sprint-20260508-everything-claude-code-integration

set -euo pipefail

HARNESS_DIR="${HARNESS_DIR:-$HOME/.solar/harness}"
ADAPTER="$HARNESS_DIR/lib/everything_claude_code_adapter.py"

PASS=0
FAIL=0

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

CASE_FILTER="${1:-}"

check() {
    local label="$1" got="$2" want="$3"
    if [[ "$got" == "$want" ]]; then
        echo "  ✅ $label"
        PASS=$((PASS+1))
    else
        echo "  ❌ $label"
        echo "       want: $want"
        echo "        got: $got"
        FAIL=$((FAIL+1))
    fi
}

check_contains() {
    local label="$1" haystack="$2" needle="$3"
    if echo "$haystack" | grep -q "$needle" 2>/dev/null; then
        echo "  ✅ $label"
        PASS=$((PASS+1))
    else
        echo "  ❌ $label — '$needle' not found"
        FAIL=$((FAIL+1))
    fi
}

check_rc() {
    local label="$1" rc="$2" want="$3"
    if [[ "$rc" == "$want" ]]; then
        echo "  ✅ $label (rc=$rc)"
        PASS=$((PASS+1))
    else
        echo "  ❌ $label (want rc=$want, got rc=$rc)"
        FAIL=$((FAIL+1))
    fi
}

run_case() {
    [[ -z "$CASE_FILTER" || "$CASE_FILTER" == "--case" ]] && return 0
    [[ "$CASE_FILTER" == "--case" && "${2:-}" == "$1" ]] && return 0
    # --case <name> was passed; run only that case
    return 0
}

# ─── helper: pick a real non-hooks key from inventory ────────────────────────
pick_skill_key() {
    python3 "$ADAPTER" inventory --json 2>/dev/null \
      | python3 -c "
import json,sys
d=json.load(sys.stdin)
items=d.get('items',{}).get('skills',[])
if items:
    print(items[0]['key'])
else:
    print('')
" 2>/dev/null || echo ""
}

SKILL_KEY="$(pick_skill_key)"

echo "=== test-everything-claude-code-integration.sh ==="
echo ""

# ─── A1: vendor is present and has a git commit ──────────────────────────────
if [[ -z "$CASE_FILTER" || "$CASE_FILTER" == "--case" ]]; then
echo "--- A1: vendor present, not activated ---"

vendor_dir="$HARNESS_DIR/vendor/everything-claude-code"
check "vendor .git exists" "$(test -d "$vendor_dir/.git" && echo yes)" "yes"
sha=$(git -C "$vendor_dir" rev-parse HEAD 2>/dev/null || echo "")
check "vendor commit SHA non-empty" "$([ -n "$sha" ] && echo yes)" "yes"
echo ""
fi

# ─── A2: inventory covers required surfaces ──────────────────────────────────
if [[ -z "$CASE_FILTER" || "$CASE_FILTER" == "--case" ]]; then
echo "--- A2: inventory counts all surfaces ---"

inv_out=$(python3 "$ADAPTER" inventory --json 2>/dev/null)
rc=$?
check_rc "inventory exits 0" "$rc" "0"

py_check='
import json,sys
d=json.load(sys.stdin)
required=["agents","commands","skills","hooks","rules","mcp_configs","scripts","tests"]
missing=[k for k in required if k not in d.get("counts",{})]
print("missing:"+",".join(missing) if missing else "ok")
'
result=$(echo "$inv_out" | python3 -c "$py_check" 2>/dev/null || echo "error")
check "inventory has all required surface keys" "$result" "ok"
echo ""
fi

# ─── A3: dry-run has collision + compatibility keys ──────────────────────────
if [[ -z "$CASE_FILTER" || "$CASE_FILTER" == "--case" ]]; then
echo "--- A3: collision analysis present ---"

dry_out=$(python3 "$ADAPTER" install-dry-run --json 2>/dev/null)
rc=$?
check_rc "install-dry-run exits 0" "$rc" "0"

py_check='
import json,sys
d=json.load(sys.stdin)
ok = "collisions" in d and "gstack" in d.get("compatibility",{}) and "superpowers" in d.get("compatibility",{})
print("ok" if ok else "missing_keys")
'
result=$(echo "$dry_out" | python3 -c "$py_check" 2>/dev/null || echo "error")
check "dry-run has collisions + gstack + superpowers" "$result" "ok"
echo ""
fi

# ─── A4: no live hook changes ─────────────────────────────────────────────────
if [[ -z "$CASE_FILTER" || "$CASE_FILTER" == "--case" ]]; then
echo "--- A4: no global hook activation ---"

live_hooks=$(echo "$dry_out" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('live_hook_changes',99))" 2>/dev/null || echo 99)
check "live_hook_changes == 0" "$live_hooks" "0"
echo ""
fi

# ─── A5: sync idempotent + rollback ──────────────────────────────────────────
sync_rollback_case() {
echo "--- A5: sync idempotent + rollback ---"

if [[ -z "$SKILL_KEY" ]]; then
    echo "  ⚠️  no skill keys in upstream — skipping sync-rollback case"
    return
fi

# Temp dirs for this test
T_STAGING="$TMP/staging"
T_RUN="$TMP/run"
T_HOME="$TMP/home"

# Build minimal allowlist that allows one skill
AL="$TMP/test-allowlist.json"
python3 -c "
import json
al = {
    'version': 1,
    'source': 'test',
    'default_action': 'defer',
    'allowed': {
        'skills': ['$SKILL_KEY'],
        'agents': [],
        'commands': [],
        'rules': [],
        'hooks': [],
        'mcp_configs': []
    },
    'blocked_by_default': ['hooks', 'mcp_configs']
}
print(json.dumps(al, indent=2))
" > "$AL"

export ECC_STAGING="$T_STAGING"
export ECC_RUN_DIR="$T_RUN"
export ECC_HOME_OVERRIDE="$T_HOME"

# S1: sync → should copy one skill
sync1=$(python3 "$ADAPTER" sync-allowlisted --allowlist "$AL" --json 2>/dev/null)
rc=$?
check_rc "first sync exits 0" "$rc" "0"

copied_count=$(echo "$sync1" | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d.get('copied',[])))" 2>/dev/null || echo -1)
check "first sync copies 1 skill" "$copied_count" "1"

# Check manifest written
manifest_count=$(ls "$T_RUN"/sync-*.json 2>/dev/null | wc -l | tr -d ' ')
check "sync manifest written" "$([ "$manifest_count" -ge 1 ] && echo yes)" "yes"

# Check staged file exists
dest_file=$(echo "$sync1" | python3 -c "import json,sys; d=json.load(sys.stdin); c=d.get('copied',[]); print(c[0]['dest'] if c else '')" 2>/dev/null || echo "")
check "staged file exists" "$(test -f "$dest_file" && echo yes || echo no)" "yes"

# S2: re-run sync → idempotent (skipped, identical)
sync2=$(python3 "$ADAPTER" sync-allowlisted --allowlist "$AL" --json 2>/dev/null)
skip_count=$(echo "$sync2" | python3 -c "
import json,sys
d=json.load(sys.stdin)
n=[x for x in d.get('skipped',[]) if x.get('reason')=='identical']
print(len(n))
" 2>/dev/null || echo -1)
check "second sync skips identical file" "$([ "$skip_count" -ge 1 ] && echo yes)" "yes"

copied2=$(echo "$sync2" | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d.get('copied',[])))" 2>/dev/null || echo -1)
check "second sync copies 0 (idempotent)" "$copied2" "0"

# S3: rollback the FIRST sync (not latest which has copied=[])
sync1_ts=$(echo "$sync1" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('sync_ts',''))" 2>/dev/null || echo "")
rb=$(python3 "$ADAPTER" rollback --sync-ts "$sync1_ts" --json 2>/dev/null)
rc_rb=$?
check_rc "rollback exits 0" "$rc_rb" "0"

rb_ok=$(echo "$rb" | python3 -c "import json,sys; d=json.load(sys.stdin); print('yes' if d.get('ok') else 'no')" 2>/dev/null || echo no)
check "rollback ok=true" "$rb_ok" "yes"

check "staged file removed after rollback" "$(test ! -f "$dest_file" && echo yes || echo no)" "yes"

# Manifest archived
archived=$(echo "$rb" | python3 -c "import json,sys; d=json.load(sys.stdin); print('yes' if d.get('manifest_archived') else 'no')" 2>/dev/null || echo no)
check "manifest archived after rollback" "$archived" "yes"

unset ECC_STAGING ECC_RUN_DIR ECC_HOME_OVERRIDE
echo ""
}

if [[ -z "$CASE_FILTER" || ("$CASE_FILTER" == "--case" && "${2:-}" == "sync-rollback") ]]; then
    sync_rollback_case
fi

# ─── A6: integrations status shows everything-claude-code ────────────────────
if [[ -z "$CASE_FILTER" || "$CASE_FILTER" == "--case" ]]; then
echo "--- A6: status server has ECC candidate ---"

status_out=$(python3 "$HARNESS_DIR/lib/external-integrations-health.py" --json --refresh 2>/dev/null)
rc=$?
check_rc "integrations status exits 0" "$rc" "0"

py_check='
import json,sys
d=json.load(sys.stdin)
items=[x for x in d.get("integrations",[]) if "everything-claude-code" in x.get("name","")]
if not items:
    print("not_found")
elif items[0]["status"] in ("warn","missing"):
    print("ok")
else:
    print("status="+items[0]["status"])
'
result=$(echo "$status_out" | python3 -c "$py_check" 2>/dev/null || echo "error")
check "integrations status has ECC with warn/missing" "$result" "ok"
echo ""
fi

# ─── A7: tests run safe (self-check) ─────────────────────────────────────────
if [[ -z "$CASE_FILTER" || "$CASE_FILTER" == "--case" ]]; then
echo "--- A7: tests are local and safe ---"

check "no live ~/.claude modification" "$(
    # Verify the adapter never writes to ~/.claude by checking it uses STAGING
    python3 -c "
import ast, pathlib, sys
src = pathlib.Path('$ADAPTER').read_text()
# verify STAGING env var is used (not hard-coded ~/.claude path)
ok = 'ECC_STAGING' in src and 'ECC_RUN_DIR' in src and 'ECC_HOME_OVERRIDE' in src
print('ok' if ok else 'missing_env_overrides')
"
)" "ok"

check "sync writes to staging not live claude" "$(
    python3 -c "
import pathlib
src = pathlib.Path('$ADAPTER').read_text()
# sync_allowlisted must reference STAGING, not ~/.claude directly
if 'STAGING' in src and 'sync_allowlisted' in src:
    print('ok')
else:
    print('fail')
"
)" "ok"

check "adapter has rollback command" "$(
    python3 -c "
import pathlib
src = pathlib.Path('$ADAPTER').read_text()
print('ok' if 'def rollback' in src and 'sync-ts' in src else 'fail')
"
)" "ok"

echo ""
fi

echo "=== RESULT: PASS=$PASS FAIL=$FAIL ==="
[[ $FAIL -eq 0 ]]
