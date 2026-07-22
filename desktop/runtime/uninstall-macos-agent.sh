#!/usr/bin/env bash
# Remove the Solar status-server LaunchAgent (macOS).
set -euo pipefail
: "${HOME:?HOME must be set}"   # refuse to run if HOME is empty (anchors the rm path)
LABEL="com.solar.status-server"
DST="$HOME/Library/LaunchAgents/$LABEL.plist"
launchctl unload "$DST" 2>/dev/null || true
rm -f "$DST"
echo "[uninstall] removed $LABEL"
