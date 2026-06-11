#!/usr/bin/env bash

write_receipt() {
    dry_run_note "write receipt $RECEIPT_PATH" && return 0
    tmp="$RECEIPT_PATH.tmp.$$"
    mkdir -p "$(dirname "$RECEIPT_PATH")"
    SELECTED_COMPONENTS="$SELECTED_COMPONENTS" \
    SOURCE_DIR="$SOURCE_DIR" \
    SOLAR_HOME="$SOLAR_HOME" \
    CLAUDE_DIR="$CLAUDE_DIR" \
    SOLAR_DB="$SOLAR_DB" \
    OS_KIND="$OS_KIND" \
    python3 - "$tmp" <<'PY'
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

tmp = sys.argv[1]
source = os.environ["SOURCE_DIR"]
try:
    sha = subprocess.check_output(
        ["git", "-C", source, "rev-parse", "--short", "HEAD"],
        text=True,
        stderr=subprocess.DEVNULL,
    ).strip()
except Exception:
    sha = "unknown"

components = [c for c in os.environ.get("SELECTED_COMPONENTS", "").split() if c]
all_roots = {
    "kernel": [os.path.join(os.environ["CLAUDE_DIR"], "solar")],
    "core-runtime": [os.path.join(os.environ["SOLAR_HOME"], "core")],
    "harness": [os.path.join(os.environ["SOLAR_HOME"], "harness")],
    "skills-md": [os.path.join(os.environ["CLAUDE_DIR"], "skills")],
    "codex-bridge": [os.path.join(os.environ["SOLAR_HOME"], "codex-bridge")],
    "mempalace": [
        os.path.join(os.environ["SOLAR_HOME"], "mempalace"),
        os.path.join(os.environ["SOLAR_HOME"], "venv"),
    ],
}
receipt = {
    "schema": 1,
    "version": "p1-alpha",
    "git_sha": sha,
    "source_dir": source,
    "os": os.environ.get("OS_KIND", "unknown"),
    "installed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "solar_home": os.environ["SOLAR_HOME"],
    "claude_dir": os.environ["CLAUDE_DIR"],
    "db": os.environ["SOLAR_DB"],
    "components": components,
    "component_roots": {name: all_roots[name] for name in components if name in all_roots},
    "sentinels": {
        "claude_md": os.path.join(os.environ["CLAUDE_DIR"], "CLAUDE.md"),
        "begin": "<!-- BEGIN OPENSOLAR -->",
        "end": "<!-- END OPENSOLAR -->",
    },
}
with open(tmp, "w", encoding="utf-8") as f:
    json.dump(receipt, f, indent=2, sort_keys=True)
    f.write("\n")
PY
    mv "$tmp" "$RECEIPT_PATH"
}
