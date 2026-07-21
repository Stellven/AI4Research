#!/usr/bin/env bash
# test-intent-engine-adapter.sh — verify old Solar intent semantics in Harness.
set -euo pipefail

HARNESS_DIR="$(cd "$(dirname "$0")/.." && pwd)"
INTENT_PY="$HARNESS_DIR/lib/intent_engine_adapter.py"
SKILLS_PY="$HARNESS_DIR/lib/solar_skills.py"
TMPDIR_TEST="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_TEST"' EXIT

fail() { echo "FAIL: $*" >&2; exit 1; }
pass() { echo "PASS: $*"; }

json_has() {
  local input="$1" needle="$2"
  python3 "$INTENT_PY" match "$input" --json | grep -q "$needle" || fail "expected '$needle' for input: $input"
}

json_has "可以" '"type": "confirm"'
json_has "赶紧继续修复" '"type": "execute"'
json_has "请用系统化调试逐步排查这个问题" '"source": "superpowers"'
json_has "打开网页 screenshot 看看 localhost" '"source": "gstack"'

TMP_DB="$TMPDIR_TEST/intent.db"
SOLAR_INTENT_DB="$TMP_DB" python3 "$INTENT_PY" learn "狠狠的干" execute >/dev/null || fail "learned intent write failed"
SOLAR_INTENT_DB="$TMP_DB" python3 "$INTENT_PY" match "请你狠狠的干" --json | grep -q '"source": "solar-learned-db"' \
  || fail "learned intent did not match"

DISPATCH="$TMPDIR_TEST/dispatch.md"
cat > "$DISPATCH" <<'EOF'
# Dispatch

请用系统化调试逐步排查 browser-use 的 localhost screenshot 问题，然后继续修复。
EOF

python3 "$SKILLS_PY" inject "$DISPATCH" >/dev/null || fail "skills inject failed"
grep -q "<solar-intent-context>" "$DISPATCH" || fail "intent block not injected"
grep -q "superpowers" "$DISPATCH" || fail "superpowers hint missing in injected intent block"
grep -q "execute" "$DISPATCH" || fail "execute intent missing in injected intent block"

pass "direct intent detection: confirm/execute"
pass "legacy hint detection: Superpowers/gstack precedence"
pass "learned intent DB: write/read"
pass "skills inject includes solar-intent-context"
echo "PROBES_PASSED=4 PROBES_FAILED=0"
