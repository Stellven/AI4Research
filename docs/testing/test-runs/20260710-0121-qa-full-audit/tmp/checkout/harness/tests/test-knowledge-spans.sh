#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="${TMPDIR:-/tmp}/solar-knowledge-spans-test-$$"
DB="$TMP_DIR/knowledge_ingest.sqlite"
VAULT="$TMP_DIR/vault"
RAW="$TMP_DIR/raw"
SPAN_ROOT="$TMP_DIR/spans"
mkdir -p "$VAULT/concepts" "$VAULT/references" "$VAULT/synthesis" "$VAULT/projects" "$RAW/web"
trap 'rm -rf "$TMP_DIR"' EXIT

cat > "$VAULT/concepts/concept.md" <<'MD'
# Concept

Intro paragraph.

## Code

```python
def hello():
    return "world"
```

## Table

| A | B |
|---|---|
| 1 | 2 |
MD

cat > "$VAULT/references/ref.md" <<'MD'
# Reference

Evidence note.
MD

cat > "$VAULT/synthesis/syn.md" <<'MD'
# Synthesis

Synthesis note.
MD

cat > "$VAULT/projects/proj.md" <<'MD'
# Project

Project note.
MD

cat > "$RAW/web/raw.md" <<'MD'
# Raw

Raw evidence.
MD

python3 "$ROOT/lib/knowledge_ingest_dispatcher.py" --db "$DB" --json discover-vault \
  --vault "$VAULT" \
  --span-root "$SPAN_ROOT/vault" \
  --limit 10 >/tmp/knowledge-spans-vault.json

python3 "$ROOT/lib/knowledge_ingest_dispatcher.py" --db "$DB" --json discover-raw \
  --source-dir "$RAW" \
  --span-root "$SPAN_ROOT/raw" \
  --limit 10 >/tmp/knowledge-spans-raw.json

doc_count="$(sqlite3 "$DB" 'select count(*) from documents;')"
span_count="$(sqlite3 "$DB" 'select count(*) from spans;')"
test "$doc_count" = "5"
test "$span_count" -ge "5"

python3 - "$SPAN_ROOT" <<'PY'
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
sidecars = list(root.rglob("*.spans.json"))
assert sidecars, "missing span sidecars"
payloads = [json.loads(p.read_text()) for p in sidecars]
concept = next(p for p in payloads if p["source_path"].endswith("concept.md"))
texts = "\n".join(span["text"] for span in concept["spans"])
assert "def hello()" in texts
assert "| A | B |" in texts
assert [s["span_id"] for s in concept["spans"]][0] == "S001"
folders = json.loads(pathlib.Path("/tmp/knowledge-spans-vault.json").read_text())["folders"]
assert folders == ["concepts", "projects", "references", "synthesis"], folders
PY

echo "knowledge_spans ok"
