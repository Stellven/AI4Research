#!/usr/bin/env bash
set -euo pipefail
# These tests reference lib/, bin/ and tools/ relative to the working
# directory, so they need to run from harness/. They used to live at
# harness/tests/, where "$0/.." was harness/; after the move to
# tests/harness/ the same expression lands in tests/ instead. Sibling tests
# in this directory already resolve harness/ this way.
cd "$(dirname "$0")/../../harness"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

mkdir -p "$TMP/work/subdir"
touch "$TMP/work/subdir/file.txt"

WRAPPER="$PWD/bin/find"
chmod +x "$WRAPPER"

SOLAR_SAFE_FIND_ROOT="$TMP/work" "$WRAPPER" "$TMP/work" -type f | grep -q "file.txt" \
  || { echo "FAIL: allowed workspace find did not return file"; exit 1; }

if SOLAR_SAFE_FIND_ROOT="$TMP/work" "$WRAPPER" "$HOME" -maxdepth 1 -type d >/tmp/solar-safe-find.out 2>&1; then
  echo "FAIL: protected find unexpectedly succeeded"
  exit 1
fi

grep -q "blocked path outside workspace" /tmp/solar-safe-find.out \
  || { echo "FAIL: blocked find did not explain workspace guard"; exit 1; }

echo '{"ok": true, "feature": "safe_find_wrapper"}'
