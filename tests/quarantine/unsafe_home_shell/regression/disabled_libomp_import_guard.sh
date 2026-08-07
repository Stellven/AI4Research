#!/usr/bin/env bash
set -euo pipefail

HARNESS_DIR="${HARNESS_DIR:-$HOME/.solar/harness}"

"$HARNESS_DIR/tools/guard-libomp-imports.sh"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/lib"
cat > "$tmp/lib/bad.py" <<'PY'
import omlx
PY

set +e
HARNESS_DIR="$tmp" "$HARNESS_DIR/tools/guard-libomp-imports.sh" >/tmp/solar-libomp-guard.out 2>/tmp/solar-libomp-guard.err
rc=$?
set -e

if [[ "$rc" == "0" ]]; then
  echo "FAIL: guard did not reject unsafe import" >&2
  cat /tmp/solar-libomp-guard.out >&2 || true
  cat /tmp/solar-libomp-guard.err >&2 || true
  exit 1
fi

if ! grep -q "unsafe ThunderOMLX package-root import" /tmp/solar-libomp-guard.err; then
  echo "FAIL: guard rejection message missing" >&2
  cat /tmp/solar-libomp-guard.err >&2 || true
  exit 1
fi

echo "libomp import guard regression: PASS"
