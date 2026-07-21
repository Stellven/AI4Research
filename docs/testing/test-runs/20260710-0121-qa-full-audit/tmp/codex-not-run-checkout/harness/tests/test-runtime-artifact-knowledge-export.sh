#!/usr/bin/env bash
set -euo pipefail

SCRIPT="${RUNTIME_ARTIFACT_EXPORTER:-${HOME}/.solar/harness/tools/runtime-artifact-knowledge-export.py}"
if [[ ! -f "$SCRIPT" ]]; then
  SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/tools/runtime-artifact-knowledge-export.py"
fi

python3 -m py_compile "$SCRIPT"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

python3 - "$SCRIPT" <<'PY'
import importlib.util
import json
import os
from pathlib import Path
import sys

script = Path(sys.argv[1])
spec = importlib.util.spec_from_file_location("runtime_artifact_export", script)
mod = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(mod)

tmp = Path(os.environ.get("TMPDIR", "/tmp")) / "runtime-artifact-export-unit"
tmp.mkdir(parents=True, exist_ok=True)
p = tmp / "sprint-20260521-demo.contract.md"
p.write_text("api_key=sk-secret123456\nAuthorization: Bearer tokenvalue\n# Contract\n", encoding="utf-8")
body, meta = mod.render_export(p)
assert meta["artifact_kind"] == "contract"
assert meta["sprint_id"] == "sprint-20260521-demo"
assert "sk-secret" not in body
assert "Bearer tokenvalue" not in body
assert "REDACTED" in body
print(json.dumps({"ok": True, "kind": meta["artifact_kind"]}))
PY

echo "ok - runtime artifact exporter redaction/kind/id test passed"
