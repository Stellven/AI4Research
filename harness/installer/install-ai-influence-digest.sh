#!/usr/bin/env bash
set -euo pipefail

LABEL="com.solar.ai-influence-daily-digest"
HARNESS_DIR="${HARNESS_DIR:-${HOME}/Solar/harness}"
PLIST_SRC="$HARNESS_DIR/${LABEL}.plist"
PLIST_DST="$HOME/Library/LaunchAgents/${LABEL}.plist"
CONFIG="$HARNESS_DIR/config/ai-influence-daily-digest.yaml"

host="$(hostname 2>/dev/null || true)"
case "$host" in
  solar-host.local|solar-host) ;;
  *)
    echo "[ai-digest] skip install: Mac-mini-only job, current host=$host"
    exit 0
    ;;
esac

mkdir -p "$HOME/Library/LaunchAgents" "$HARNESS_DIR/logs" "$HOME/Knowledge/_raw/ai-influence-daily-digest"
chmod +x "$HARNESS_DIR/scripts/run_ai_influence_digest.sh" "$HARNESS_DIR/scripts/ai_influence_digest.py"

python3 "$HARNESS_DIR/scripts/ai_influence_digest.py" --config "$CONFIG" --dry-run --limit-accounts 1 >/dev/null

cp "$PLIST_SRC" "$PLIST_DST"
launchctl bootout "gui/$(id -u)" "$PLIST_DST" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$PLIST_DST"
launchctl enable "gui/$(id -u)/$LABEL"

echo "[ai-digest] installed: $PLIST_DST"
echo "[ai-digest] schedule: 08:07, 13:07, 18:07 local time"
echo "[ai-digest] raw output: $HOME/Knowledge/_raw/ai-influence-daily-digest"
