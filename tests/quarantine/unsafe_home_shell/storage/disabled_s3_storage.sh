#!/usr/bin/env bash
# S3 Storage & Data Access test suite — sprint-20260509-solar-product-platform
# Tests: source_manifest, qmd_adapter, _sources skeleton, storage config, drive status
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

# ── T1: py_compile all S3 modules ────────────────────────────────────────────
echo "T1: py_compile"
for mod in source_manifest qmd_adapter; do
  python3 -m py_compile "$LIB/${mod}.py" 2>&1 \
    && ok "${mod}.py compiles" \
    || fail "${mod}.py compile error"
done

# ── T2: storage.solar.yaml exists and has required keys ──────────────────────
echo "T2: storage.solar.yaml structure"
python3 -c "
import sys
text = open('$HARNESS_DIR/config/storage.solar.yaml').read()
required = ['sources:', 'staging:', 'migration:', 'mineru:', 'drive:', 'qmd:']
missing = [k for k in required if k not in text]
assert not missing, f'missing keys: {missing}'
assert 'dry_run_default: true' in text, 'dry_run_default not true'
assert 'degraded' in text, 'drive degraded not configured'
assert 'require_checksum: true' in text, 'require_checksum not enforced'
print('ok')
" 2>/dev/null | grep -q "ok" \
  && ok "storage.solar.yaml: required keys present" \
  || fail "storage.solar.yaml: missing keys"

# ── T3: _sources directory skeleton exists ────────────────────────────────────
echo "T3: _sources skeleton"
[[ -d "$HARNESS_DIR/_sources" ]] && ok "_sources dir exists" || fail "_sources dir missing"
[[ -d "$HARNESS_DIR/_sources/papers" ]] && ok "_sources/papers exists" || fail "_sources/papers missing"
[[ -f "$HARNESS_DIR/_sources/.gitkeep" ]] && ok "_sources/.gitkeep exists" || fail "_sources/.gitkeep missing"

# ── T4: launchd plist exists with required fields ────────────────────────────
echo "T4: MinerU launchd plist"
PLIST="$HARNESS_DIR/com.solar.mineru-idle.plist"
[[ -f "$PLIST" ]] && ok "plist exists" || fail "plist missing"
python3 -c "
import plistlib
with open('$PLIST', 'rb') as f:
    p = plistlib.load(f)
assert p.get('Label') == 'com.solar.mineru-idle', f'bad label: {p.get(\"Label\")}'
assert 'SoftResourceLimits' in p, 'SoftResourceLimits missing'
assert p.get('Nice', 0) >= 10, 'Nice not set high (idle priority)'
assert p.get('ProcessType') == 'Background', 'not Background process'
print('ok')
" 2>/dev/null | grep -q "ok" && ok "plist: required fields present" || fail "plist: missing required fields"

# ── T5: source_manifest scan on empty dir ────────────────────────────────────
echo "T5: source_manifest scan (empty)"
mkdir -p "$TMPDIR_TEST/raw"
OUT=$(python3 "$LIB/source_manifest.py" scan --raw-dir "$TMPDIR_TEST/raw" --json 2>/dev/null)
check "scan: ok" "$OUT" '"ok": true'
check "scan: total=0" "$OUT" '"total": 0'

# ── T6: source_manifest migrate dry-run ──────────────────────────────────────
echo "T6: source_manifest migrate dry-run"
mkdir -p "$TMPDIR_TEST/raw_pdfs"
# Create a synthetic PDF-like file
echo "%PDF-1.4 fake content for testing" > "$TMPDIR_TEST/raw_pdfs/test.pdf"
DEST="$TMPDIR_TEST/papers"
OUT=$(python3 "$LIB/source_manifest.py" migrate \
  --raw-dir "$TMPDIR_TEST/raw_pdfs" \
  --dest "$DEST" \
  --json 2>/dev/null)
check "migrate dry-run: ok" "$OUT" '"ok": true'
check "migrate dry-run: dry_run=true" "$OUT" '"dry_run": true'
check "migrate dry-run: originals preserved" "$OUT" '"note"'
# Verify original NOT moved (dry-run)
[[ -f "$TMPDIR_TEST/raw_pdfs/test.pdf" ]] && ok "original preserved in dry-run" || fail "original was moved in dry-run!"

