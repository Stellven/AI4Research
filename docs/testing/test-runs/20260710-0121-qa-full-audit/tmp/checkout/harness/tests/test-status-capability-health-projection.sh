#!/usr/bin/env bash
set -euo pipefail

HARNESS_DIR="${HARNESS_DIR:-$HOME/.solar/harness}"

python3 - <<'PY'
import importlib.util
import json
import os
from pathlib import Path

harness = Path(os.environ.get("HARNESS_DIR", str(Path.home() / ".solar" / "harness")))
path = harness / "lib" / "symphony" / "status-server.py"
spec = importlib.util.spec_from_file_location("solar_status_capability_projection_test", path)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)  # type: ignore[union-attr]

payload = mod._status_payload(limit=5)  # type: ignore[attr-defined]
health = payload.get("capability_health") or {}
checks = health.get("checks") or {}
required = ["model", "knowledge", "mirage_qmd", "intent", "skills", "sandbox"]
missing = [name for name in required if name not in checks]
if missing:
    raise SystemExit(f"missing global capability checks: {missing}")
bad = [name for name in required if checks.get(name, {}).get("status") not in {"ok", "warn"}]
if bad:
    raise SystemExit(f"bad global capability check status: {bad}")

for screen_name in ("main_screen", "lab_screen"):
    panes = (payload.get(screen_name) or {}).get("panes") or []
    if not panes:
        raise SystemExit(f"{screen_name} has no panes")
    for pane in panes:
        pane_checks = ((pane.get("capability_health") or {}).get("checks") or {})
        pane_missing = [name for name in required if name not in pane_checks]
        if pane_missing:
            raise SystemExit(f"{screen_name}:{pane.get('target')} missing {pane_missing}")

print(json.dumps({
    "ok": True,
    "global_status": health.get("status"),
    "checks": required,
    "main_panes": len((payload.get("main_screen") or {}).get("panes") or []),
    "lab_panes": len((payload.get("lab_screen") or {}).get("panes") or []),
}, ensure_ascii=False))
PY

echo "PASS: status capability health projects to global status and every pane"
