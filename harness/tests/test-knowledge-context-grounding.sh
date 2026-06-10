#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="${TMPDIR:-/tmp}/solar-knowledge-context-grounding-test-$$"
mkdir -p "$TMP_DIR/_extracted" "$TMP_DIR/_raw"
trap 'rm -rf "$TMP_DIR"' EXIT

cat > "$TMP_DIR/_extracted/sample.extracted.md" <<'MD'
---
source_path: /tmp/source/raw.md
source_sha256: abcdef1234567890
---

# Semantic Extraction

Evidence: raw:S001
MD

PYTHONPATH="$ROOT/lib" python3 - "$TMP_DIR/_extracted/sample.extracted.md" <<'PY'
import importlib.util, pathlib, sys
mod_path = pathlib.Path("${HOME}/Solar/harness/lib/solar-knowledge-context.py")
spec = importlib.util.spec_from_file_location("skc", mod_path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
hit = {"path": sys.argv[1], "id": sys.argv[1], "title": "sample", "snippet": "derived snippet", "score": 1.0}
out = mod._ground_derived_hit(hit)
assert out["derived"] is True
assert out["grounding_required"] is True
assert out["source_doc_path"] == "/tmp/source/raw.md"
assert "DERIVED" in out["snippet"]
PY

echo "knowledge_context_grounding ok"
