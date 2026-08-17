#!/usr/bin/env bash
set -euo pipefail

# These tests reference lib/, bin/ and tools/ relative to the working
# directory, so they need to run from harness/. They used to live at
# harness/tests/, where "$0/.." was harness/; after the move to
# tests/harness/ the same expression lands in tests/ instead. Sibling tests
# in this directory already resolve harness/ this way.
cd "$(dirname "$0")/../../harness"

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

