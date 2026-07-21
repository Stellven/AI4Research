#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."

python3 -m py_compile lib/skill_evolution_runner.py
bash -n solar-harness.sh

out="$(./solar-harness.sh skills evolve run --candidate solar-prompt-residue-quarantine --no-remote --update-memrl --json || true)"
python3 - "$out" <<'PY'
import json
import os
import pathlib
import sys

text = sys.argv[1]
start = text.find("{")
assert start >= 0, text
data = json.loads(text[start:])
assert data["selected_count"] == 1, data
run = data["runs"][0]
assert run["candidate"] == "solar-prompt-residue-quarantine"
assert run["verdict"] in {"proposed", "blocked"}
assert run["promoted"] is False
assert "candidate_skill_not_implemented" in run["blockers"]
assert run["memrl_status"]["ready"] is True
assert run["eval"]["ok"] is True
assert pathlib.Path(os.path.expanduser("~/.solar/harness/state/skill-evolution/latest.json")).exists()
print("skill-evolution runner run ok")
PY

status="$(./solar-harness.sh skills evolve status --json)"
python3 - "$status" <<'PY'
import json
import sys

text = sys.argv[1]
data = json.loads(text[text.find("{"):])
assert data["ok"] is True
assert data["runs"]
assert data["registry"]
print("skill-evolution runner status ok")
PY
