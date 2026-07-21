#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="${TMPDIR:-/tmp}/solar-knowledge-health-test-$$"
DB="$TMP_DIR/knowledge_ingest.sqlite"
PAUSE="$TMP_DIR/extract_queue.paused.json"
mkdir -p "$TMP_DIR"
trap 'rm -rf "$TMP_DIR"' EXIT

python3 "$ROOT/lib/knowledge_ingest_registry.py" --db "$DB" --json upsert-document \
  --source-kind raw \
  --source-path "$TMP_DIR/doc.md" \
  --source-adapter test \
  --source-sha256 test-sha \
  --state RAW_MATERIALIZED >/tmp/knowledge-health-doc.json

doc_id="$(python3 - <<'PY'
import json
j=json.load(open('/tmp/knowledge-health-doc.json'))
print(j['doc_id'])
PY
)"

python3 - "$DB" "$doc_id" <<'PY'
import sqlite3, sys, datetime
db, doc_id = sys.argv[1], sys.argv[2]
conn=sqlite3.connect(db)
now=datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
for i in range(8):
    job=f'job-{i}'
    conn.execute("insert into extract_jobs(job_id,doc_id,source_span_ids,prompt_template_id,model,state,created_at,updated_at) values(?,?,?,?,?,?,?,?)", (job, doc_id, 'S001', 'p', 'm', 'done', now, now))
    conn.execute("insert into validation_results(result_id,job_id,layer,passed,error_code,detail_json,ts) values(?,?,?,?,?,?,?)", (f'vr-{i}', job, 'extracted', 0 if i < 6 else 1, 'E_EVIDENCE_UNKNOWN_SPAN' if i < 6 else None, '{}', now))
conn.commit()
PY

python3 "$ROOT/lib/knowledge_ingest_health.py" --db "$DB" --pause-file "$PAUSE" audit >/tmp/knowledge-health-audit.json
python3 "$ROOT/lib/knowledge_ingest_health.py" --db "$DB" --pause-file "$PAUSE" circuit-check \
  --window 8 \
  --max-fail-rate 0.25 \
  --max-consecutive-failures 5 >/tmp/knowledge-health-circuit.json
python3 "$ROOT/lib/knowledge_ingest_health.py" --db "$DB" --pause-file "$PAUSE" health --window 8 >/tmp/knowledge-health-status.json

python3 - "$PAUSE" <<'PY'
import json, pathlib, sys
audit=json.load(open('/tmp/knowledge-health-audit.json'))
circuit=json.load(open('/tmp/knowledge-health-circuit.json'))
health=json.load(open('/tmp/knowledge-health-status.json'))
assert audit['orphan_count'] == 0
assert circuit['paused'] is True
assert pathlib.Path(sys.argv[1]).exists()
assert health['status'] == 'red'
PY

echo "knowledge_ingest_health ok"
