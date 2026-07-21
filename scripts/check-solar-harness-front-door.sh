#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
sandbox="$(mktemp -d "${TMPDIR:-/tmp}/solar-harness-front-door.XXXXXX")"
home_dir="$sandbox/home"
kernel_home="$sandbox/kernel-home"

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

echo "solar harness front-door smoke"
echo "sandbox=$sandbox"

HOME="$home_dir" "$repo_dir/install.sh" --yes --components kernel,harness --fake-keys --skip-llm-cli >/dev/null

help_out="$sandbox/harness-help.txt"
HOME="$home_dir" "$home_dir/.solar/bin/solar" harness > "$help_out"
assert_contains "$help_out" "Solar Harness"
assert_contains "$help_out" "solar-harness"
assert_contains "$help_out" "Cockpit & status"
assert_contains "$help_out" "solar-harness start"
echo "bare solar harness help: ok"

models_out="$sandbox/models-show.txt"
HOME="$home_dir" "$home_dir/.solar/bin/solar" harness models show > "$models_out"
assert_contains "$models_out" "main pm"
assert_contains "$models_out" "lab matrix"
echo "solar harness models show: ok"

status_out="$sandbox/harness-status.txt"
HOME="$home_dir" "$home_dir/.solar/bin/solar" harness status > "$status_out" 2>&1 || true
assert_contains "$status_out" "deterministic status only; real Claude response/delegation remains owner-manual"
echo "solar harness status passthrough: ok"

set +e
HOME="$home_dir" "$home_dir/.solar/bin/solar" harness does-not-exist > "$sandbox/unknown.txt" 2>&1
rc=$?
set -e
[ "$rc" -eq 2 ] || { echo "FAIL: unknown harness verb rc=$rc, expected 2" >&2; cat "$sandbox/unknown.txt" >&2; exit 1; }
echo "solar harness unknown verb exits 2: ok"

HOME="$home_dir" "$home_dir/.solar/bin/solar" uninstall --yes >/dev/null

HOME="$kernel_home" "$repo_dir/install.sh" --yes --components kernel --fake-keys --skip-llm-cli >/dev/null
set +e
HOME="$kernel_home" "$kernel_home/.solar/bin/solar" harness > "$sandbox/kernel-only.txt" 2>&1
rc=$?
set -e
[ "$rc" -eq 1 ] || { echo "FAIL: kernel-only solar harness rc=$rc, expected 1" >&2; cat "$sandbox/kernel-only.txt" >&2; exit 1; }
assert_contains "$sandbox/kernel-only.txt" "solar harness backend not found"
HOME="$kernel_home" "$kernel_home/.solar/bin/solar" uninstall --yes >/dev/null
echo "solar harness missing backend: ok"

echo "solar harness front-door smoke passed"
