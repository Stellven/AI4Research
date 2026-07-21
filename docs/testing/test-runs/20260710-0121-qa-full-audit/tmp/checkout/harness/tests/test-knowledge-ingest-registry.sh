#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="${TMPDIR:-/tmp}/solar-knowledge-registry-test-$$"
DB="$TMP_DIR/knowledge_ingest.sqlite"
mkdir -p "$TMP_DIR"
trap 'rm -rf "$TMP_DIR"' EXIT

python3 "$ROOT/lib/knowledge_ingest_registry.py" --db "$DB" --json migrate >/dev/null
python3 "$ROOT/lib/knowledge_ingest_registry.py" --db "$DB" --json migrate >/dev/null

tables="$(sqlite3 "$DB" '.tables')"
for table in documents spans ingest_events qmd_index_events extract_jobs extract_outputs validation_results relations watermarks migration_log; do
  if ! grep -q "$table" <<<"$tables"; then
    echo "missing table: $table" >&2
    exit 1
  fi
done

python3 "$ROOT/lib/knowledge_ingest_registry.py" --db "$DB" --json upsert-document \
  --source-kind obsidian_vault \
  --source-path "$TMP_DIR/example.md" \
  --source-adapter obsidian_adapter \
  --declared-doc-type concept \
  --state VAULT_DISCOVERED >/dev/null

doc_count="$(sqlite3 "$DB" 'select count(*) from documents;')"
event_count="$(sqlite3 "$DB" 'select count(*) from ingest_events;')"
watermark_count="$(sqlite3 "$DB" 'select count(*) from watermarks;')"

test "$doc_count" = "1"
test "$event_count" = "1"
test "$watermark_count" = "3"

echo "knowledge_ingest_registry ok"
