#!/usr/bin/env bash
# Release coherence must judge the tracked release tree, not owner-local build
# residue. The same stale tag is ignored while untracked and rejected once it
# becomes a tracked release input.
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/solar-release-coherence-tracked.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT

git clone --no-local --quiet "$repo_root" "$tmp/repo"
cp "$repo_root/scripts/check-release-coherence.sh" \
   "$tmp/repo/scripts/check-release-coherence.sh"
cd "$tmp/repo"

bash scripts/check-release-coherence.sh >"$tmp/baseline.log" 2>&1

printf '%s\n' 'v1.0.0-rc.0' > distribution/pipx/owner-local-build-note.txt
if ! bash scripts/check-release-coherence.sh >"$tmp/untracked.log" 2>&1; then
    echo "FAIL: an untracked pipx file changed release coherence" >&2
    tail -20 "$tmp/untracked.log" >&2
    exit 1
fi

git add distribution/pipx/owner-local-build-note.txt
if bash scripts/check-release-coherence.sh >"$tmp/tracked.log" 2>&1; then
    echo "FAIL: a tracked stale pipx tag escaped release coherence" >&2
    exit 1
fi
grep -q 'pipx tree references stale tags: v1.0.0-rc.0' "$tmp/tracked.log"

echo "release coherence tracked-input boundary: PASS"
