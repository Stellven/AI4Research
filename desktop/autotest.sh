#!/usr/bin/env bash
# Autonomous desktop test runner — no manual clicking. Runs the deterministic gates and
# reports PASS, FAIL, or NOT VERIFIED. Point HARNESS_DIR at the runtime tree to test
# (defaults to ../harness).
#
#   bash desktop/autotest.sh
#   HARNESS_DIR=/path/to/harness bash desktop/autotest.sh
#
# Gates:
#   runtime-detect.test.cjs — WSL/runtime detection logic (stub-but-no-distro classification, etc.).
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
incomplete=0

not_verified() {
  echo "NOT VERIFIED: $1"
  incomplete=1
}

run_gate() {
  "$@"
  local rc=$?
  if [ "$rc" -eq 2 ]; then
    incomplete=1
  elif [ "$rc" -ne 0 ]; then
    fail=1
  fi
}

echo; echo "-- gate: bootstrap logic --"
run_gate node ../tests/desktop/src/runtime-detect.test.cjs

echo; echo "-- gate: bootstrap/package contract --"
run_gate node ../tests/desktop/bootstrap-contract.test.cjs

echo; echo "-- gate: desktop selftest truth --"
run_gate node ../tests/desktop/src/selftest-verdict.test.cjs

echo; echo "-- gate: backend contract --"
run_gate node contract.js

echo; echo "-- gate: dashboard render --"
if [ -d node_modules/playwright ]; then
  run_gate node verify.js
else
  not_verified "playwright not installed; render gate did not run (run: npm ci && npx playwright install chromium)"
fi

echo; echo "-- gate: functional e2e (real backend: intake form, Settings persistence, SSE) --"
if [ -d node_modules/playwright ]; then
  run_gate node ../tests/desktop/functional.test.cjs     # isolated temp HARNESS_DIR+SOLAR_DB; headless chromium
else
  not_verified "playwright not installed; functional gate did not run"
fi

echo; echo "-- gate: source Electron selftest e2e --"
if [ ! -d node_modules/playwright ]; then
  not_verified "playwright not installed; source Electron selftest did not run"
elif command -v xvfb-run >/dev/null 2>&1; then
  run_gate xvfb-run -a node ../tests/desktop/selftest-electron.test.cjs
elif [ -n "${DISPLAY:-}" ]; then
  echo "(no xvfb; rendering to \$DISPLAY=$DISPLAY — windows may briefly appear)"
  run_gate node ../tests/desktop/selftest-electron.test.cjs
else
  not_verified "no display/xvfb; source Electron selftest did not run"
fi

echo; echo "-- gate: first-run screens (Electron via SOLAR_SIMULATE) --"
# Prefer xvfb (a headless virtual display) so the test windows NEVER pop onto the user's real
# screen. Only fall back to an existing $DISPLAY if xvfb is unavailable (and say so).
if [ ! -d node_modules/playwright ]; then
  not_verified "playwright not installed; Electron screen gate did not run"
elif command -v xvfb-run >/dev/null 2>&1; then
  run_gate xvfb-run -a node ../tests/desktop/screens.test.cjs
elif [ -n "${DISPLAY:-}" ]; then
  echo "(no xvfb; rendering to \$DISPLAY=$DISPLAY — windows may briefly appear)"
  run_gate node ../tests/desktop/screens.test.cjs
else
  not_verified "no display/xvfb; Electron screen gate did not run"
fi

echo
if [ "$fail" -ne 0 ]; then
  echo "AUTOTEST FAIL"
  exit 1
fi
if [ "$incomplete" -ne 0 ]; then
  echo "AUTOTEST NOT VERIFIED"
  exit 2
fi
echo "AUTOTEST PASS"
exit 0
