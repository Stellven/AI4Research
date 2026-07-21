#!/usr/bin/env bash
# Remove the Solar status-server systemd user service (Linux / WSL2).
set -euo pipefail
: "${HOME:?HOME must be set}"   # refuse to run if HOME is empty (anchors the rm path)
UNIT="solar-status-server.service"
systemctl --user disable --now "$UNIT" 2>/dev/null || true
rm -f "$HOME/.config/systemd/user/$UNIT"
systemctl --user daemon-reload 2>/dev/null || true
echo "[uninstall] removed $UNIT"
