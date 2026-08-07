#!/usr/bin/env bash
# Test suite for apple_notes_ingest.py
# Does NOT require real Apple Notes permission — uses APPLE_NOTES_MOCK_DIR fixtures.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ADAPTER="$SCRIPT_DIR/../lib/apple_notes_ingest.py"
PASS=0; FAIL=0

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# Isolation env
export HARNESS_DIR="$TMP/harness"
export ECC_HOME_OVERRIDE="$TMP/home"
export APPLE_NOTES_MOCK_DIR="$TMP/mock_notes"
export APPLE_NOTES_WECHAT_HTML_FILE="$TMP/wechat-article.html"

mkdir -p "$HARNESS_DIR/config" "$HARNESS_DIR/state/apple-notes-ingest" \
         "$HARNESS_DIR/logs" "$TMP/home/Library/LaunchAgents" \
         "$APPLE_NOTES_MOCK_DIR"

# Write test config
cat > "$HARNESS_DIR/config/apple-notes-ingest.json" <<'EOF'
{
  "notes_folder": "Solar Inbox",
  "tags": ["#solar-ingest"],
  "interval_seconds": 3600,
  "raw_dir": "",
  "all_notes": false
}
EOF

# Set raw_dir dynamically
RAW_DIR="$TMP/Knowledge/_raw/apple-notes"
python3 -c "
import json, sys
cfg = json.load(open('$HARNESS_DIR/config/apple-notes-ingest.json'))
cfg['raw_dir'] = '$RAW_DIR'
json.dump(cfg, open('$HARNESS_DIR/config/apple-notes-ingest.json','w'), indent=2)
"

# Write mock notes
cat > "$APPLE_NOTES_MOCK_DIR/note1.json" <<'EOF'
{
  "note_id": "note-abc001",
  "title": "WeChat Article Test",
  "modified_at": "2026-05-08T10:00:00Z",
  "created_at": "2026-05-08T09:00:00Z",
  "source_url": "https://mp.weixin.qq.com/s/test123",
  "body": "This is a test article about AI. Contact: test@example.com Phone: 13812345678",
  "source_app": "WeChat"
}
EOF

cat > "$APPLE_NOTES_WECHAT_HTML_FILE" <<'EOF'
<!doctype html>
<html>
<body>
  <h1 id="activity-name">微信深度文章标题</h1>
  <div id="js_content">
    <p>第一段：这是从微信网页正文提取出来的知识内容。</p>
    <p>第二段：不是 Apple Notes 里的短链接正文。</p>
  </div>
</body>
</html>
EOF

cat > "$APPLE_NOTES_MOCK_DIR/note2.json" <<'EOF'
{
  "note_id": "x-coredata://7376A57E-4EF9-49E2-A514-9B6455241B61/ICNote/p20",
  "title": "Second Note",
  "modified_at": "2026-05-08T11:00:00Z",
  "created_at": "2026-05-08T11:00:00Z",
  "source_url": "",
  "body": "Another note content. Bearer eyJhbGciOiJIUzI1NiJ9.test.token123456789",
  "source_app": "Apple Notes"
}
EOF

# ---------------------------------------------------------------------------
run_test() {
  local name="$1"; shift
  if "$@" >/dev/null 2>&1; then
    echo "PASS: $name"; PASS=$((PASS+1))
  else
    echo "FAIL: $name"; FAIL=$((FAIL+1))
  fi
}

assert_json_key() {
  local name="$1"; local output="$2"; local key="$3"
  if echo "$output" | python3 -c "import json,sys; d=json.load(sys.stdin); assert '$key' in d" 2>/dev/null; then
    echo "PASS: $name"; PASS=$((PASS+1))
  else
    echo "FAIL: $name (missing key '$key' in output)"; FAIL=$((FAIL+1))
  fi
}

assert_json_value() {
  local name="$1"; local output="$2"; local expr="$3"
  if echo "$output" | python3 -c "import json,sys; d=json.load(sys.stdin); $expr" 2>/dev/null; then
    echo "PASS: $name"; PASS=$((PASS+1))
  else
    echo "FAIL: $name (assertion failed: $expr)"; FAIL=$((FAIL+1))
  fi
}

