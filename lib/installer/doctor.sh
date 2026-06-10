#!/usr/bin/env bash

doctor_json() {
    python3 - <<'PY'
import json
import os
from datetime import datetime, timezone

solar_home = os.environ.get("SOLAR_HOME", os.path.expanduser("~/.solar"))
claude_dir = os.environ.get("CLAUDE_DIR", os.path.expanduser("~/.claude"))
receipt_path = os.path.join(solar_home, "install-receipt.json")
result = {
    "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "verdict": "ok",
    "paths": {},
    "components": [],
    "warnings": [],
}
if not os.path.isfile(receipt_path):
    result["verdict"] = "fail"
    result["warnings"].append("install receipt missing")
else:
    with open(receipt_path, encoding="utf-8") as f:
        receipt = json.load(f)
    result["components"] = receipt.get("components", [])

checks = {
    "solar_home": solar_home,
    "receipt": receipt_path,
    "claude_dir": claude_dir,
    "kernel": os.path.join(claude_dir, "solar", "SOLAR.md"),
    "db": os.path.join(solar_home, "db", "solar.db"),
    "solar_bin": os.path.join(solar_home, "bin", "solar"),
}
for key, path in checks.items():
    ok = os.path.isdir(path) if key.endswith("_dir") or key == "solar_home" else os.path.exists(path)
    result["paths"][key] = "ok" if ok else "missing"
    if not ok and key in ("solar_home", "receipt", "kernel", "solar_bin"):
        result["verdict"] = "fail"
        result["warnings"].append(f"path missing: {key}")

print(json.dumps(result, indent=2, sort_keys=True))
PY
}
