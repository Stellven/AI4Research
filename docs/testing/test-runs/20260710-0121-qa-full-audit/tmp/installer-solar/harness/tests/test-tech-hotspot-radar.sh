#!/usr/bin/env bash
# test-tech-hotspot-radar.sh — validate init/status/doctor/seed on temp DB
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
CLI="$PROJECT_DIR/scripts/tech_hotspot_radar.py"
CONFIG="$PROJECT_DIR/config/tech-hotspot-radar.yaml"

# Temp DB (clean for each run)
TEMP_DB="/tmp/test-tech-hotspot-radar-$$.sqlite"
cleanup() { rm -f "$TEMP_DB"; }
trap cleanup EXIT

PASS=0
FAIL=0

assert() {
    local label="$1" actual="$2" expected="$3"
    if [ "$actual" = "$expected" ]; then
        PASS=$((PASS + 1))
        echo "  PASS: $label"
    else
        FAIL=$((FAIL + 1))
        echo "  FAIL: $label — expected='$expected' got='$actual'"
    fi
}

echo "=== test-tech-hotspot-radar ==="
echo "CLI: $CLI"
echo "Config: $CONFIG"
echo "Temp DB: $TEMP_DB"
echo ""

# ── Test 1: init ────────────────────────────────────────────────
echo "--- T1: init ---"
OUT=$(python3 "$CLI" --db "$TEMP_DB" init 2>&1)
RC=$?
assert "init exit code" "$RC" "0"
assert "init creates tables" "$(echo "$OUT" | grep -c 'tables created')" "1"

