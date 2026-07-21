#!/usr/bin/env bash
# S4 Extension Framework test suite — sprint-20260509-solar-product-platform
# Tests: plugin manifests, capability_registry, plugin_loader, scope enforcement, CLI routing
set -euo pipefail

HARNESS_DIR="${HARNESS_DIR:-$HOME/.solar/harness}"
LIB="$HARNESS_DIR/lib"
PASS=0; FAIL=0

ok()   { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }
check() {
  local label="$1" actual="$2" expected="$3"
  if [[ "$actual" == *"$expected"* ]]; then ok "$label"; else fail "$label (got: $actual)"; fi
}

TMPDIR_TEST=$(mktemp -d)
trap 'rm -rf "$TMPDIR_TEST"' EXIT

# ── T1: py_compile ────────────────────────────────────────────────────────────
echo "T1: py_compile"
for mod in plugin_loader capability_registry; do
  python3 -m py_compile "$LIB/${mod}.py" 2>&1 \
    && ok "${mod}.py compiles" \
    || fail "${mod}.py compile error"
done

# ── T2: bash -n on solar-harness.sh ──────────────────────────────────────────
echo "T2: solar-harness.sh syntax"
bash -n "$HARNESS_DIR/solar-harness.sh" 2>/dev/null \
  && ok "solar-harness.sh bash syntax" \
  || fail "solar-harness.sh bash syntax error"

# ── T3: schemas valid JSON ────────────────────────────────────────────────────
echo "T3: JSON schemas"
for schema in plugin.schema.json capability.schema.json; do
  python3 -c "import json; json.load(open('$HARNESS_DIR/schemas/$schema'))" 2>/dev/null \
    && ok "schemas/$schema: valid JSON" \
    || fail "schemas/$schema: invalid JSON"
done

