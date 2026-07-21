#!/usr/bin/env bash
# check-dry-run.sh — assert that `install.sh --dry-run` is side-effect-free:
# a dry run must write ZERO files anywhere under HOME (which is where both
# ~/.solar and ~/.claude default). Verifies the dry-run contract from the plan.
set -eu

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
home="$(mktemp -d "${TMPDIR:-/tmp}/solar-dryrun.XXXXXX")"
log="$(mktemp "${TMPDIR:-/tmp}/solar-dryrun-log.XXXXXX")"
trap 'rm -rf "$home" "$log"' EXIT

if ! HOME="$home" "$repo_dir/install.sh" \
    --yes --components kernel,harness --dry-run --fake-keys --skip-llm-cli \
    >"$log" 2>&1; then
    echo "check-dry-run FAILED: --dry-run install exited nonzero:" >&2
    cat "$log" >&2
    exit 1
fi

created="$(find "$home" -mindepth 1 2>/dev/null || true)"
if [ -n "$created" ]; then
    echo "check-dry-run FAILED: --dry-run created files under HOME:" >&2
    printf '%s\n' "$created" >&2
    exit 1
fi
echo "check-dry-run passed: --dry-run wrote zero files under HOME"
