#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="${TMPDIR:-/tmp}/solar-knowledge-extract-json-test-$$"
mkdir -p "$TMP_DIR"
trap 'rm -rf "$TMP_DIR"' EXIT

cat > "$TMP_DIR/source.md" <<'MD'
# Dispatcher

QMD remains the deterministic indexing layer.

ThunderOMLX is the semantic extraction layer.
MD

python3 "$ROOT/lib/knowledge_spans.py" \
  --source "$TMP_DIR/source.md" \
  --doc-id "raw:test:source" \
  --source-kind raw \
  --output "$TMP_DIR/source.spans.json" \
  --json >/dev/null

python3 "$ROOT/lib/knowledge_extract_json.py" extract-sidecar \
  --sidecar "$TMP_DIR/source.spans.json" \
  --output-dir "$TMP_DIR/out" \
  --doc-type design \
  --mock >/tmp/knowledge-extract-json-result.json

candidate="$(python3 - <<'PY'
import json
j=json.load(open('/tmp/knowledge-extract-json-result.json'))
print(j['candidate'])
PY
)"
markdown="$(python3 - <<'PY'
import json
j=json.load(open('/tmp/knowledge-extract-json-result.json'))
print(j['markdown'])
PY
)"

python3 - "$candidate" "$markdown" <<'PY'
import json, pathlib, sys
c=json.loads(pathlib.Path(sys.argv[1]).read_text())
m=pathlib.Path(sys.argv[2]).read_text()
assert c["schema_version"] == "extracted-json-v2"
assert c["summary"]["evidence"] == ["S001"]
assert "source_sha256:" in m
assert "schema_version: extracted-json-v2" in m
assert "# Semantic Extraction" in m
assert "Evidence: raw:S001" in m
assert "## Core Facts" in m
assert "## Functional Modules" in m
PY

echo "knowledge_extract_json ok"