# ── T4: at least 5 plugin manifest dirs ──────────────────────────────────────
echo "T4: plugin manifest count"
PLUGIN_COUNT=$(ls -d "$HARNESS_DIR/plugins"/*/manifest.yaml 2>/dev/null | wc -l)
[[ $PLUGIN_COUNT -ge 5 ]] \
  && ok "plugin manifests: $PLUGIN_COUNT >= 5" \
  || fail "plugin manifests: only $PLUGIN_COUNT (need >=5)"

# ── T5: all manifests parse without errors ────────────────────────────────────
echo "T5: manifest validation"
OUT=$(python3 "$LIB/plugin_loader.py" validate --json 2>/dev/null)
check "validate: ok" "$OUT" '"ok": true'
# All 5 should be valid
VALID_COUNT=$(echo "$OUT" | python3 -c "
import json,sys
d=json.load(sys.stdin)
print(sum(1 for r in d.get('results',[]) if r.get('valid')))
" 2>/dev/null || echo "0")
[[ $VALID_COUNT -ge 5 ]] \
  && ok "manifests valid: $VALID_COUNT >= 5" \
  || fail "manifests valid: only $VALID_COUNT"

# ── T6: plugin list --json has 5+ entries ─────────────────────────────────────
echo "T6: plugin list"
OUT=$(python3 "$LIB/plugin_loader.py" list --json 2>/dev/null)
check "list: ok" "$OUT" '"ok": true'
TOTAL=$(echo "$OUT" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('total',0))" 2>/dev/null || echo "0")
[[ $TOTAL -ge 5 ]] \
  && ok "plugin list: total=$TOTAL >= 5" \
  || fail "plugin list: total=$TOTAL < 5"

# ── T7: integrations status returns four-level data ──────────────────────────
echo "T7: integrations plugin-status --json"
OUT=$(python3 "$LIB/plugin_loader.py" status --json 2>/dev/null)
check "status: ok" "$OUT" '"ok": true'
check "status: by_level present" "$OUT" '"by_level"'
check "status: has closed_loop" "$OUT" '"closed_loop"'

# ── T8: scope enforcement — reject out-of-scope path ─────────────────────────
echo "T8: scope enforcement"
OUT=$(python3 "$LIB/plugin_loader.py" check-scope \
  --plugin mermaid \
  --path "/etc/passwd" \
  --json 2>/dev/null || true)
check "scope: /etc/passwd rejected" "$OUT" '"allowed": false'
check "scope: alert emitted" "$OUT" '"alert"'

# ── T9: scope enforcement — allow declared scope ──────────────────────────────
echo "T9: scope allow declared path"
OUT=$(python3 "$LIB/plugin_loader.py" check-scope \
  --plugin obsidian \
  --path "$HARNESS_DIR/_sources/ingested/test.md" \
  --json 2>/dev/null)
check "scope: ingested path allowed for obsidian" "$OUT" '"allowed": true'

# ── T10: scope violation writes event to events.jsonl ─────────────────────────
echo "T10: scope violation event"
BEFORE=$(wc -l < "$HARNESS_DIR/events.jsonl" 2>/dev/null || echo "0")
python3 "$LIB/plugin_loader.py" check-scope \
  --plugin mermaid \
  --path "/tmp/evil-write.sh" \
  --json >/dev/null 2>&1 || true
AFTER=$(wc -l < "$HARNESS_DIR/events.jsonl" 2>/dev/null || echo "0")
[[ $AFTER -gt $BEFORE ]] \
  && ok "scope violation: event written to events.jsonl" \
  || fail "scope violation: no event written"

# ── T11: capability registry sync ─────────────────────────────────────────────
echo "T11: capability registry sync"
OUT=$(python3 "$LIB/capability_registry.py" sync --json 2>/dev/null)
check "cap sync: ok" "$OUT" '"ok": true'
SYNCED=$(echo "$OUT" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('synced_capabilities',0))" 2>/dev/null || echo "0")
[[ $SYNCED -ge 5 ]] \
  && ok "capability sync: $SYNCED capabilities >= 5" \
  || fail "capability sync: only $SYNCED capabilities"

# ── T12: capability registry list ─────────────────────────────────────────────
echo "T12: capability list"
OUT=$(python3 "$LIB/capability_registry.py" list --json 2>/dev/null)
check "cap list: ok" "$OUT" '"ok": true'
check "cap list: has capabilities array" "$OUT" '"capabilities"'

# ── T13: capability query finds wiki.read ─────────────────────────────────────
echo "T13: capability query"
OUT=$(python3 "$LIB/capability_registry.py" query wiki.read --json 2>/dev/null)
check "query wiki.read: found" "$OUT" '"found": true'
check "query wiki.read: obsidian provides it" "$OUT" '"obsidian"'

# ── T14: solar-harness integrations CLI routing ───────────────────────────────
echo "T14: solar-harness integrations CLI routing"
bash "$HARNESS_DIR/solar-harness.sh" integrations list --json 2>/dev/null | grep -q '"ok"' \
  && ok "solar-harness integrations list" \
  || fail "solar-harness integrations list failed"
bash "$HARNESS_DIR/solar-harness.sh" integrations plugins --json 2>/dev/null | grep -q '"ok"' \
  && ok "solar-harness integrations plugins" \
  || fail "solar-harness integrations plugins failed"
bash "$HARNESS_DIR/solar-harness.sh" integrations validate --json 2>/dev/null | grep -q '"ok"' \
  && ok "solar-harness integrations validate" \
  || fail "solar-harness integrations validate failed"

# ── T15: install/disable round-trip ──────────────────────────────────────────
echo "T15: install/disable round-trip"
# Use mermaid as test subject (already enabled; will disable then re-enable)
python3 "$LIB/plugin_loader.py" disable mermaid --json 2>/dev/null | grep -q '"new_status": "disabled"' \
  && ok "disable mermaid: ok" \
  || fail "disable mermaid: failed"
python3 "$LIB/plugin_loader.py" install mermaid --json 2>/dev/null | grep -q '"new_status": "enabled"' \
  && ok "install mermaid: ok (re-enabled)" \
  || fail "install mermaid: failed"

# ── T16: capability scorecard ─────────────────────────────────────────────────
echo "T16: capability scorecard"
OUT=$(python3 "$LIB/capability_registry.py" scorecard --json 2>/dev/null)
check "scorecard: ok" "$OUT" '"ok": true'
check "scorecard: weighted_score present" "$OUT" '"weighted_score"'

echo ""
echo "=== S4 Plugins: PASS=$PASS FAIL=$FAIL ==="
[[ $FAIL -eq 0 ]] && exit 0 || exit 1
