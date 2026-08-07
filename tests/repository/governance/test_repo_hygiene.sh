#!/usr/bin/env bash
set -euo pipefail

source_repo="$(cd "$(dirname "$0")/../../.." && pwd)"
fixture="$(mktemp -d)"
trap 'rm -rf "$fixture"' EXIT

mkdir -p "$fixture/scripts" "$fixture/docs/testing/test-runs" "$fixture/harness/logs"
cp "$source_repo/scripts/check-repo-hygiene.sh" "$fixture/scripts/"
printf '# fixture\n' >"$fixture/README.md"
printf '# policy\n' >"$fixture/docs/testing/test-runs/README.md"
: >"$fixture/harness/logs/.gitkeep"
printf 'SAFE=value\n' >"$fixture/.env.template"

git -C "$fixture" init -q
git -C "$fixture" config user.name "Hygiene Test"
git -C "$fixture" config user.email "hygiene@example.invalid"
git -C "$fixture" add README.md scripts/check-repo-hygiene.sh \
  docs/testing/test-runs/README.md harness/logs/.gitkeep .env.template

bash "$fixture/scripts/check-repo-hygiene.sh" >/dev/null

expect_rejected() {
  category="$1"
  relative="$2"
  target="$fixture/$relative"
  mkdir -p "$(dirname "$target")"
  printf 'generated\n' >"$target"
  git -C "$fixture" add -f -- "$relative"

  if output="$(bash "$fixture/scripts/check-repo-hygiene.sh" 2>&1)"; then
    echo "expected hygiene rejection for $relative" >&2
    exit 1
  fi
  printf '%s\n' "$output" | grep -F "$category" >/dev/null
  printf '%s\n' "$output" | grep -F "$relative" >/dev/null
  git -C "$fixture" rm -q -f -- "$relative"
}

expect_rejected OS_METADATA "._finder"
expect_rejected OS_METADATA "nested/.DS_Store"
expect_rejected PACKAGE_CACHE "pkg/node_modules/dependency.js"
expect_rejected LOCAL_ENV "service/.venv/bin/python"
expect_rejected LANGUAGE_CACHE "service/__pycache__/module.pyc"
expect_rejected LOCAL_ENV_CONFIG ".env.local"
expect_rejected GENERATED_OUTPUT "tmp/session/state.json"
expect_rejected GENERATED_OUTPUT "test-results/result.json"
expect_rejected RAW_TEST_EVIDENCE "docs/testing/test-runs/run-1/log.txt"
expect_rejected HARNESS_RUNTIME "harness/logs/pane-exit.jsonl"
expect_rejected MACHINE_SOURCE_ARCHIVE "Feature list stuff/Solar_Harness_All_Sources_2099/files/state.txt"

# R8 Governance negative controls
expect_rejected EXCEL_LOCK_FILE '~$AI4RnD Feature List.xlsx'
expect_rejected TRANSIENT_TEST_OUTPUT "outputs/real-data-tests/run-1/data.json"
expect_rejected TRANSIENT_TEST_OUTPUT "outputs/phase22-real-journeys/j01/log.txt"
expect_rejected LIVE_PROVIDER_ARTIFACT "outputs/provider-artifacts/serper-response.json"
expect_rejected LANGUAGE_CACHE "tests/harness/.pytest_cache/v/cache/nodeids"

bash "$fixture/scripts/check-repo-hygiene.sh" >/dev/null
echo "repository hygiene negative controls passed"
