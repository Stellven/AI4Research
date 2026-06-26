#!/usr/bin/env bash
# Autonomous desktop test runner — no manual clicking. Runs the deterministic gates and
# reports a single PASS/FAIL. Point HARNESS_DIR at the runtime tree to test (defaults to ../harness).
#
#   bash desktop/autotest.sh
#   HARNESS_DIR=/path/to/harness bash desktop/autotest.sh
#
# Gates:
#   runtime-detect.test.js — WSL/runtime detection logic (stub-but-no-distro classification, etc.).
#                  Pure Node, mocks wsl.exe — no display/electron. Runs on Linux/macOS/Windows node.exe.
#   contract.js  — backend HTTP contract (CORS/OPTIONS/HEAD/auth/runtime-info; no token leak). Pure Node;
#                  runs on Linux/macOS/Windows node.exe. Locks in the dashboard-backend fixes.
#   verify.js    — renders the dashboard in headless chromium and asserts the intake + Settings UI.
#                  Needs the bundled playwright chromium (npm i --no-save playwright + a cached browser).
set -u
cd "$(dirname "$0")"
export HARNESS_DIR="${HARNESS_DIR:-$(cd .. && pwd)/harness}"
echo "== Solar desktop autotest =="
echo "HARNESS_DIR=$HARNESS_DIR"
fail=0

echo; echo "-- gate: bootstrap logic --"
node src/runtime-detect.test.js || fail=1

echo; echo "-- gate: backend contract --"
node contract.js || fail=1

echo; echo "-- gate: dashboard render --"
if [ -d node_modules/playwright ]; then
  node verify.js || fail=1
else
  echo "SKIP: playwright not installed (npm install --no-save playwright@1.61.1) — render gate skipped"
fi

echo; echo "-- gate: first-run screens (Electron via SOLAR_SIMULATE) --"
# Prefer xvfb (a headless virtual display) so the test windows NEVER pop onto the user's real
# screen. Only fall back to an existing $DISPLAY if xvfb is unavailable (and say so).
if [ ! -d node_modules/playwright ]; then
  echo "SKIP: playwright not installed — screen gate skipped"
elif command -v xvfb-run >/dev/null 2>&1; then
  xvfb-run -a node screens.test.js || fail=1
elif [ -n "${DISPLAY:-}" ]; then
  echo "(no xvfb; rendering to \$DISPLAY=$DISPLAY — windows may briefly appear)"
  node screens.test.js || fail=1
else
  echo "SKIP: no display/xvfb for the Electron screen gate"
fi

echo
if [ "$fail" -eq 0 ]; then echo "AUTOTEST PASS"; else echo "AUTOTEST FAIL"; fi
exit "$fail"
