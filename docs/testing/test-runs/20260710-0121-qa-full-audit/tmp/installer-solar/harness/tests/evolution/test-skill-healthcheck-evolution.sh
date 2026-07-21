#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."

python3 lib/eval_runner.py run --pack evals/packs/skill-healthcheck-evolution/eval.json --json > /tmp/solar-skill-healthcheck-evolution-eval.json
python3 - <<'PY'
import json
from pathlib import Path

data = json.loads(Path("/tmp/solar-skill-healthcheck-evolution-eval.json").read_text())
assert data["ok"] is True, data
assert data["passed"] == data["checks"], data
print("skill-healthcheck-evolution eval ok")
PY
