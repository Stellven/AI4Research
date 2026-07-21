#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="${TMPDIR:-/tmp}/solar-knowledge-sample-quota-test-$$"
VAULT="$TMP_DIR/Knowledge"
mkdir -p "$VAULT/_raw/.spans" "$VAULT/_vault_index/spans" "$TMP_DIR/out"
trap 'rm -rf "$TMP_DIR"' EXIT

make_sidecar() {
  local dir="$1"
  local kind="$2"
  local idx="$3"
  local doc_id="${kind}:${idx}"
  cat >"$dir/${kind}_${idx}.spans.json" <<JSON
{
  "doc_id": "$doc_id",
  "schema_version": "spans-v1",
  "source_kind": "$kind",
  "source_path": "$TMP_DIR/${kind}_${idx}.md",
  "source_sha256": "sha-$kind-$idx",
  "spans": [
    {
      "span_id": "S001",
      "start_line": 1,
      "end_line": 1,
      "heading_path": [],
      "text_sha256": "text-sha-$kind-$idx",
      "char_count": 32,
      "text": "sample text for $kind $idx"
    }
  ]
}
JSON
}

for i in 1 2; do
  make_sidecar "$VAULT/_raw/.spans" raw_chatgpt "$i"
  make_sidecar "$VAULT/_raw/.spans" raw_youtube "$i"
  make_sidecar "$VAULT/_vault_index/spans" obsidian_vault "$i"
done

python3 "$ROOT/scripts/knowledge_ingest_sample_backfill.py" \
  --vault "$VAULT" \
  --quota-per-class 2 \
  --source-kinds raw_chatgpt,raw_youtube,obsidian_vault \
  --output-dir "$TMP_DIR/out" \
  --report "$TMP_DIR/report.md" >/tmp/knowledge-sample-quota-ok.json

python3 - <<'PY'
import json
data=json.load(open('/tmp/knowledge-sample-quota-ok.json'))
assert data["ok"] is True
assert data["total"] == 6
for kind in ["raw_chatgpt", "raw_youtube", "obsidian_vault"]:
    assert data["by_source_kind"][kind]["enough_sample"] is True
    assert data["by_source_kind"][kind]["pass_rate"] == 1.0
PY

echo "knowledge_sample_quota ok"
