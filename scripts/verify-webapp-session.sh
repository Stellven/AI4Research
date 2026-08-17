#!/usr/bin/env bash
# verify-webapp-session.sh — one repeatable gate for the webapp session-correctness + P0 fixes,
# run against the CURRENT tree. Each step prints PASS / FAIL / SKIP; the script exits non-zero if
# ANY step FAILED.
#
# SKIP semantics (honest): SKIP is reserved for OS-IMPOSSIBLE checks only. A MISSING LOCAL DEP is
# NOT a skip — it is reported as "NOT VERIFIED" and counts as FAIL, with the exact, reproducible
# setup command printed, so a green run means every gate actually executed. (This gate has no
# OS-impossible steps: the functional e2e uses headless chromium, which runs on Linux/macOS/WSL.)
#
#   bash scripts/verify-webapp-session.sh
#
# One-time reproducible setup (from lockfiles; chromium browser binary for Playwright):
#   ( cd harness/status-server/react-app && npm ci )
#   ( cd desktop && npm ci && npx playwright install chromium )
set -u
repo="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo"
RA="harness/status-server/react-app"
pass=0; fail=0; skip=0

if [ -n "${PYTHON:-}" ]; then
  PYTHON_BIN="$PYTHON"
elif [ -x "$repo/.venv/bin/python" ]; then
  PYTHON_BIN="$repo/.venv/bin/python"
elif command -v cygpath >/dev/null 2>&1 && [ -x "$repo/.venv/Scripts/python.exe" ]; then
  PYTHON_BIN="$(cygpath -w "$repo/.venv/Scripts/python.exe")"
else
  PYTHON_BIN="$(command -v python3 || true)"
fi
if command -v cygpath >/dev/null 2>&1; then
  PYTEST_TEMP_ROOT="${SOLAR_TEST_TEMP_ROOT:-${TEMP:-/tmp}}"
  PYTEST_BASE="$(cygpath -w "$PYTEST_TEMP_ROOT")\\solar-webapp-pytest-$$-$RANDOM"
  PYTEST_CACHE="$(cygpath -w "$PYTEST_TEMP_ROOT")\\solar-webapp-cache-$$-$RANDOM"
else
  PYTEST_TEMP_ROOT="${SOLAR_TEST_TEMP_ROOT:-${TMPDIR:-/tmp}}"
  PYTEST_BASE="$PYTEST_TEMP_ROOT/solar-webapp-pytest-$$-$RANDOM"
  PYTEST_CACHE="$PYTEST_TEMP_ROOT/solar-webapp-cache-$$-$RANDOM"
fi

node_with_desktop_deps() {
  local modules="$repo/desktop/node_modules"
  if command -v cygpath >/dev/null 2>&1; then
    modules="$(cygpath -w "$modules")"
  fi
  NODE_PATH="$modules${NODE_PATH:+:$NODE_PATH}" node "$@"
}

run() {  # run <name> <cmd...>   (exit 0=PASS, any non-zero=FAIL/not-verified)
  local name="$1"; shift
  printf '\n--- %s ---\n' "$name"
  "$@"; local rc=$?
  if [ "$rc" -eq 0 ]; then
    echo "PASS: $name"; pass=$((pass + 1))
  else
    echo "FAIL: $name (rc=$rc)"; fail=$((fail + 1))
  fi
}

need() {  # need <thing> <reproducible-fix-cmd> ; emits NOT VERIFIED + returns 1 (counts as FAIL)
  echo "NOT VERIFIED: $1"
  echo "    reproducible fix: $2"
  return 1
}

backend_pytest() {
  [ -n "$PYTHON_BIN" ] || { need "Python not on PATH and repository .venv missing" "install Python 3.10+ or create .venv"; return 1; }
  "$PYTHON_BIN" -m pytest -q \
    tests/harness/test_status_server_session_scoping.py \
    tests/harness/test_s04_orchestration_routes.py \
    --basetemp "$PYTEST_BASE" -o "cache_dir=$PYTEST_CACHE" 2>&1 | tail -3
  return "${PIPESTATUS[0]}"
}

settings_concurrency() {
  [ -n "$PYTHON_BIN" ] || { need "Python not on PATH and repository .venv missing" "install Python 3.10+ or create .venv"; return 1; }
  "$PYTHON_BIN" tests/harness/status_server/test_settings_concurrency.py 2>&1 | tail -3
  return "${PIPESTATUS[0]}"
}

frontend_typecheck() {
  [ -d "$RA/node_modules" ] || { need "$RA/node_modules missing" "( cd $RA && npm ci )"; return 1; }
  npm --prefix "$RA" run typecheck
}

