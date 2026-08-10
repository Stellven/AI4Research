#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-${HOME}/.solar/harness}"
HARNESS="${ROOT}/solar-harness.sh"
PASS=0
FAIL=0

run_test() {
  local name="$1"; shift
  if "$@" >/dev/null 2>&1; then
    echo "PASS: ${name}"
    PASS=$((PASS + 1))
  else
    echo "FAIL: ${name}"
    FAIL=$((FAIL + 1))
  fi
}

echo "=== Tech Hotspot Radar wiki bridge tests ==="

run_test "top_level_help_mentions_bridge" bash -c \
  "bash '${HARNESS}' help 2>&1 | grep -q 'tech-hotspot-radar'"

run_test "wiki_help_mentions_bridge" bash -c \
  "bash '${HARNESS}' wiki help 2>&1 | grep -q 'wiki tech-hotspot-radar'"

run_test "bridge_help_routes_to_python_cli" bash -c \
  "bash '${HARNESS}' wiki tech-hotspot-radar help 2>&1 | grep -q 'Tech Hotspot Radar'"

run_test "bridge_validate_routes_to_runtime" bash -c \
  "bash '${HARNESS}' wiki tech-hotspot-radar validate-ai-influence-planned-reports --date 2026-05-25 --report-id agentic-developer-stack --require-project-archive 2>&1 | grep -q '\"status\": \"ok\"'"

echo "=== Summary: ${PASS} passed, ${FAIL} failed ==="
if [[ "${FAIL}" -ne 0 ]]; then
  exit 1
fi