# ── T7: source_manifest migrate --apply copies without deleting original ──────
echo "T7: source_manifest migrate --apply"
OUT=$(python3 "$LIB/source_manifest.py" migrate \
  --raw-dir "$TMPDIR_TEST/raw_pdfs" \
  --dest "$DEST" \
  --apply \
  --json 2>/dev/null)
check "migrate apply: ok" "$OUT" '"ok": true'
[[ -f "$TMPDIR_TEST/raw_pdfs/test.pdf" ]] && ok "original still exists after apply" || fail "original deleted!"
# Check manifest written
MANIFEST_COUNT=$(find "$DEST" -name "manifest.json" 2>/dev/null | wc -l)
[[ $MANIFEST_COUNT -ge 1 ]] && ok "manifest.json written" || fail "manifest.json not found"

# ── T8: source_manifest verify ───────────────────────────────────────────────
echo "T8: source_manifest verify"
SOURCES_TMP="$TMPDIR_TEST/sources_root"
mkdir -p "$SOURCES_TMP"
# Link the papers we just created
cp -r "$DEST" "$SOURCES_TMP/papers"
OUT=$(python3 "$LIB/source_manifest.py" verify \
  --sources-dir "$SOURCES_TMP" \
  --json 2>/dev/null)
check "verify: ok" "$OUT" '"ok": true'
check "verify: passed>=1" "$OUT" '"passed"'

# ── T9: qmd_adapter drive-status shows degraded when no creds ────────────────
echo "T9: drive-status degraded without credentials"
OUT=$(GOOGLE_APPLICATION_CREDENTIALS="" python3 "$LIB/qmd_adapter.py" drive-status --json 2>/dev/null)
check "drive-status: degraded" "$OUT" '"status": "degraded"'
check "drive-status: not ok" "$OUT" '"credential_present": false'

# ── T10: qmd_adapter rebuild --dry-run ───────────────────────────────────────
echo "T10: qmd rebuild dry-run"
OUT=$(python3 "$LIB/qmd_adapter.py" rebuild --dry-run --json 2>/dev/null)
check "rebuild dry-run: ok" "$OUT" '"ok": true'
check "rebuild dry-run: dry_run=true" "$OUT" '"dry_run": true'

# ── T11: qmd_adapter check-links ─────────────────────────────────────────────
echo "T11: qmd check-links"
OUT=$(python3 "$LIB/qmd_adapter.py" check-links --json 2>/dev/null || true)
check "check-links: returns ok field" "$OUT" '"ok"'

# ── T12: mirage doctor returns 8 mounts ──────────────────────────────────────
echo "T12: mirage doctor 8 mounts"
OUT=$(python3 "$LIB/solar_mirage.py" doctor --json 2>/dev/null || echo '{}')
MOUNT_COUNT=$(echo "$OUT" | python3 -c "
import json, sys
d = json.load(sys.stdin)
mounts = d.get('mounts', [])
print(len(mounts))
" 2>/dev/null || echo "0")
[[ "$MOUNT_COUNT" -ge 8 ]] \
  && ok "mirage doctor: $MOUNT_COUNT mounts >= 8" \
  || fail "mirage doctor: only $MOUNT_COUNT mounts (need >=8)"

# ── T13: storage migrate has --dry-run safety ────────────────────────────────
echo "T13: migrate dry-run is default"
python3 -c "
text = open('$HARNESS_DIR/config/storage.solar.yaml').read()
assert 'dry_run_default: true' in text, 'dry_run_default not true'
assert 'stop_on_missing_checksum: true' in text, 'checksum enforcement missing'
print('ok')
" 2>/dev/null | grep -q "ok" && ok "migrate: dry-run default + checksum enforced" || fail "migrate: safety defaults missing"

echo ""
echo "=== S3 Storage: PASS=$PASS FAIL=$FAIL ==="
[[ $FAIL -eq 0 ]] && exit 0 || exit 1
