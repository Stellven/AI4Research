#!/usr/bin/env bash
set -euo pipefail

HARNESS_DIR="${HARNESS_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
LAUNCHER="$HARNESS_DIR/pane-launcher.sh"
TMP_ROOT="$(mktemp -d /tmp/solar-pane-landlock-test.XXXXXX)"
trap 'rm -rf -- "$TMP_ROOT"' EXIT

grep -Fq 'run_codex_with_filesystem_scope' "$LAUNCHER"
grep -Fq 'SOLAR_CODEX_PANE_FS_ISOLATION' "$LAUNCHER"
grep -Fq 'SOLAR_CODEX_PANE_STRICT_FS_SCOPE' "$LAUNCHER"
grep -Fq 'landlock_exec.py' "$LAUNCHER"
grep -Fq '"$ORIGINAL_WORK_DIR" "$WORK_DIR"' "$LAUNCHER"
grep -Fq '"$codex_home/auth.json"' "$LAUNCHER"
grep -Fq '"$codex_arg0_dir"' "$LAUNCHER"

mkdir -p "$TMP_ROOT/project" "$TMP_ROOT/denied"
printf 'must-not-cross-scope\n' >"$TMP_ROOT/denied/secret.txt"
FAKE_CODEX="$TMP_ROOT/project/codex"
cat >"$FAKE_CODEX" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
echo "FAKE_CODEX_STARTED"
if cat "$DENIED_FILE" >/dev/null 2>&1; then
  echo "FAIL: fake Codex read the sibling directory" >&2
  exit 91
fi
echo "FAKE_CODEX_SIBLING_READ_DENIED"
SH
chmod +x "$FAKE_CODEX"

output="$({
  DENIED_FILE="$TMP_ROOT/denied/secret.txt" \
  HARNESS_DIR="$HARNESS_DIR" \
  SOLAR_PANE_RUNTIME=codex \
  SOLAR_CODEX_BIN="$FAKE_CODEX" \
  SOLAR_CODEX_BYPASS=0 \
  SOLAR_CODEX_TRUST_WORKSPACE=0 \
  SHELL=/bin/true \
  TERM=xterm \
  bash "$LAUNCHER" pm "$TMP_ROOT/project"
} 2>&1)"

grep -Fq 'Filesystem boundary:' <<<"$output"
grep -Fq 'landlock_exec: active' <<<"$output"
grep -Fq 'FAKE_CODEX_STARTED' <<<"$output"
grep -Fq 'FAKE_CODEX_SIBLING_READ_DENIED' <<<"$output"

echo "PASS: Codex panes route through the strict Landlock launcher"
