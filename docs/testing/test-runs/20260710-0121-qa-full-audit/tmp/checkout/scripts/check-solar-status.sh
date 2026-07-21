#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
sandbox="$(mktemp -d "${TMPDIR:-/tmp}/solar-status.XXXXXX")"
home_dir="$sandbox/home"

cleanup() {
  rm -rf "$sandbox"
}
trap cleanup EXIT

assert_contains() {
  local file="$1"
  local needle="$2"
  if ! grep -Fq "$needle" "$file"; then
    echo "FAIL: expected '$needle' in $file" >&2
    cat "$file" >&2
    exit 1
  fi
}

echo "solar status smoke: install health + runtime + daemon truthfulness"
echo "sandbox=$sandbox"

set +e
HOME="$sandbox/not-installed" "$repo_dir/bin/solar" status > "$sandbox/not-installed.txt" 2>&1
rc=$?
set -e
[ "$rc" -eq 1 ] || { echo "FAIL: source solar status without install rc=$rc, expected 1" >&2; cat "$sandbox/not-installed.txt" >&2; exit 1; }
assert_contains "$sandbox/not-installed.txt" "health: fail"
echo "not-installed status exits 1: ok"

set +e
HOME="$sandbox/bad-option" "$repo_dir/bin/solar" status --bad-option > "$sandbox/bad-option.txt" 2>&1
rc=$?
set -e
[ "$rc" -eq 2 ] || { echo "FAIL: bad status option rc=$rc, expected 2" >&2; cat "$sandbox/bad-option.txt" >&2; exit 1; }
echo "status bad option exits 2: ok"

HOME="$home_dir" "$repo_dir/install.sh" --yes --components kernel,harness --fake-keys --skip-llm-cli >/dev/null

text_out="$sandbox/status.txt"
json_out="$sandbox/status.json"
HOME="$home_dir" "$home_dir/.solar/bin/solar" status > "$text_out"
HOME="$home_dir" "$home_dir/.solar/bin/solar" status --json > "$json_out"

assert_contains "$text_out" "OpenSolar status"
assert_contains "$text_out" "Install"
assert_contains "$text_out" "health: ok"
assert_contains "$text_out" "components: kernel,harness"
assert_contains "$text_out" "Runtime"
assert_contains "$text_out" "harness: installed"
assert_contains "$text_out" "Daemon"
assert_contains "$text_out" "component: not-installed"
assert_contains "$text_out" "state: not-installed"

python3 - "$json_out" <<'PY'
import json
import sys

payload = json.load(open(sys.argv[1], encoding="utf-8"))
install = payload.get("install", {})
runtime = payload.get("runtime", {})
daemon = payload.get("daemon", {})
if install.get("verdict") != "ok":
    raise SystemExit(f"install verdict not ok: {payload}")
if install.get("components") != ["kernel", "harness"]:
    raise SystemExit(f"unexpected components: {install.get('components')}")
if not install.get("version") or install.get("version") == "unknown":
    raise SystemExit(f"missing truthful version: {payload}")
if not install.get("channel"):
    raise SystemExit(f"missing channel: {payload}")
if runtime.get("harness") != "installed":
    raise SystemExit(f"harness status not installed: {payload}")
if daemon.get("component") != "not-installed":
    raise SystemExit(f"daemon backend should be not-installed for kernel,harness: {payload}")
if daemon.get("state") != "not-installed":
    raise SystemExit(f"daemon state should be not-installed: {payload}")
PY
echo "fresh install status text/json: ok"

HOME="$home_dir" "$home_dir/.solar/bin/solar" uninstall --yes >/dev/null
if [ -e "$home_dir/.solar" ] || [ -e "$home_dir/.claude/solar" ]; then
  echo "FAIL: uninstall left Solar paths" >&2
  find "$home_dir" -maxdepth 3 -print >&2 2>/dev/null || true
  exit 1
fi
echo "solar status smoke passed"
