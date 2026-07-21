#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="${TMPDIR:-/tmp}/solar-knowledge-ingest-dispatcher-test-$$"
DB="$TMP_DIR/knowledge_ingest.sqlite"
mkdir -p "$TMP_DIR"
trap 'rm -rf "$TMP_DIR"' EXIT

PASS=0
FAIL=0

assert_exit_0() {
  local label="$1"; shift
  if "$@" >/dev/null 2>&1; then
    PASS=$((PASS + 1))
  else
    FAIL=$((FAIL + 1))
    echo "FAIL: $label (exit != 0)"
  fi
}

assert_output_contains() {
  local label="$1" needle="$2"; shift 2
  local out
  out=$("$@" 2>&1) || true
  if echo "$out" | grep -q "$needle"; then
    PASS=$((PASS + 1))
  else
    FAIL=$((FAIL + 1))
    echo "FAIL: $label (missing '$needle')"
    echo "  output: $(echo "$out" | head -3)"
  fi
}

assert_eq() {
  local label="$1" expected="$2" actual="$3"
  if [ "$expected" = "$actual" ]; then
    PASS=$((PASS + 1))
  else
    FAIL=$((FAIL + 1))
    echo "FAIL: $label (expected='$expected' actual='$actual')"
  fi
}

DISPATCHER="$ROOT/lib/knowledge_ingest_dispatcher.py"

# --- A1: status --json exits 0 and contains registry ---
assert_exit_0 "status exits 0" python3 "$DISPATCHER" --db "$DB" status --json
assert_output_contains "status has registry" "schema_version" python3 "$DISPATCHER" --db "$DB" status --json

# --- A2: migrate is idempotent ---
python3 "$DISPATCHER" --db "$DB" migrate --json >/dev/null
tables1="$(sqlite3 "$DB" "SELECT COUNT(*) FROM sqlite_master WHERE type='table'")"
python3 "$DISPATCHER" --db "$DB" migrate --json >/dev/null
tables2="$(sqlite3 "$DB" "SELECT COUNT(*) FROM sqlite_master WHERE type='table'")"
assert_eq "migrate idempotent" "$tables1" "$tables2"

# --- A3: submit-event writes registry row ---
mkdir -p "$TMP_DIR/docs"
echo "# Test doc" > "$TMP_DIR/docs/test.md"
python3 "$DISPATCHER" --db "$DB" submit-event \
  --source-kind test \
  --source-path "$TMP_DIR/docs/test.md" \
  --source-adapter test_adapter \
  --json >/dev/null 2>&1
row_count="$(sqlite3 "$DB" "SELECT COUNT(*) FROM documents WHERE source_kind='test'")"
assert_eq "submit-event writes row" "1" "$row_count"

# --- A4: submit-event writes ingest_events audit trail ---
event_count="$(sqlite3 "$DB" "SELECT COUNT(*) FROM ingest_events WHERE event_kind='upsert_document'")"
assert_eq "submit-event writes event" "1" "$event_count"

# --- A5: submit-event is idempotent (same doc_id, no duplicate) ---
python3 "$DISPATCHER" --db "$DB" submit-event \
  --source-kind test \
  --source-path "$TMP_DIR/docs/test.md" \
  --source-adapter test_adapter \
  --json >/dev/null 2>&1
doc_count="$(sqlite3 "$DB" "SELECT COUNT(*) FROM documents WHERE source_kind='test'")"
assert_eq "submit-event idempotent" "1" "$doc_count"

# --- A6: discover-raw works ---
mkdir -p "$TMP_DIR/raw/sub"
echo "# Raw 1" > "$TMP_DIR/raw/r1.md"
echo "# Raw 2" > "$TMP_DIR/raw/sub/r2.md"
raw_out="$(python3 "$DISPATCHER" --db "$DB" discover-raw --source-dir "$TMP_DIR/raw" --json 2>&1)"
raw_count="$(echo "$raw_out" | python3 -c "import json,sys; print(json.load(sys.stdin)['count'])")"
assert_eq "discover-raw count" "2" "$raw_count"

# --- A7: discover-vault works ---
mkdir -p "$TMP_DIR/vault/concepts" "$TMP_DIR/vault/references"
echo "# C1" > "$TMP_DIR/vault/concepts/c1.md"
echo "# R1" > "$TMP_DIR/vault/references/r1.md"
vault_out="$(python3 "$DISPATCHER" --db "$DB" discover-vault --vault "$TMP_DIR/vault" --json 2>&1)"
vault_count="$(echo "$vault_out" | python3 -c "import json,sys; print(json.load(sys.stdin)['count'])")"
assert_eq "discover-vault count" "2" "$vault_count"

# --- A8: process-queue exits 0 ---
assert_exit_0 "process-queue exits 0" python3 "$DISPATCHER" --db "$DB" process-queue --json

# --- A9: all 10 tables exist ---
expected_tables="documents extract_jobs extract_outputs ingest_events migration_log qmd_index_events relations spans validation_results watermarks"
actual_tables="$(sqlite3 "$DB" "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name" | tr '\n' ' ' | sed 's/ $//')"
assert_eq "all tables exist" "$expected_tables" "$actual_tables"

# --- A10: watermarks exist for raw/vault/extracted ---
wm_count="$(sqlite3 "$DB" "SELECT COUNT(*) FROM watermarks")"
assert_eq "3 watermarks" "3" "$wm_count"

echo ""
echo "=== knowledge-ingest-dispatcher results: $PASS passed, $FAIL failed ==="
if [ "$FAIL" -gt 0 ]; then
  exit 1
fi