# ---------------------------------------------------------------------------
# A1 — doctor returns notes_access + target_folder
OUT=$(python3 "$ADAPTER" doctor --json 2>/dev/null)
assert_json_key "A1-doctor-notes_access" "$OUT" "notes_access"
assert_json_key "A1-doctor-target_folder" "$OUT" "target_folder"

# A8 — config.all_notes is False
assert_json_value "A8-config-all_notes-false" "$OUT" "assert d['config']['all_notes'] is False"

# A2 — dry-run returns candidates + dry_run=True, no files written
OUT=$(python3 "$ADAPTER" scan --dry-run --json 2>/dev/null)
assert_json_key "A2-dry-run-candidates" "$OUT" "candidates"
assert_json_value "A2-dry-run-flag" "$OUT" "assert d['dry_run'] is True"
run_test "A2-dry-run-no-files" bash -c "! ls '$RAW_DIR' 2>/dev/null | grep -q '.md'"

# A3 — scan exports .md files
OUT=$(python3 "$ADAPTER" scan --json 2>/dev/null)
assert_json_key "A3-scan-exported-key" "$OUT" "exported"
assert_json_value "A3-scan-exported-count-gt0" "$OUT" "assert d['exported_count'] > 0"
run_test "A3-md-files-exist" bash -c "find '$RAW_DIR' -name '*.md' | grep -q '.'"

# Verify frontmatter in exported file
EXPORTED_FILE=$(find "$RAW_DIR" -name "*abc001*.md" | head -1)
if [[ -n "$EXPORTED_FILE" ]]; then
  run_test "A3-frontmatter-source" grep -q "source: \"apple-notes\"" "$EXPORTED_FILE"
  run_test "A3-frontmatter-note_id" grep -q "note_id:" "$EXPORTED_FILE"
  run_test "A3-frontmatter-ingest_status" grep -q "ingest_status:" "$EXPORTED_FILE"
  run_test "A3-wechat-fetch-status" grep -q "wechat_fetch_status: \"ok\"" "$EXPORTED_FILE"
  run_test "A3-wechat-web-body" grep -q "微信网页正文提取出来的知识内容" "$EXPORTED_FILE"
else
  echo "FAIL: A3-md-file-missing"; FAIL=$((FAIL+1))
  echo "FAIL: A3-frontmatter-source"; FAIL=$((FAIL+1))
  echo "FAIL: A3-frontmatter-note_id"; FAIL=$((FAIL+1))
  echo "FAIL: A3-frontmatter-ingest_status"; FAIL=$((FAIL+1))
  echo "FAIL: A3-wechat-fetch-status"; FAIL=$((FAIL+1))
  echo "FAIL: A3-wechat-web-body"; FAIL=$((FAIL+1))
fi

# A4 — delta manifest prevents duplicates (second scan exports 0)
OUT2=$(python3 "$ADAPTER" scan --json 2>/dev/null)
assert_json_value "A4-idempotent-no-duplicates" "$OUT2" "assert d['exported_count'] == 0"
run_test "A4-manifest-exists" test -s "$HARNESS_DIR/state/apple-notes-ingest/manifest.json"

# Verify manifest has note entries
run_test "A4-manifest-has-notes" python3 -c "
import json
m = json.load(open('$HARNESS_DIR/state/apple-notes-ingest/manifest.json'))
assert len(m['notes']) > 0
"

# A4b — content hash prevents delete/recreate duplicates with a new note_id
cat > "$APPLE_NOTES_MOCK_DIR/note3.json" <<'EOF'
{
  "note_id": "note-recreated001",
  "title": "Recreated WeChat Article Test",
  "modified_at": "2026-05-08T12:00:00Z",
  "created_at": "2026-05-08T12:00:00Z",
  "source_url": "https://mp.weixin.qq.com/s/test123",
  "body": "This is a test article about AI. Contact: test@example.com Phone: 13812345678",
  "source_app": "WeChat"
}
EOF
OUT3=$(python3 "$ADAPTER" scan --json 2>/dev/null)
assert_json_value "A4b-recreated-note-no-export" "$OUT3" "assert d['exported_count'] == 0"
run_test "A4b-manifest-duplicate-status" python3 -c "
import json
m = json.load(open('$HARNESS_DIR/state/apple-notes-ingest/manifest.json'))
r = m['notes']['note-recreated001']
assert r['ingest_status'] == 'duplicate'
assert r['duplicate_of'] == 'note-abc001'
assert m['content_index'][r['content_hash']]['note_id'] == 'note-abc001'
"

