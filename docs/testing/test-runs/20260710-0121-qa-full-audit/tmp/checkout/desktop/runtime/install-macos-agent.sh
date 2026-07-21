#!/usr/bin/env bash
# Install the Solar status-server LaunchAgent (macOS). Substitutes __HOME_DIR__,
# validates the plist, and (re)loads it so the runtime starts now + at every login.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/com.solar.status-server.plist"
LABEL="com.solar.status-server"
DST="$HOME/Library/LaunchAgents/$LABEL.plist"

[ "$(uname)" = "Darwin" ] || { echo "ERROR: macOS only (uname=$(uname))" >&2; exit 1; }
[ -f "$HOME/.solar/harness/lib/symphony/status-server.py" ] || {
  echo "ERROR: Solar runtime not installed at ~/.solar/harness — run the Solar installer first" >&2; exit 1; }

# Resolve a Python >= 3.11 absolute path. launchd runs with no shell PATH, so the
# plist must reference the concrete interpreter — and its location differs by arch
# (/opt/homebrew on Apple Silicon, /usr/local on Intel). The Apple stub
# /usr/bin/python3 is too old (and xcode-select-gated), so we require Homebrew 3.11+.
resolve_python() {
  local cands=() c bp
  if command -v brew >/dev/null 2>&1; then
    bp="$(brew --prefix python@3.11 2>/dev/null || true)"
    [ -n "$bp" ] && cands+=("$bp/bin/python3.11")
  fi
  cands+=(/opt/homebrew/bin/python3.11 /usr/local/bin/python3.11 \
          /opt/homebrew/bin/python3.12 /usr/local/bin/python3.12)
  command -v python3.11 >/dev/null 2>&1 && cands+=("$(command -v python3.11)")
  command -v python3    >/dev/null 2>&1 && cands+=("$(command -v python3)")
  for c in "${cands[@]}"; do
    [ -x "$c" ] || continue
    "$c" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)' 2>/dev/null \
      && { echo "$c"; return 0; }
  done
  return 1
}
PY="$(resolve_python || true)"
[ -n "$PY" ] || { echo "ERROR: Solar needs Python >= 3.11. Install it with:  brew install python@3.11" >&2; exit 1; }
echo "[install] python: $PY"

mkdir -p "$HOME/Library/LaunchAgents" "$HOME/.solar/logs"
sed -e "s#__HOME_DIR__#$HOME#g" -e "s#__PYTHON_BIN__#$PY#g" "$SRC" > "$DST"
plutil -lint "$DST"

# reload if already present (launchctl load is idempotent-unfriendly)
launchctl unload "$DST" 2>/dev/null || true
launchctl load "$DST"

echo "[install] loaded $LABEL"
echo "[install] verify:  launchctl list | grep $LABEL"
echo "[install] health:   curl -fsS http://127.0.0.1:\$(cat ~/.solar/harness/run/status-server.port)/healthz"