frontend_build() {
  [ -d "$RA/node_modules" ] || { need "$RA/node_modules missing" "( cd $RA && npm ci )"; return 1; }
  npm --prefix "$RA" run build >/dev/null 2>&1
}

# Scenario 7 (Codex): the served bundle's index.html must reference only assets that actually
# exist on disk — catches a stale build where index.html points at deleted hashed files.
bundle_consistency() {
  local html="harness/status-server/static/p0-app/index.html"
  [ -f "$html" ] || { need "built bundle $html absent" "( cd $RA && npm ci && npm run build )"; return 1; }
  local missing=0
  for ref in $(grep -oE '/static/p0-app/assets/[A-Za-z0-9._-]+' "$html" | sort -u); do
    local rel="harness/status-server/static/p0-app/${ref#/static/p0-app/}"
    if [ ! -f "$rel" ]; then echo "  MISSING asset referenced by index.html: $ref"; missing=$((missing + 1)); fi
  done
  if [ "$missing" -gt 0 ]; then echo "  $missing stale/missing asset reference(s)"; return 1; fi
  echo "  index.html references resolve to on-disk assets"
}

desktop_functional() {
  command -v node >/dev/null || { need "node not on PATH" "install Node.js 18+"; return 1; }
  [ -f tests/desktop/functional.test.cjs ] || { need "tests/desktop/functional.test.cjs absent" "checkout the desktop tests"; return 1; }
  if [ ! -d desktop/node_modules ] || [ ! -d desktop/node_modules/playwright ]; then
    need "desktop Playwright deps missing" "( cd desktop && npm ci && npx playwright install chromium )"; return 1
  fi
  node_with_desktop_deps tests/desktop/functional.test.cjs 2>&1 | tail -5
  return "${PIPESTATUS[0]}"
}

desktop_rapid_switch() {
  command -v node >/dev/null || { need "node not on PATH" "install Node.js 18+"; return 1; }
  [ -f tests/desktop/rapid-switch.test.cjs ] || { need "tests/desktop/rapid-switch.test.cjs absent" "checkout the desktop tests"; return 1; }
  if [ ! -d desktop/node_modules/playwright ]; then
    need "desktop Playwright deps missing" "( cd desktop && npm ci && npx playwright install chromium )"; return 1
  fi
  node_with_desktop_deps tests/desktop/rapid-switch.test.cjs 2>&1 | tail -4
  return "${PIPESTATUS[0]}"
}

# Dashboard overhaul (WS1-WS6): seed a realistic mid-run sprint and render the REAL session
# view at DESKTOP + MOBILE — assert every overhaul surface renders, the result CTA names the
# canonical output, no raw coordinator jargon leaks, the gate shows chips + the honest
# no-worker note, and there is no mobile horizontal overflow.
desktop_overhaul_visual() {
  command -v node >/dev/null || { need "node not on PATH" "install Node.js 18+"; return 1; }
  [ -f tests/desktop/overhaul-visual.test.cjs ] || { need "tests/desktop/overhaul-visual.test.cjs absent" "checkout the desktop tests"; return 1; }
  if [ ! -d desktop/node_modules/playwright ]; then
    need "desktop Playwright deps missing" "( cd desktop && npm ci && npx playwright install chromium )"; return 1
  fi
  node_with_desktop_deps tests/desktop/overhaul-visual.test.cjs 2>&1 | tail -6
  return "${PIPESTATUS[0]}"
}

echo "== webapp session-verification gate =="
echo "repo: $repo   tree: $(git rev-parse --short HEAD 2>/dev/null || echo '?')"

run "git diff --check (whitespace)"        git diff --check
run "backend pytest (session-scoping + orchestration)" backend_pytest
run "settings concurrency + CORS token (real server)"  settings_concurrency
run "frontend typecheck (tsc --noEmit)"    frontend_typecheck
run "frontend build (vite -> static/p0-app)" frontend_build
run "static bundle consistency"            bundle_consistency
run "desktop functional e2e (real backend + headless chromium)" desktop_functional
run "desktop session-isolation regression (rapid switch)" desktop_rapid_switch
run "dashboard overhaul visual (desktop+mobile, real backend + chromium)" desktop_overhaul_visual

echo
echo "================================"
echo "PASS=$pass  FAIL=$fail  SKIP=$skip"
if [ "$fail" -eq 0 ]; then
  echo "WEBAPP GATE: GREEN"; [ "$skip" -gt 0 ] && echo "(note: $skip OS-impossible skip(s))"; exit 0
else
  echo "WEBAPP GATE: RED ($fail not-verified/failed) — see the reproducible fix command(s) above"; exit 1
fi
