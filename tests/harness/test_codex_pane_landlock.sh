#!/usr/bin/env bash
set -euo pipefail

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "SKIP: Landlock pane integration is Linux-only"
  exit 0
fi

HARNESS_DIR="${HARNESS_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../harness" && pwd)}"
LAUNCHER="$HARNESS_DIR/pane-launcher.sh"
TMP_ROOT="$(mktemp -d /tmp/solar-pane-landlock-test.XXXXXX)"
trap 'rm -rf -- "$TMP_ROOT"' EXIT

grep -Fq 'run_codex_with_filesystem_scope' "$LAUNCHER"
grep -Fq 'resolve_codex_source_home' "$LAUNCHER"
grep -Fq 'codex_pane_state_home' "$LAUNCHER"
grep -Fq 'SOLAR_CODEX_PANE_FS_ISOLATION' "$LAUNCHER"
grep -Fq 'SOLAR_CODEX_PANE_STRICT_FS_SCOPE' "$LAUNCHER"
grep -Fq 'landlock_exec.py' "$LAUNCHER"
grep -Fq '"$ORIGINAL_WORK_DIR" "$WORK_DIR"' "$LAUNCHER"
grep -Fq 'export CODEX_HOME="$sandbox_codex_home"' "$LAUNCHER"
grep -Fq '"$source_codex_home/auth.json"' "$LAUNCHER"
grep -Fq '"$codex_arg0_dir"' "$LAUNCHER"
grep -Fq '/etc/resolv.conf /etc/hosts /etc/nsswitch.conf /etc/gai.conf' "$LAUNCHER"

mkdir -p "$TMP_ROOT/project" "$TMP_ROOT/denied" "$TMP_ROOT/home/.codex" "$TMP_ROOT/stale-codex-home"
printf 'must-not-cross-scope\n' >"$TMP_ROOT/denied/secret.txt"
printf '{"fixture":true}\n' >"$TMP_ROOT/home/.codex/auth.json"
printf 'must_not_be_projected = true\n' >"$TMP_ROOT/home/.codex/config.toml"
printf 'stale = true\n' >"$TMP_ROOT/stale-codex-home/config.toml"
ln -s "$TMP_ROOT/home/.codex/auth.json" "$TMP_ROOT/stale-codex-home/auth.json"
FAKE_CODEX="$TMP_ROOT/project/codex"
cat >"$FAKE_CODEX" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
echo "FAKE_CODEX_STARTED"
printf '%s\n' "$@" | grep -Fxq 'cli_auth_credentials_store="file"'
test "$CODEX_HOME" != "$SOURCE_CODEX_HOME"
test -f "$CODEX_HOME/auth.json"
test ! -L "$CODEX_HOME/auth.json"
test "$(stat -c %a "$CODEX_HOME/auth.json")" = "600"
grep -Fq '"fixture":true' "$CODEX_HOME/auth.json"
test "$(stat -c %a "$CODEX_HOME/config.toml")" = "600"
grep -Fxq 'cli_auth_credentials_store = "file"' "$CODEX_HOME/config.toml"
! grep -Fq 'must_not_be_projected' "$CODEX_HOME/config.toml"
profiles=("$CODEX_HOME"/solar-managed-*.config.toml)
test -f "${profiles[0]}"
test ! -L "${profiles[0]}"
echo "FAKE_CODEX_SANDBOX_HOME_READY"
cat /etc/resolv.conf >/dev/null
echo "FAKE_CODEX_RESOLVER_READABLE"
if cat "$DENIED_FILE" >/dev/null 2>&1; then
  echo "FAIL: fake Codex read the sibling directory" >&2
  exit 91
fi
echo "FAKE_CODEX_SIBLING_READ_DENIED"
SH
chmod +x "$FAKE_CODEX"

output="$({
  DENIED_FILE="$TMP_ROOT/denied/secret.txt" \
  SOURCE_CODEX_HOME="$TMP_ROOT/home/.codex" \
  HOME="$TMP_ROOT/home" \
  CODEX_HOME="$TMP_ROOT/stale-codex-home" \
  SOLAR_CODEX_PANE_STATE_ROOT="$TMP_ROOT/pane-state" \
  SOLAR_CODEX_PANE_TMP_ROOT="$TMP_ROOT/pane-tmp" \
  HARNESS_DIR="$HARNESS_DIR" \
  SOLAR_PANE_RUNTIME=codex \
  SOLAR_CODEX_BIN="$FAKE_CODEX" \
  SOLAR_CODEX_BYPASS=0 \
  SOLAR_CODEX_PANE_FS_ISOLATION=landlock \
  SOLAR_CODEX_TRUST_WORKSPACE=1 \
  SOLAR_HARNESS_SESSION=solar-pane-landlock-test \
  SHELL=/bin/true \
  TERM=xterm \
  bash "$LAUNCHER" pm "$TMP_ROOT/project"
} 2>&1)"

grep -Fq 'Filesystem boundary:' <<<"$output"
grep -Fq 'landlock_exec: active' <<<"$output"
grep -Fq 'FAKE_CODEX_STARTED' <<<"$output"
grep -Fq 'FAKE_CODEX_SANDBOX_HOME_READY' <<<"$output"
grep -Fq 'FAKE_CODEX_RESOLVER_READABLE' <<<"$output"
grep -Fq 'FAKE_CODEX_SIBLING_READ_DENIED' <<<"$output"

echo "PASS: Codex panes route through the strict Landlock launcher"
