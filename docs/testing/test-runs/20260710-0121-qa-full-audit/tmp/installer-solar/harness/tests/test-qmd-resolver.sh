#!/usr/bin/env bash
set -euo pipefail

HARNESS_DIR="${HARNESS_DIR:-$HOME/.solar/harness}"
BIN="$HARNESS_DIR/solar-harness.sh"
RESOLVER="$HARNESS_DIR/lib/qmd-resolver.sh"

pass() { printf 'PASS %s\n' "$*"; }
fail() { printf 'FAIL %s\n' "$*" >&2; exit 1; }
skip() { printf 'SKIP %s\n' "$*"; exit 0; }

[[ -x "$RESOLVER" ]] || fail "qmd resolver missing or not executable"
bash -n "$RESOLVER" "$BIN" "$HARNESS_DIR/lib/qmd-embed-runner.sh" "$HARNESS_DIR/lib/qmd-launcher-repair.sh"
pass "shell syntax"

QMD_BIN_FOUND="$(env -i HOME="$HOME" PATH="/usr/bin:/bin:/usr/sbin:/sbin" bash "$RESOLVER" --print 2>/dev/null || true)"
[[ -n "$QMD_BIN_FOUND" ]] || skip "qmd not installed on this machine"
[[ -x "$QMD_BIN_FOUND" ]] || fail "resolved qmd is not executable: $QMD_BIN_FOUND"
pass "resolver works under stripped PATH: $QMD_BIN_FOUND"

OUT="$(env -i HOME="$HOME" PATH="/usr/bin:/bin:/usr/sbin:/sbin" HARNESS_DIR="$HARNESS_DIR" bash "$BIN" wiki qmd-status 2>&1)" || {
  printf '%s\n' "$OUT" >&2
  fail "qmd-status failed under stripped PATH"
}
printf '%s\n' "$OUT" | grep -Eiq 'NODE_MODULE_VERSION|ERR_DLOPEN_FAILED|node: No such file or directory' && {
  printf '%s\n' "$OUT" >&2
  fail "qmd-status used wrong node runtime under stripped PATH"
}
pass "qmd-status works under stripped PATH"
