#!/usr/bin/env bash
# Install the Solar status-server systemd user service (Linux / WSL2).
# enable-linger lets it run without an active login (survives logout; runs in WSL).
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/solar-status-server.service"
UNIT="solar-status-server.service"
DST="$HOME/.config/systemd/user/$UNIT"

command -v systemctl >/dev/null || { echo "ERROR: systemd not available" >&2; exit 1; }
[ -f "$HOME/.solar/harness/lib/symphony/status-server.py" ] || {
  echo "ERROR: Solar runtime not installed at ~/.solar/harness — run the Solar installer first" >&2; exit 1; }

mkdir -p "$HOME/.config/systemd/user"
cp "$SRC" "$DST"
systemctl --user daemon-reload
loginctl enable-linger "$(whoami)" 2>/dev/null || true
systemctl --user enable --now "$UNIT"

echo "[install] started $UNIT"
echo "[install] status: systemctl --user status $UNIT"
echo "[install] health: curl -fsS http://127.0.0.1:\$(cat ~/.solar/harness/run/status-server.port)/healthz"
