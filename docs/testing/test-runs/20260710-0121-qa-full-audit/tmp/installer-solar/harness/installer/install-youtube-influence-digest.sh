#!/usr/bin/env bash
set -euo pipefail

LABEL="com.solar.youtube-influence-digest"
HARNESS_DIR="${HARNESS_DIR:-${HOME}/Solar/harness}"
PLIST_SRC="$HARNESS_DIR/${LABEL}.plist"
PLIST_DST="$HOME/Library/LaunchAgents/${LABEL}.plist"
CONFIG="$HARNESS_DIR/config/youtube-influence-digest.yaml"

host="$(hostname 2>/dev/null || true)"
case "$host" in
  solar-host.local|solar-host) ;;
  *)
    echo "[youtube-digest] skip install: Mac-mini-only job, current host=$host"
    exit 0
    ;;
esac

mkdir -p "$HOME/Library/LaunchAgents" "$HARNESS_DIR/logs" "$HOME/Knowledge/_raw/youtube-influence-digest"
chmod +x "$HARNESS_DIR/scripts/run_youtube_influence_digest.sh" "$HARNESS_DIR/scripts/youtube_influence_digest.py"

python3 "$HARNESS_DIR/scripts/youtube_influence_digest.py" --config "$CONFIG" --dry-run --force-host >/dev/null

cp "$PLIST_SRC" "$PLIST_DST"
launchctl bootout "gui/$(id -u)" "$PLIST_DST" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$PLIST_DST"
launchctl enable "gui/$(id -u)/$LABEL"

echo "[youtube-digest] installed: $PLIST_DST"
echo "[youtube-digest] schedule: 08:17, 13:17, 18:17 local time"
echo "[youtube-digest] raw output: $HOME/Knowledge/_raw/youtube-influence-digest"
