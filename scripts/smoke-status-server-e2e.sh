#!/usr/bin/env bash
# E2E: fresh sandbox-HOME install -> start the INSTALLED harness status-server -> assert the
# HTTP contract the dashboard + desktop shell depend on -> uninstall residue-free. Proves
# "install -> working dashboard backend" with zero manual steps and no container (the installer
# writes only to $HOME, so a mktemp HOME is a clean target). Complements smoke-install-matrix.sh,
# which covers the bun core-runtime dashboard (:3721) but NOT the harness status-server (:8765).
set -u
repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
[ -f "$repo_dir/install.sh" ] || { echo "cannot locate install.sh from $repo_dir" >&2; exit 2; }
sandbox="$(mktemp -d "${TMPDIR:-/tmp}/solar-ss-e2e.XXXXXX")"
home_dir="$sandbox/home"; mkdir -p "$home_dir"
export RUSTUP_HOME="$sandbox/rustup" CARGO_HOME="$sandbox/cargo"
PY="${SOLAR_PYTHON:-python3}"; srv_pid=""
cleanup(){ [ -n "$srv_pid" ] && { kill "$srv_pid" 2>/dev/null; wait "$srv_pid" 2>/dev/null; }; }
trap cleanup EXIT INT TERM
fail(){ echo "E2E FAIL: $*" >&2; exit 1; }

echo "== sandbox=$sandbox =="
echo "-- 1. fresh install (kernel,harness) --"
HOME="$home_dir" "$repo_dir/install.sh" --yes --components kernel,harness --fake-keys --skip-llm-cli \
  >"$sandbox/install.log" 2>&1 || { tail -20 "$sandbox/install.log" >&2; fail "install.sh nonzero"; }
echo "   install ok"

echo "-- 2. doctor verdict --"
HOME="$home_dir" "$home_dir/.solar/bin/solar" doctor --json >"$sandbox/doctor.json" 2>/dev/null
"$PY" -c "import json,sys;d=json.load(open('$sandbox/doctor.json'));sys.exit(0 if d.get('verdict')=='ok' else 1)" \
  || fail "doctor verdict != ok"
echo "   doctor ok"

SS="$home_dir/.solar/harness/lib/symphony/status-server.py"
[ -f "$SS" ] || fail "installed harness has no status-server.py at $SS"
echo "-- 3. start INSTALLED harness status-server --"
HOME="$home_dir" HARNESS_DIR="$home_dir/.solar/harness" "$PY" "$SS" >"$sandbox/ss.log" 2>&1 &
srv_pid="$!"
PORT=""
for _ in $(seq 1 40); do
  PORT=$(cat "$home_dir/.solar/harness/run/status-server.port" 2>/dev/null || true)
  [ -n "$PORT" ] && curl -fsS "http://127.0.0.1:$PORT/healthz" >/dev/null 2>&1 && break
  PORT=""; sleep 0.5
done
[ -n "$PORT" ] || { tail -20 "$sandbox/ss.log" >&2; fail "status-server did not come up"; }
echo "   status-server up on :$PORT"

echo "-- 4. assert dashboard backend contract --"
B="http://127.0.0.1:$PORT"
code(){ curl -s -o /dev/null -w '%{http_code}' "$@" 2>/dev/null; }
[ "$(code "$B/healthz")" = 200 ]            || fail "/healthz != 200"
[ "$(code -X OPTIONS "$B/status")" = 204 ]  || fail "OPTIONS != 204 (CORS preflight regressed)"
[ "$(code -I "$B/status")" = 200 ]          || fail "HEAD != 200"
[ "$(code "$B/runtime-info")" = 200 ]       || fail "/runtime-info != 200"
[ "$(code "$B/auth/status")" = 200 ]        || fail "/auth/status != 200"
curl -s -D - -o /dev/null -X OPTIONS "$B/status" | grep -qi 'access-control-allow-origin' \
  || fail "missing CORS header on preflight"
echo "   contract ok (healthz 200, OPTIONS 204+CORS, HEAD 200, runtime-info 200, auth/status 200)"

cleanup; srv_pid=""
echo "-- 5. uninstall + residue --"
HOME="$home_dir" "$home_dir/.solar/bin/solar" uninstall --yes >"$sandbox/uninstall.log" 2>&1 || fail "uninstall nonzero"
residue=$(find "$home_dir" -mindepth 1 2>/dev/null | head)
[ -z "$residue" ] || { echo "$residue" >&2; fail "uninstall left residue"; }
echo "   uninstall clean"
echo "E2E PASS — fresh install -> working dashboard backend -> clean uninstall"
