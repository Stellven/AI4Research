#!/usr/bin/env bash
# test-runtime-interface-chaos.sh — R5 runtime interface chaos suite
set -euo pipefail

HARNESS_DIR="${HOME}/.solar/harness"
LIB_DIR="${HARNESS_DIR}/lib"
REPORT_DIR="${HARNESS_DIR}/reports/managed-agent-runtime-interfaces"

export PYTHONPATH="${LIB_DIR}:${PYTHONPATH:-}"

echo "=== test-runtime-interface-chaos ==="

OUT=$(python3 "${LIB_DIR}/runtime_chaos_suite.py" --json)
echo "$OUT" > /tmp/solar-runtime-chaos-test.json

python3 - <<'PY'
import json
from pathlib import Path

data = json.loads(Path("/tmp/solar-runtime-chaos-test.json").read_text())
assert data["ok"] is True, data
assert data["passed"] == data["total"], data
names = {case["name"] for case in data["cases"] if case["ok"]}
required = {
    "duplicate_command",
    "shell_destructive_denied",
    "shell_secret_redacted",
    "cancelled_activity_event",
    "worker_lease_expiry",
    "context_projection_no_rewrite_and_redact",
}
missing = required - names
assert not missing, missing
PY

test -s "${REPORT_DIR}/chaos-report.json"
test -s "${REPORT_DIR}/chaos-report.md"

echo "PASS: runtime interface chaos suite"
