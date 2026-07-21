#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

python3 -m py_compile lib/skill_healthcheck.py
bash -n solar-harness.sh

out="$(./solar-harness.sh skills healthcheck --force --no-remote --json)"
python3 - "$out" <<'PY'
import json
import pathlib
import sys

data = json.loads(sys.argv[1])
assert data["ok"] is True
assert data["window_ok"] is True
assert data["power_ok"] is True
assert data["remote"]["checked"] is False
assert data["report_path"]
assert pathlib.Path(data["report_path"]).exists()
assert isinstance(data["skill_candidates"], list)
print("skill-healthcheck ok")
PY

