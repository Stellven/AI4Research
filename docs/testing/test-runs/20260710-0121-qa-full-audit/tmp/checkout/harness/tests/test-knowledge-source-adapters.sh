#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="${TMPDIR:-/tmp}/solar-knowledge-source-adapters-test-$$"
DB="$TMP_DIR/knowledge_ingest.sqlite"
RAW="$TMP_DIR/raw"
mkdir -p "$RAW/chatgpt-extension-inbox" "$RAW/github-trends-digest/2026-05-24" "$RAW/youtube-influence-digest/asr" "$RAW/solar-harness/accepted" "$RAW/web-captures" "$RAW/ai-influence-daily-digest"
trap 'rm -rf "$TMP_DIR"' EXIT

printf '{"title":"ChatGPT Test","messages":[{"role":"user","content":"hello"}]}\n' > "$RAW/chatgpt-extension-inbox/chat.json"
printf '# GitHub Digest\n' > "$RAW/github-trends-digest/2026-05-24/digest.md"
printf 'transcript text\n' > "$RAW/youtube-influence-digest/asr/latest-asr.txt"
printf '# Accepted\n' > "$RAW/solar-harness/accepted/sprint.accepted.md"
printf '<html><body>web</body></html>\n' > "$RAW/web-captures/page.html"
printf '# Social Signal\n' > "$RAW/ai-influence-daily-digest/item.md"

python3 "$ROOT/lib/knowledge_ingest_dispatcher.py" --db "$DB" --json discover-sources \
  --source-dir "$RAW" \
  --materialized-root "$TMP_DIR/materialized" \
  --span-root "$TMP_DIR/spans" \
  --limit 20 >/tmp/knowledge-source-adapters.json

python3 - "$DB" <<'PY'
import sqlite3, sys
conn=sqlite3.connect(sys.argv[1])
rows=dict(conn.execute("select source_kind,count(*) from documents group by source_kind").fetchall())
for key in ["raw_chatgpt","raw_github","raw_youtube","accepted_sprint","raw_web","raw_social"]:
    assert rows.get(key) == 1, (key, rows)
assert conn.execute("select count(*) from spans").fetchone()[0] >= 6
PY

grep -q 'raw_chatgpt' /tmp/knowledge-source-adapters.json
grep -q 'raw_github' /tmp/knowledge-source-adapters.json
grep -q 'raw_youtube' /tmp/knowledge-source-adapters.json
grep -q 'raw_social' /tmp/knowledge-source-adapters.json

echo "knowledge_source_adapters ok"
