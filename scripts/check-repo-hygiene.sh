#!/usr/bin/env bash
# Reject machine-local, generated, and raw test-run state in the Git index.
set -euo pipefail

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_dir"

violations="$(mktemp)"
trap 'rm -f "$violations"' EXIT

record_violation() {
  printf '%s\t%s\n' "$1" "$2" >>"$violations"
}

git ls-files -z | while IFS= read -r -d '' path; do
  case "$path" in
    .DS_Store|*/.DS_Store|._*|*/._*)
      record_violation "OS_METADATA" "$path"
      ;;
    Thumbs.db|*/Thumbs.db|ehthumbs.db|*/ehthumbs.db|desktop.ini|*/desktop.ini|Desktop.ini|*/Desktop.ini|\$RECYCLE.BIN/*|*/\$RECYCLE.BIN/*)
      record_violation "OS_METADATA" "$path"
      ;;
  esac

  case "$path" in
    node_modules|node_modules/*|*/node_modules|*/node_modules/*|.pnpm-store/*|*/.pnpm-store/*|.npm/*|*/.npm/*|.yarn/*|*/.yarn/*|.bun/*|*/.bun/*)
      record_violation "PACKAGE_CACHE" "$path"
      ;;
  esac

  case "$path" in
    .venv|.venv/*|.venv*/*|*/.venv|*/.venv/*|*/.venv*/*|venv|venv/*|*/venv|*/venv/*|env|env/*|*/env|*/env/*|ENV|ENV/*|*/ENV|*/ENV/*)
      record_violation "LOCAL_ENV" "$path"
      ;;
    .pytest_cache/*|*/.pytest_cache/*|__pycache__/*|*/__pycache__/*|.mypy_cache/*|*/.mypy_cache/*|.ruff_cache/*|*/.ruff_cache/*|.tox/*|*/.tox/*|.nox/*|*/.nox/*)
      record_violation "LANGUAGE_CACHE" "$path"
      ;;
    *.pyc|*.pyo)
      record_violation "LANGUAGE_CACHE" "$path"
      ;;
  esac

  case "$path" in
    .env.template|*/.env.template|.env.example|*/.env.example)
      ;;
    .env|*/.env|.env.*|*/.env.*)
      record_violation "LOCAL_ENV_CONFIG" "$path"
      ;;
  esac

  case "$path" in
    tmp/*|tmp_*|test-results/*|*/test-results/*|playwright-report/*|*/playwright-report/*|blob-report/*|*/blob-report/*|.nyc_output/*|*/.nyc_output/*)
      record_violation "GENERATED_OUTPUT" "$path"
      ;;
    docs/testing/test-runs/README.md)
      ;;
    docs/testing/test-runs/*)
      record_violation "RAW_TEST_EVIDENCE" "$path"
      ;;
    harness/logs/.gitkeep)
      ;;
    harness/logs/*|harness/sprints/*|harness/run/*|harness/runs/*|harness/state/*|harness/queue/*)
      record_violation "HARNESS_RUNTIME" "$path"
      ;;
    harness/artifacts/scientific/sprint-*/*|harness/artifacts/scientific/workflow-runs/*)
      record_violation "HARNESS_RUNTIME" "$path"
      ;;
    Feature\ list\ stuff/Solar_Harness_All_Sources_*/*)
      record_violation "MACHINE_SOURCE_ARCHIVE" "$path"
      ;;
  esac
done

if [ -s "$violations" ]; then
  echo "repository hygiene FAILED: forbidden tracked paths:" >&2
  LC_ALL=C sort -u "$violations" >&2
  exit 1
fi

echo "repository hygiene passed: no forbidden machine-local or generated paths are tracked"
