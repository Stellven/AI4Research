#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
sandbox="$(mktemp -d "${TMPDIR:-/tmp}/solar-ui-lite.XXXXXX")"
install_sh="$repo_dir/install.sh"

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

assert_not_contains() {
  local file="$1"
  local needle="$2"
  if grep -Fq "$needle" "$file"; then
    echo "FAIL: unexpected '$needle' in $file" >&2
    cat "$file" >&2
    exit 1
  fi
}

echo "Solar UI-lite smoke: deterministic harness plumbing, not live Claude behavior"
echo "sandbox=$sandbox"

full_home="$sandbox/full-home"
HOME="$full_home" "$install_sh" --yes --components kernel,harness --fake-keys --skip-llm-cli >/dev/null

full_out="$sandbox/full-ui.txt"
HOME="$full_home" "$full_home/.solar/bin/solar" ui --once --no-color > "$full_out"
assert_contains "$full_out" "Solar UI-lite"
assert_contains "$full_out" "[Install health]"
assert_contains "$full_out" "[Harness readiness]"
assert_contains "$full_out" "[Runtime status]"
assert_contains "$full_out" "[Manual boundary]"
assert_contains "$full_out" "live Claude status:"
assert_contains "$full_out" "not verified here: live Claude panes"
assert_not_contains "$full_out" "verified-live"
assert_not_contains "$full_out" "live Claude verified"
echo "solar ui kernel+harness render: ok"

doctor_json="$sandbox/full-doctor.json"
HOME="$full_home" "$full_home/.solar/bin/solar" doctor --json > "$doctor_json"
python3 - "$doctor_json" <<'PY'
import json
import sys

payload = json.load(open(sys.argv[1], encoding="utf-8"))
if payload.get("verdict") != "ok":
    raise SystemExit(f"solar doctor verdict was not ok: {payload}")
if "harness" not in payload.get("components", []):
    raise SystemExit(f"harness component missing from doctor payload: {payload}")
PY
echo "solar doctor after UI render: ok"

HOME="$full_home" "$full_home/.solar/bin/solar" uninstall --yes >/dev/null
if [ -e "$full_home/.solar" ] || [ -e "$full_home/.claude/solar" ]; then
  echo "FAIL: full install cleanup left Solar paths" >&2
  find "$full_home" -maxdepth 3 -print >&2 2>/dev/null || true
  exit 1
fi
echo "solar uninstall after UI render: ok"

kernel_home="$sandbox/kernel-home"
HOME="$kernel_home" "$install_sh" --yes --components kernel --fake-keys --skip-llm-cli >/dev/null

kernel_out="$sandbox/kernel-ui.txt"
HOME="$kernel_home" "$kernel_home/.solar/bin/solar" ui --once --no-color > "$kernel_out"
assert_contains "$kernel_out" "[Install health]"
assert_contains "$kernel_out" "[Harness readiness]"
assert_contains "$kernel_out" "status: harness not installed"
assert_contains "$kernel_out" "remedy: install with --components kernel,harness"
assert_contains "$kernel_out" "[Manual boundary]"
assert_not_contains "$kernel_out" "verified-live"
echo "solar ui kernel-only partial render: ok"

HOME="$kernel_home" "$kernel_home/.solar/bin/solar" uninstall --yes >/dev/null
if [ -e "$kernel_home/.solar" ] || [ -e "$kernel_home/.claude/solar" ]; then
  echo "FAIL: kernel-only cleanup left Solar paths" >&2
  find "$kernel_home" -maxdepth 3 -print >&2 2>/dev/null || true
  exit 1
fi
echo "Solar UI-lite smoke passed"
