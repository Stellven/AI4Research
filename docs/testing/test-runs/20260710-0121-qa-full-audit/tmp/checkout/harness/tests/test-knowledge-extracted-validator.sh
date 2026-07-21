#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="${TMPDIR:-/tmp}/solar-knowledge-validator-test-$$"
mkdir -p "$TMP_DIR"
trap 'rm -rf "$TMP_DIR"' EXIT

cat > "$TMP_DIR/source.md" <<'MD'
# Validator

Only claims with known span evidence may enter the extracted index.
MD

python3 "$ROOT/lib/knowledge_spans.py" \
  --source "$TMP_DIR/source.md" \
  --doc-id "raw:test:validator" \
  --source-kind raw \
  --output "$TMP_DIR/source.spans.json" \
  --json >/dev/null

python3 "$ROOT/lib/knowledge_extract_json.py" extract-sidecar \
  --sidecar "$TMP_DIR/source.spans.json" \
  --output-dir "$TMP_DIR/out" \
  --doc-type design \
  --mock >/tmp/knowledge-validator-extract.json

candidate="$(python3 - <<'PY'
import json
j=json.load(open('/tmp/knowledge-validator-extract.json'))
print(j['candidate'])
PY
)"

python3 "$ROOT/lib/knowledge_extracted_validator.py" validate \
  --candidate "$candidate" \
  --sidecar "$TMP_DIR/source.spans.json" >/tmp/knowledge-validator-pass.json

python3 - "$candidate" "$TMP_DIR/bad.json" <<'PY'
import json, pathlib, sys
c=json.loads(pathlib.Path(sys.argv[1]).read_text())
c["summary"]["evidence"] = ["S999"]
c["core_facts"][0]["evidence"] = ["S999"]
pathlib.Path(sys.argv[2]).write_text(json.dumps(c, ensure_ascii=False, indent=2))
PY

if python3 "$ROOT/lib/knowledge_extracted_validator.py" validate \
  --candidate "$TMP_DIR/bad.json" \
  --sidecar "$TMP_DIR/source.spans.json" >/tmp/knowledge-validator-bad.json; then
  echo "expected validator failure" >&2
  exit 1
fi

grep -q 'E_EVIDENCE_UNKNOWN_SPAN' /tmp/knowledge-validator-bad.json

python3 "$ROOT/lib/knowledge_extracted_validator.py" process \
  --candidate "$TMP_DIR/bad.json" \
  --sidecar "$TMP_DIR/source.spans.json" \
  --quarantine-dir "$TMP_DIR/quarantine" >/tmp/knowledge-validator-process.json

grep -q 'repaired_validated' /tmp/knowledge-validator-process.json

python3 - "$candidate" "$TMP_DIR/poison.json" <<'PY'
import json, pathlib, sys
c=json.loads(pathlib.Path(sys.argv[1]).read_text())
c["summary"]["evidence"] = ["S999"]
c["core_facts"] = [{"claim": "bad", "evidence": ["S999"], "confidence": "high"}]
pathlib.Path(sys.argv[2]).write_text(json.dumps(c, ensure_ascii=False, indent=2))
PY

echo '{"doc_id":"raw:test:validator","source_sha256":"empty","source_kind":"raw","schema_version":"spans-v1","spans":[]}' > "$TMP_DIR/empty.spans.json"
echo '{"doc_id":"raw:test:validator","source_sha256":"empty","source_kind":"raw","doc_type":"design","schema_version":"extracted-json-v2","summary":{"claim":"x","evidence":["S999"]},"core_facts":[{"claim":"x","evidence":["S999"],"confidence":"high"}]}' > "$TMP_DIR/unrepairable.json"

if python3 "$ROOT/lib/knowledge_extracted_validator.py" process \
  --candidate "$TMP_DIR/unrepairable.json" \
  --sidecar "$TMP_DIR/empty.spans.json" \
  --quarantine-dir "$TMP_DIR/quarantine" >/tmp/knowledge-validator-quarantine.json; then
  echo "expected quarantine failure" >&2
  exit 1
fi

grep -q 'quarantined' /tmp/knowledge-validator-quarantine.json

echo "knowledge_extracted_validator ok"
