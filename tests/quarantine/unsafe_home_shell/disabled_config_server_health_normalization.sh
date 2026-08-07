#!/usr/bin/env bash
# Regression: config server health normalizes current Mirage/QMD/Drive doctor schema.
set -euo pipefail

HARNESS_DIR="${HARNESS_DIR:-$HOME/.solar/harness}"

python3 - "$HARNESS_DIR/integrations/solar-config-server.py" <<'PY'
import importlib.util
import json
import sys

path = sys.argv[1]
spec = importlib.util.spec_from_file_location("solar_config_server", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

sample = {
    "enabled": True,
    "mounts": [
        {"path": "/knowledge", "status": "ok", "type": "logical", "physical_root": "/Users/x/Knowledge", "reason": ""},
        {"path": "/drive", "status": "ok", "type": "logical", "physical_root": "/Users/x/Library/CloudStorage/GoogleDrive-a", "reason": "local Google Drive File Provider mount found"},
    ],
    "drive": {
        "status": "ok",
        "reason": "local Google Drive File Provider mount found",
        "local_root": "/Users/x/Library/CloudStorage/GoogleDrive-a",
        "provider": "macos-google-drive-file-provider",
    },
    "qmd": {
        "status": "ok",
        "binary": "/usr/local/bin/qmd",
        "detail": {
            "total": "2584 files indexed",
            "vectors": "34687 embedded",
            "pending": "1 need embedding (run 'qmd embed')",
            "collection": "solar-wiki",
        },
    },
}
result = mod._mirage_detail({"ok": True, "stdout": json.dumps(sample)})
assert result["ok"] is True
assert result["mounts"][0]["ready"] is True
assert result["mounts"][0]["mode"] == "logical"
assert result["mounts"][1]["physical_root"].endswith("GoogleDrive-a")
assert result["drive_status"] == "ok"
assert result["credential_configured"] is True
assert result["qmd_status"] == "ok"
assert result["qmd_indexed"] == 2584
assert result["qmd_vectors"] == 34687
assert result["qmd_pending"] == 1
print("PASS: config server normalizes Mirage/QMD/Drive health")
PY
