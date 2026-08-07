#!/usr/bin/env bash
# S03 N6 — shell smoke test for the benchmark runner CLI.
#
# Verifies the --json paths of doctor/list/plan exit cleanly without
# invoking any real harbor/docker/uvx subprocess. All subprocess + network
# probes are mocked at the Python level via monkeypatched stand-ins so this
# script is safe to run anywhere.
#
# Exit codes: 0 = all checks pass; any non-zero = first failing check.

set -euo pipefail

HARNESS_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$HARNESS_ROOT"

PY="${PYTHON:-python3}"
TMP_REPORTS="$(mktemp -d -t solar-bench-smoke.XXXXXX)"
TMP_HARNESS="$(mktemp -d -t solar-bench-smoke-harness.XXXXXX)"

cleanup() {
    rm -rf "$TMP_REPORTS" "$TMP_HARNESS"
}
trap cleanup EXIT

export SOLAR_BENCH_REPORTS_DIR="$TMP_REPORTS"
export HARNESS_DIR="$TMP_HARNESS"
export HOME_FOR_TEST="$TMP_HARNESS"
export PYTHONPATH="$HARNESS_ROOT${PYTHONPATH:+:$PYTHONPATH}"

# Build a tiny driver that monkeypatches harbor + docker probes off, then
# dispatches runner.main(...) with each subcommand. This keeps the smoke
# self-contained — no real binaries touched.
DRIVER="$(mktemp -t solar-bench-driver.XXXXXX).py"
cat > "$DRIVER" <<'PY'
"""Driver for shell smoke — patches subprocess + network probes off."""
from __future__ import annotations
import json
import sys
from io import StringIO
from unittest.mock import patch
from pathlib import Path

# PYTHONPATH set by the parent shell script points to the harness root.
# Keep this CWD-independent: do NOT rely on Path.resolve() against "harness".
from harness.lib.benchmark import runner


def _run(argv):
    buf = StringIO()
    err = StringIO()
    with patch("harness.lib.benchmark.harbor_adapter.detect",
               return_value=(False, "missing")), \
         patch("harness.lib.benchmark.harbor_adapter.docker_available",
               return_value=False), \
         patch("harness.lib.benchmark.harbor_adapter.probe_dataset",
               return_value=False), \
         patch("harness.lib.benchmark.harbor_adapter.probe_api_key",
               return_value=False), \
         patch("sys.stdout", buf), \
         patch("sys.stderr", err):
        try:
            code = runner.main(argv)
        except SystemExit as exc:
            code = int(exc.code) if exc.code is not None else 0
    return code, buf.getvalue(), err.getvalue()


checks = []

# Check 1: doctor --json prints JSON and exits 0 (doctor itself never fails;
# missing prereqs are surfaced in payload, not via exit code).
code, out, _ = _run(["doctor", "--json"])
assert code == 0, f"doctor --json exit code = {code}"
payload = json.loads(out)
assert payload["adapter_id"] == "terminal-bench@2.0"
assert "missing_prereqs" in payload
assert payload["harbor_available"] is False  # forced missing
checks.append("doctor --json -> exit 0, well-formed JSON")

# Check 2: list --json prints a JSON array of tasks
code, out, _ = _run(["list", "--json"])
assert code == 0, f"list --json exit code = {code}"
tasks = json.loads(out)
assert isinstance(tasks, list)
assert any(t["id"] == "hello-world-cli" for t in tasks)
checks.append("list --json -> exit 0, hello-world-cli present")

# Check 3: plan --json prints a JSON object with command argv
code, out, _ = _run([
    "plan", "--agent", "claude-code", "--model", "claude-opus-4-7",
    "--env", "docker", "--tasks", "hello-world-cli", "--json",
])
assert code == 0, f"plan --json exit code = {code}"
plan_out = json.loads(out)
assert "command" in plan_out
assert plan_out["command"][-1] == "hello-world-cli"
checks.append("plan --json -> exit 0, command argv present")

# Check 4: run --json --dry-run with missing prereqs -> exit 2 (pending)
code, out, _ = _run([
    "run", "--agent", "claude-code", "--model", "claude-opus-4-7",
    "--env", "", "--tasks", "hello-world-cli", "--json", "--dry-run",
])
# When prereqs missing, verdict=pending → exit_code=2
assert code == 2, f"run dry-run pending exit code = {code} (expected 2)"
result = json.loads(out)
assert result["verdict"] == "pending"
checks.append("run --json --dry-run (missing prereqs) -> exit 2 pending")

# Check 5: run with bad agent → exit 1 (error)
code, _, _ = _run([
    "run", "--agent", "rogue-cli", "--model", "x", "--env", "docker",
    "--tasks", "hello-world-cli", "--json",
])
assert code == 1, f"bad-agent exit code = {code} (expected 1)"
checks.append("run --agent rogue-cli -> exit 1 error")

# Check 6: run --full without --confirm-budget → exit 1 (error)
code, _, _ = _run([
    "run", "--agent", "claude-code", "--model", "x", "--env", "docker",
    "--full", "--tasks", "hello-world-cli", "--json",
])
assert code == 1, f"full-without-budget exit code = {code} (expected 1)"
checks.append("run --full without --confirm-budget -> exit 1 error")

print("OK: shell smoke passed")
for c in checks:
    print(f"  - {c}")
PY

if "$PY" "$DRIVER"; then
    rm -f "$DRIVER"
    echo "test-terminal-bench-adapter.sh: PASS"
    exit 0
fi

rm -f "$DRIVER"
echo "test-terminal-bench-adapter.sh: FAIL" >&2
exit 1