# ── Test 2: table count ────────────────────────────────────────
echo "--- T2: table count ---"
TABLE_COUNT=$(python3 -c "
import sqlite3
conn = sqlite3.connect('$TEMP_DB')
cur = conn.execute(\"SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'\")
print(cur.fetchone()[0])
")
assert "35 tables created" "$TABLE_COUNT" "35"

# ── Test 3: core tables exist ──────────────────────────────────
echo "--- T3: core tables ---"
for t in youtube_channels youtube_videos youtube_video_snapshots youtube_transcripts social_accounts social_posts social_post_snapshots social_clusters github_topics github_repos github_star_snapshots hotspot_events cross_source_links hotspot_alerts pipeline_runs retry_queue _meta strategy_tracks repo_master; do
    EXISTS=$(python3 -c "
import sqlite3
conn = sqlite3.connect('$TEMP_DB')
cur = conn.execute(\"SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='$t'\")
print(cur.fetchone()[0])
")
    assert "table $t exists" "$EXISTS" "1"
done

# ── Test 4: status after init ──────────────────────────────────
echo "--- T4: status after init ---"
OUT=$(python3 "$CLI" --db "$TEMP_DB" status 2>&1)
RC=$?
assert "status exit code" "$RC" "0"
assert "status shows tables" "$(echo "$OUT" | grep -c 'tables:')" "1"

# ── Test 5: doctor after init (clean) ──────────────────────────
echo "--- T5: doctor clean ---"
OUT=$(python3 "$CLI" --db "$TEMP_DB" doctor 2>&1)
RC=$?
assert "doctor exit code (no issues)" "$RC" "0"
assert "doctor says all checks passed" "$(echo "$OUT" | grep -c 'all checks passed')" "1"

# ── Test 6: seed youtube ───────────────────────────────────────
echo "--- T6: seed youtube ---"
OUT=$(python3 "$CLI" --db "$TEMP_DB" seed youtube 2>&1)
RC=$?
assert "seed youtube exit code" "$RC" "0"
assert "seed youtube channels > 0" "$(echo "$OUT" | grep -c 'youtube channels imported: [1-9]')" "1"

YOUTUBE_COUNT=$(python3 -c "
import sqlite3
conn = sqlite3.connect('$TEMP_DB')
print(conn.execute('SELECT COUNT(*) FROM youtube_channels').fetchone()[0])
")
assert "youtube_channels >= 40" "$( [ "$YOUTUBE_COUNT" -ge 40 ] && echo 1 || echo 0 )" "1"

# ── Test 7: seed social ────────────────────────────────────────
echo "--- T7: seed social ---"
OUT=$(python3 "$CLI" --db "$TEMP_DB" seed social 2>&1)
RC=$?
assert "seed social exit code" "$RC" "0"

SOCIAL_COUNT=$(python3 -c "
import sqlite3
conn = sqlite3.connect('$TEMP_DB')
print(conn.execute('SELECT COUNT(*) FROM social_accounts').fetchone()[0])
")
assert "social_accounts >= 100" "$( [ "$SOCIAL_COUNT" -ge 100 ] && echo 1 || echo 0 )" "1"

# ── Test 8: social handle has no leading @ ──────────────────────
echo "--- T8: handle no leading @ ---"
AT_COUNT=$(python3 -c "
import sqlite3
conn = sqlite3.connect('$TEMP_DB')
cur = conn.execute(\"SELECT COUNT(*) FROM social_accounts WHERE handle LIKE '@%'\")
print(cur.fetchone()[0])
")
assert "no handle starts with @" "$AT_COUNT" "0"

# ── Test 9: social weights calculated ──────────────────────────
echo "--- T9: social weights ---"
WEIGHT_COUNT=$(python3 -c "
import sqlite3
conn = sqlite3.connect('$TEMP_DB')
cur = conn.execute('SELECT COUNT(*) FROM social_accounts WHERE weight > 1.0')
print(cur.fetchone()[0])
")
assert "some accounts have weight > 1.0" "$( [ "$WEIGHT_COUNT" -ge 10 ] && echo 1 || echo 0 )" "1"

# ── Test 10: seed github ───────────────────────────────────────
echo "--- T10: seed github ---"
OUT=$(python3 "$CLI" --db "$TEMP_DB" seed github 2>&1)
RC=$?
assert "seed github exit code" "$RC" "0"

TOPIC_COUNT=$(python3 -c "
import sqlite3
conn = sqlite3.connect('$TEMP_DB')
print(conn.execute('SELECT COUNT(*) FROM github_topics').fetchone()[0])
")
assert "github_topics == 9" "$TOPIC_COUNT" "9"

REPO_COUNT=$(python3 -c "
import sqlite3
conn = sqlite3.connect('$TEMP_DB')
print(conn.execute('SELECT COUNT(*) FROM github_repos').fetchone()[0])
")
assert "github_repos == 9" "$REPO_COUNT" "9"

# ── Test 11: seed idempotent ───────────────────────────────────
echo "--- T11: seed idempotent ---"
python3 "$CLI" --db "$TEMP_DB" seed all > /dev/null 2>&1
python3 "$CLI" --db "$TEMP_DB" seed all > /dev/null 2>&1
DOUBLE_COUNT=$(python3 -c "
import sqlite3
conn = sqlite3.connect('$TEMP_DB')
print(conn.execute('SELECT COUNT(*) FROM youtube_channels').fetchone()[0])
")
assert "idempotent: channels unchanged" "$DOUBLE_COUNT" "$YOUTUBE_COUNT"

# ── Test 12: doctor after seed ─────────────────────────────────
echo "--- T12: doctor after seed ---"
OUT=$(python3 "$CLI" --db "$TEMP_DB" doctor 2>&1)
RC=$?
assert "doctor exit code (seeded)" "$RC" "0"
assert "doctor shows youtube_channels > 0" "$(echo "$OUT" | grep -c 'youtube_channels: [1-9]')" "1"

# ── Test 13: --db override ─────────────────────────────────────
echo "--- T13: --db override ---"
TEMP_DB2="/tmp/test-thr-override-$$.sqlite"
python3 "$CLI" --db "$TEMP_DB2" init > /dev/null 2>&1
OVERRIDE_COUNT=$(python3 -c "
import sqlite3
conn = sqlite3.connect('$TEMP_DB2')
cur = conn.execute(\"SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'\")
print(cur.fetchone()[0])
")
rm -f "$TEMP_DB2"
assert "--db override creates tables" "$OVERRIDE_COUNT" "35"

# ── Test 14: existing source scripts still syntax valid ────────
echo "--- T14: existing scripts not broken ---"
for script in github_trends_digest.py youtube_influence_digest.py ai_influence_daily.py; do
    python3 -c "import ast; ast.parse(open('$PROJECT_DIR/scripts/$script').read())" 2>&1
    assert "$script syntax OK" "$?" "0"
done

# ── Test 15: schema integrity (foreign keys) ───────────────────
echo "--- T15: schema integrity ---"
FK_RESULT=$(python3 -c "
import sqlite3
conn = sqlite3.connect('$TEMP_DB')
conn.execute('PRAGMA foreign_keys=ON')
conn.execute('INSERT OR IGNORE INTO youtube_channels (channel_id, channel_name, channel_url, imported_at) VALUES (?, ?, ?, ?)',
    ('test_ch', 'Test', 'https://example.com', '2026-01-01T00:00:00Z'))
conn.execute('INSERT OR IGNORE INTO youtube_videos (video_id, channel_id, channel_name, video_url, title, fetched_at) VALUES (?, ?, ?, ?, ?, ?)',
    ('vid1', 'test_ch', 'Test', 'https://example.com/v1', 'Test Video', '2026-01-01T00:00:00Z'))
conn.execute('INSERT OR IGNORE INTO youtube_transcripts (video_id, transcript_status) VALUES (?, ?)',
    ('vid1', 'missing'))
print(1)
")
assert "FK inserts work" "$FK_RESULT" "1"

# ── Test 16: snapshot tables append-only ────────────────────────
echo "--- T16: snapshot append-only ---"
APPEND=$(python3 -c "
import sqlite3
conn = sqlite3.connect('$TEMP_DB')
conn.execute('INSERT INTO youtube_video_snapshots (video_id, view_count, snapshot_at) VALUES (?, ?, ?)',
    ('vid1', 100, '2026-01-01T00:00:00Z'))
conn.execute('INSERT INTO youtube_video_snapshots (video_id, view_count, snapshot_at) VALUES (?, ?, ?)',
    ('vid1', 150, '2026-01-02T00:00:00Z'))
count = conn.execute('SELECT COUNT(*) FROM youtube_video_snapshots WHERE video_id=\"vid1\"').fetchone()[0]
print(count)
")
assert "two snapshots for same video" "$APPEND" "2"

# ── Test 17: N1B reasoning tables exist ─────────────────────────
echo "--- T17: N1B reasoning tables ---"
for t in evidence_atoms hotspot_clusters reasoning_packets premium_reasoning_results insight_verifications token_ledger; do
    EXISTS=$(python3 -c "
import sqlite3
conn = sqlite3.connect('$TEMP_DB')
cur = conn.execute(\"SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='$t'\")
print(cur.fetchone()[0])
")
    assert "table $t exists" "$EXISTS" "1"
done

# ── Test 18: preprocess-fixture creates atoms ───────────────────
echo "--- T18: preprocess-fixture ---"
OUT=$(python3 "$CLI" --db "$TEMP_DB" preprocess-fixture 2>&1)
RC=$?
assert "preprocess-fixture exit code" "$RC" "0"
assert "preprocess-fixture creates atoms" "$(echo "$OUT" | grep -c 'created 3 evidence atoms')" "1"
ATOM_COUNT=$(python3 -c "
import sqlite3
conn = sqlite3.connect('$TEMP_DB')
print(conn.execute('SELECT COUNT(*) FROM evidence_atoms').fetchone()[0])
")
assert "3 evidence atoms in DB" "$ATOM_COUNT" "3"

# ── Test 19: premium-gate-fixture ───────────────────────────────
echo "--- T19: premium-gate-fixture ---"
OUT=$(python3 "$CLI" --db "$TEMP_DB" premium-gate-fixture 2>&1)
RC=$?
assert "premium-gate-fixture exit code" "$RC" "0"
assert "low-score blocked" "$(echo "$OUT" | grep -c 'low-score blocked: True')" "1"
assert "critical allowed" "$(echo "$OUT" | grep -c 'critical allowed: True')" "1"
assert "cross-source allowed" "$(echo "$OUT" | grep -c 'cross-source allowed: True')" "1"

# ── Test 20: model-router-test ──────────────────────────────────
echo "--- T20: model-router-test ---"
OUT=$(python3 "$CLI" --db "$TEMP_DB" model-router-test 2>&1)
RC=$?
assert "model-router-test exit code" "$RC" "0"
assert "repo_analysis route" "$(echo "$OUT" | grep -c 'repo_analysis.*PASS')" "1"
assert "viewpoint_synthesis route" "$(echo "$OUT" | grep -c 'viewpoint_synthesis.*PASS')" "1"
assert "long_context route" "$(echo "$OUT" | grep -c 'long_context_cross_source_analysis.*PASS')" "1"
assert "cheap_preprocess route" "$(echo "$OUT" | grep -c 'cheap_preprocess.*PASS')" "1"

# ── Test 21: budget-trim-test ──────────────────────────────────
echo "--- T21: budget-trim-test ---"
OUT=$(python3 "$CLI" --db "$TEMP_DB" budget-trim-test 2>&1)
RC=$?
assert "budget-trim-test exit code" "$RC" "0"

# ── Test 22: premium-mock-test ──────────────────────────────────
echo "--- T22: premium-mock-test ---"
OUT=$(python3 "$CLI" --db "$TEMP_DB" premium-mock-test 2>&1)
RC=$?
assert "premium-mock-test exit code" "$RC" "0"
assert "no raw text in packet" "$(echo "$OUT" | grep -c 'PASS: no raw text')" "1"

# ── Test 23: verifier-fixture ──────────────────────────────────
echo "--- T23: verifier-fixture ---"
OUT=$(python3 "$CLI" --db "$TEMP_DB" verifier-fixture 2>&1)
RC=$?
assert "verifier-fixture exit code" "$RC" "0"
assert "unsupported claim flagged" "$(echo "$OUT" | grep -c 'unsupported claims flagged: [1-9]')" "1"

# ── Test 24: YouTube fixture (N2 ACs 1-9) ───────────────────────
echo "--- T24: youtube-fixture ---"
OUT=$(python3 "$CLI" --db "$TEMP_DB" youtube-fixture 2>&1)
RC=$?
assert "youtube-fixture exit code" "$RC" "0"
assert "AC1 channels >= 50 PASS" "$(echo "$OUT" | grep -c 'AC1 channels >= 50.*PASS')" "1"
assert "AC2 normalization PASS" "$(echo "$OUT" | grep -c 'AC2 normalization.*PASS')" "1"
assert "AC3 video dedup PASS" "$(echo "$OUT" | grep -c 'AC3 video dedup.*PASS')" "1"
assert "AC4 snapshot append PASS" "$(echo "$OUT" | grep -c 'AC4 snapshot append.*PASS')" "1"
assert "AC5 transcript txt PASS" "$(echo "$OUT" | grep -c 'AC5 transcript txt.*PASS')" "1"
assert "AC6 transcript jsonl PASS" "$(echo "$OUT" | grep -c 'AC6 transcript jsonl.*PASS')" "1"
assert "AC7 retry queue PASS" "$(echo "$OUT" | grep -c 'AC7 retry queue.*PASS')" "1"
assert "AC8 hot score PASS" "$(echo "$OUT" | grep -c 'AC8 hot score.*PASS')" "1"
assert "AC9 evidence atoms PASS" "$(echo "$OUT" | grep -c 'AC9 evidence atoms.*PASS')" "1"

# ── Test 25: Social fixture (N3 ACs 1-9) ────────────────────────
echo "--- T25: social-fixture ---"
OUT=$(python3 "$CLI" --db "$TEMP_DB" social-fixture 2>&1)
RC=$?
assert "social-fixture exit code" "$RC" "0"
assert "AC1 accounts imported PASS" "$(echo "$OUT" | grep -c 'AC1 accounts imported.*PASS')" "1"
assert "AC2 handles with @ PASS" "$(echo "$OUT" | grep -c 'AC2 handles.*PASS')" "1"
assert "AC3 weighted accounts PASS" "$(echo "$OUT" | grep -c 'AC3 weighted accounts.*PASS')" "1"
assert "AC4 post fixture fields PASS" "$(echo "$OUT" | grep -c 'AC4 post fixture fields.*PASS')" "1"
assert "AC5 event classifier PASS" "$(echo "$OUT" | grep -c 'AC5 event classifier.*PASS')" "1"
assert "AC6 clustering PASS" "$(echo "$OUT" | grep -c 'AC6 clustering.*PASS')" "1"
assert "AC7 hot score PASS" "$(echo "$OUT" | grep -c 'AC7 hot score.*PASS')" "1"
assert "AC8 failure isolation PASS" "$(echo "$OUT" | grep -c 'AC8 failure isolation.*PASS')" "1"
assert "AC9 evidence atoms PASS" "$(echo "$OUT" | grep -c 'AC9 evidence atoms.*PASS')" "1"

# ── Test 26: GitHub fixture (N4 ACs 1-9) ────────────────────────
echo "--- T26: github-fixture ---"
OUT=$(python3 "$CLI" --db "$TEMP_DB" github-fixture 2>&1)
RC=$?
assert "github-fixture exit code" "$RC" "0"
assert "AC1 topics PASS" "$(echo "$OUT" | grep -c 'AC1 topics.*PASS')" "1"
assert "AC2 repos PASS" "$(echo "$OUT" | grep -c 'AC2 repos.*PASS')" "1"
assert "AC3 repo metadata PASS" "$(echo "$OUT" | grep -c 'AC3 repo metadata.*PASS')" "1"
assert "AC4 star snapshots PASS" "$(echo "$OUT" | grep -c 'AC4 star snapshots.*PASS')" "1"
assert "AC5 snapshot_id PASS" "$(echo "$OUT" | grep -c 'AC5 snapshot_id.*PASS')" "1"
assert "AC6 star deltas PASS" "$(echo "$OUT" | grep -c 'AC6 star deltas.*PASS')" "1"
assert "AC7 trend buckets PASS" "$(echo "$OUT" | grep -c 'AC7 trend buckets.*PASS')" "1"
assert "AC8 alerts PASS" "$(echo "$OUT" | grep -c 'AC8 alerts.*PASS')" "1"
assert "AC9 evidence atoms PASS" "$(echo "$OUT" | grep -c 'AC9 evidence atoms.*PASS')" "1"

# ── Test 27: Report fixture (N5 ACs 1-8) ───────────────────────
echo "--- T27: report-fixture ---"
REPORT_DIR="/tmp/test-thr-report-$$"
mkdir -p "$REPORT_DIR"
OUT=$(python3 "$CLI" --db "$TEMP_DB" report-fixture 2>&1)
RC=$?
assert "report-fixture exit code" "$RC" "0"
assert "AC1 source reports PASS" "$(echo "$OUT" | grep -c 'AC1 source reports.*PASS')" "1"
assert "AC2 unified overview PASS" "$(echo "$OUT" | grep -c 'AC2 unified overview.*PASS')" "1"
assert "AC3 cross-source links PASS" "$(echo "$OUT" | grep -c 'AC3 cross-source links.*PASS')" "1"
assert "AC4 alerts JSON PASS" "$(echo "$OUT" | grep -c 'AC4 alerts JSON.*PASS')" "1"
assert "AC5 transcript package PASS" "$(echo "$OUT" | grep -c 'AC5 transcript package.*PASS')" "1"
assert "AC6 HTML report PASS" "$(echo "$OUT" | grep -c 'AC6 HTML report.*PASS')" "1"
assert "AC7 artifacts PASS" "$(echo "$OUT" | grep -c 'AC7 artifacts.*PASS')" "1"
assert "AC8 wiki dispatch PASS" "$(echo "$OUT" | grep -c 'AC8 wiki dispatch.*PASS')" "1"
rm -rf "$REPORT_DIR"

# ── Summary ─────────────────────────────────────────────────────
echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
exit $FAIL