# A5 — force-dispatch creates dispatches list
OUT=$(python3 "$ADAPTER" scan --force-dispatch --json 2>/dev/null)
assert_json_key "A5-force-dispatch-key" "$OUT" "dispatches"
assert_json_key "A5-wiki-dispatch-key" "$OUT" "wiki_dispatches"
assert_json_value "A5-dispatches-not-empty" "$OUT" "assert len(d['dispatches']) > 0"
assert_json_value "A5-wiki-dispatches-not-empty" "$OUT" "assert len(d['wiki_dispatches']) > 0"

# Verify dispatch file content
DISPATCH_FILE=$(echo "$OUT" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['dispatches'][0])" 2>/dev/null || true)
if [[ -n "$DISPATCH_FILE" ]] && [[ -f "$DISPATCH_FILE" ]]; then
  run_test "A5-dispatch-instructions" python3 -c "
import json
d = json.load(open('$DISPATCH_FILE'))
assert 'instructions' in d
assert 'concepts' in d['instructions']['extract']
"
else
  echo "FAIL: A5-dispatch-file-missing"; FAIL=$((FAIL+1))
fi

WIKI_DISPATCH_FILE=$(echo "$OUT" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['wiki_dispatches'][0])" 2>/dev/null || true)
if [[ -n "$WIKI_DISPATCH_FILE" ]] && [[ -f "$WIKI_DISPATCH_FILE" ]]; then
  run_test "A5-wiki-dispatch-frontmatter" grep -q "skill: wiki-ingest" "$WIKI_DISPATCH_FILE"
  run_test "A5-wiki-dispatch-source" grep -q "project=apple-notes" "$WIKI_DISPATCH_FILE"
else
  echo "FAIL: A5-wiki-dispatch-file-missing"; FAIL=$((FAIL+1))
fi

# A6 — install-scheduler --dry-run returns interval_seconds
OUT=$(python3 "$ADAPTER" install-scheduler --interval 7200 --dry-run --json 2>/dev/null)
assert_json_value "A6-scheduler-interval" "$OUT" "assert d['interval_seconds'] == 7200"
assert_json_value "A6-scheduler-dry-run" "$OUT" "assert d['dry_run'] is True"
# Verify plist not written in dry-run
run_test "A6-no-plist-written" bash -c "! test -f '$TMP/home/Library/LaunchAgents/com.solar.apple-notes-ingest.plist'"

# Privacy / Redaction
EXPORTED_CONTENT=$(cat "$RAW_DIR"/*/note-abc001*.md 2>/dev/null || find "$RAW_DIR" -name "*.md" | head -1 | xargs cat 2>/dev/null || true)
if [[ -n "$EXPORTED_CONTENT" ]]; then
  run_test "Redaction-email-removed" bash -c "! echo '$EXPORTED_CONTENT' | grep -q 'test@example.com'"
  run_test "Redaction-phone-removed" bash -c "! echo '$EXPORTED_CONTENT' | grep -q '13812345678'"
  run_test "Redaction-token-removed" bash -c "! echo '$EXPORTED_CONTENT' | grep -q 'Bearer eyJ'"
else
  echo "SKIP: Redaction tests (no exported content found)"
fi

# status command
OUT=$(python3 "$ADAPTER" status --json 2>/dev/null)
assert_json_key "status-ok" "$OUT" "ok"
assert_json_key "status-last_scan_at" "$OUT" "last_scan_at"

# uninstall-scheduler dry-run
OUT=$(python3 "$ADAPTER" uninstall-scheduler --dry-run --json 2>/dev/null)
assert_json_key "uninstall-scheduler-ok" "$OUT" "ok"

# ---------------------------------------------------------------------------
echo ""
echo "═══════════════════════════════════"
echo "PASS=$PASS FAIL=$FAIL"
echo "═══════════════════════════════════"

[[ $FAIL -eq 0 ]]
