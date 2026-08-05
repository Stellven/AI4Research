#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_ROOT="$(mktemp -d /tmp/solar-landlock-test.XXXXXX)"
trap 'rm -rf -- "$TMP_ROOT"' EXIT

mkdir -p "$TMP_ROOT/allowed" "$TMP_ROOT/denied"
printf 'visible\n' >"$TMP_ROOT/allowed/visible.txt"
printf 'must-not-cross-scope\n' >"$TMP_ROOT/denied/secret.txt"

BASE=(
  python3 "$ROOT/tools/landlock_exec.py"
  --read-only /usr
  --read-only /lib
  --read-only /lib64
  --read-only /etc
  --read-write "$TMP_ROOT/allowed"
  --
)

"${BASE[@]}" python3 -c "from pathlib import Path; assert Path('$TMP_ROOT/allowed/visible.txt').read_text().strip() == 'visible'"

python3 "$ROOT/tools/landlock_exec.py" \
  --read-only /usr --read-only /lib --read-only /lib64 --read-only /etc \
  --read-write /dev/null --read-write "$TMP_ROOT/allowed" -- \
  python3 -c "open('/dev/null', 'w').write('ok')"

set +e
"${BASE[@]}" python3 -c "from pathlib import Path; Path('$TMP_ROOT/denied/secret.txt').read_text()" >"$TMP_ROOT/out.log" 2>"$TMP_ROOT/err.log"
rc=$?
set -e

if [[ "$rc" -eq 0 ]]; then
  echo "FAIL: Landlock allowed a sibling-directory read" >&2
  exit 1
fi
if ! grep -Eq 'PermissionError|Permission denied' "$TMP_ROOT/err.log"; then
  echo "FAIL: sibling read failed without a permission-denied signal" >&2
  sed -n '1,120p' "$TMP_ROOT/err.log" >&2
  exit 1
fi

echo "PASS: Landlock allowed the declared root and denied its sibling"
