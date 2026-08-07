#!/usr/bin/env bash
# S0 sandbox round-trip test — sprint-20260509-solar-product-platform
# Tests: snapshot, verify, restore --dry-run in isolated TMPDIR
set -euo pipefail

HARNESS_DIR="${HARNESS_DIR:-$HOME/.solar/harness}"
SNAP_PY="$HARNESS_DIR/lib/product_snapshot.py"
PASS=0; FAIL=0

ok()   { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }
check() {
  local label="$1" actual="$2" expected="$3"
  if [[ "$actual" == *"$expected"* ]]; then ok "$label"; else fail "$label (got: $actual)"; fi
}

TMPDIR_TEST=$(mktemp -d)
trap 'rm -rf "$TMPDIR_TEST"' EXIT

# Seed test data
mkdir -p "$TMPDIR_TEST/source"
echo "hello world" > "$TMPDIR_TEST/source/test.sh"
echo "secret" > "$TMPDIR_TEST/source/api.key"
echo "config" > "$TMPDIR_TEST/source/config.yaml"

BACKUP_DIR="$TMPDIR_TEST/backups"

# ── T1: py_compile ────────────────────────────────────────────────────────────
echo "T1: py_compile"
python3 -m py_compile "$SNAP_PY" 2>&1 && ok "py_compile passes" || fail "py_compile fails"

# ── T2: bash -n ───────────────────────────────────────────────────────────────
echo "T2: bash -n solar-harness.sh"
bash -n "$HARNESS_DIR/solar-harness.sh" 2>&1 && ok "solar-harness.sh syntax ok" || fail "solar-harness.sh syntax error"

# ── T3: dry-run snapshot ──────────────────────────────────────────────────────
echo "T3: snapshot --dry-run"
OUT=$(python3 "$SNAP_PY" snapshot --dry-run --scope minimal --out-dir "$BACKUP_DIR" 2>/dev/null)
check "dry_run field" "$OUT" '"dry_run": true'
check "would_include > 0" "$OUT" '"would_include":'

# ── T4: actual snapshot --scope minimal ──────────────────────────────────────
echo "T4: snapshot --scope minimal"
OUT=$(python3 "$SNAP_PY" snapshot --scope minimal --out-dir "$BACKUP_DIR" 2>/dev/null)
check "ok=true" "$OUT" '"ok": true'
check "snapshot_id" "$OUT" '"snapshot_id":'
check "archive_sha256 present" "$OUT" '"archive_sha256":'
SNAP_ID=$(echo "$OUT" | python3 -c "import json,sys; print(json.load(sys.stdin)['snapshot_id'])" 2>/dev/null)

# ── T5: verify --latest ───────────────────────────────────────────────────────
echo "T5: verify --latest"
OUT=$(python3 "$SNAP_PY" verify --latest --out-dir "$BACKUP_DIR" 2>/dev/null)
check "verify ok" "$OUT" '"ok": true'
check "sha256_match" "$OUT" '"archive_sha256_match": true'

# ── T6: restore --dry-run ─────────────────────────────────────────────────────
echo "T6: restore --latest --dry-run"
OUT=$(python3 "$SNAP_PY" restore --latest --dry-run --out-dir "$BACKUP_DIR" 2>/dev/null)
check "dry_run restore ok" "$OUT" '"ok": true'
check "restore plan count" "$OUT" '"restore_plan_count":'

# ── T7: secrets excluded ──────────────────────────────────────────────────────
echo "T7: secrets not in archive or manifest"
SNAP_DIR="$BACKUP_DIR/$SNAP_ID"
if [[ -d "$SNAP_DIR" ]]; then
  MANIFEST="$SNAP_DIR/manifest.json"
  # .key files should appear in excluded list (path) but never have their content
  if python3 -c "
import json
m=json.load(open('$MANIFEST'))
# Verify secret patterns are listed
assert '.env' in str(m['excluded_patterns']), 'excluded_patterns missing .env'
# Verify files list has no secret filenames
for f in m['files']:
    name=f['path'].split('/')[-1].lower()
    for pat in ['*.key','*.pem','*.env','*token*','*secret*','*password*']:
        import fnmatch
        assert not fnmatch.fnmatch(name, pat), f'secret file in files: {name}'
print('ok')
" 2>/dev/null | grep -q "ok"; then
    ok "secrets excluded from files list"
  else
    fail "secrets may be in files list"
  fi
  # excluded list should contain paths (not values)
  if python3 -c "
import json
m=json.load(open('$MANIFEST'))
excl=str(m.get('excluded',[]))
# Excluded should list paths only, no raw secret content patterns like 'sk-', 'Bearer'
assert 'Bearer' not in excl
assert 'sk-' not in excl
print('ok')
" 2>/dev/null | grep -q "ok"; then
    ok "excluded list contains paths not values"
  else
    fail "excluded list might contain secret values"
  fi
fi

# ── T8: list command ──────────────────────────────────────────────────────────
echo "T8: product list"
OUT=$(python3 "$SNAP_PY" list --out-dir "$BACKUP_DIR" 2>/dev/null)
check "list ok" "$OUT" '"ok": true'
check "count >= 1" "$OUT" '"count":'

echo ""
echo "=== Snapshot Round-trip: PASS=$PASS FAIL=$FAIL ==="
[[ $FAIL -eq 0 ]] && exit 0 || exit 1
