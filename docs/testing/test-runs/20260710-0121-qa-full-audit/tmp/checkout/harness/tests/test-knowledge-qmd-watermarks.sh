#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="${TMPDIR:-/tmp}/solar-knowledge-qmd-test-$$"
DB="$TMP_DIR/knowledge_ingest.sqlite"
mkdir -p "$TMP_DIR"
trap 'rm -rf "$TMP_DIR"' EXIT

python3 "$ROOT/lib/knowledge_ingest_registry.py" --db "$DB" --json migrate >/dev/null
python3 "$ROOT/lib/knowledge_ingest_registry.py" --db "$DB" --json upsert-document \
  --source-kind raw \
  --source-path "$TMP_DIR/doc.md" \
  --source-adapter test \
  --source-sha256 test-sha \
  --state RAW_MATERIALIZED >/tmp/knowledge-qmd-doc.json
doc_id="$(python3 - <<'PY'
import json
j=json.load(open('/tmp/knowledge-qmd-doc.json'))
print(j['doc_id'])
PY
)"
python3 "$ROOT/lib/knowledge_qmd_indexer.py" --db "$DB" watermarks >/tmp/knowledge-qmd-watermarks-before.json
python3 "$ROOT/lib/knowledge_qmd_indexer.py" --db "$DB" mark-indexed --layer extracted --batch-id test-batch --doc-id "$doc_id" >/tmp/knowledge-qmd-mark.json
python3 "$ROOT/lib/knowledge_qmd_indexer.py" --db "$DB" watermarks >/tmp/knowledge-qmd-watermarks-after.json

python3 - "$DB" <<'PY'
import json, sqlite3, sys
before=json.load(open('/tmp/knowledge-qmd-watermarks-before.json'))
after=json.load(open('/tmp/knowledge-qmd-watermarks-after.json'))
assert [w['layer'] for w in before['watermarks']] == ['extracted', 'raw', 'vault']
wm={w['layer']:w for w in after['watermarks']}
assert wm['extracted']['last_batch_id'] == 'test-batch'
assert wm['extracted']['last_indexed_ts']
conn=sqlite3.connect(sys.argv[1])
assert conn.execute('select count(*) from qmd_index_events').fetchone()[0] == 1
PY

echo "knowledge_qmd_watermarks ok"
