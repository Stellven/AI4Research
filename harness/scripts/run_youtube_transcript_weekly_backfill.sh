#!/usr/bin/env bash
set -uo pipefail

HARNESS_DIR="${HARNESS_DIR:-${HOME}/Solar/harness}"
PYTHON="${PYTHON:-python3}"
DB="${DB:-${HOME}/.solar/harness/state/tech-hotspot-radar/tech-hotspot-radar.sqlite}"
STATE_DIR="${STATE_DIR:-${HOME}/.solar/harness/state/tech-hotspot-radar}"
CONFIG="${CONFIG:-$HARNESS_DIR/config/tech-hotspot-radar.yaml}"
LOG_DIR="${LOG_DIR:-${HOME}/.solar/harness/run}"
LOCK_DIR="${LOCK_DIR:-$STATE_DIR/youtube-weekly-db-backfill.lockdir}"

mkdir -p "$LOG_DIR" "$STATE_DIR"
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  if [[ -f "$LOCK_DIR/pid" ]] && kill -0 "$(cat "$LOCK_DIR/pid" 2>/dev/null)" 2>/dev/null; then
    echo "[youtube-weekly-db-backfill] already running; skip $(date)"
    exit 0
  fi
  echo "[youtube-weekly-db-backfill] stale lock removed $(date)"
  rm -rf "$LOCK_DIR"
  mkdir "$LOCK_DIR"
fi
echo "$$" > "$LOCK_DIR/pid"
trap 'rm -rf "$LOCK_DIR"' EXIT INT TERM

export PYTHONPATH="$HARNESS_DIR/lib:${PYTHONPATH:-}"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"
export PYTHONIOENCODING="utf-8"

exec "$PYTHON" "$HARNESS_DIR/scripts/youtube_transcript_weekly_db_backfill.py" \
  --db "$DB" \
  --state-dir "$STATE_DIR" \
  --config "$CONFIG" \
  --start-week "${YOUTUBE_BACKFILL_START_WEEK:-2026-W20}" \
  --end-week "${YOUTUBE_BACKFILL_END_WEEK:-2026-W01}" \
  --enqueue-limit "${YOUTUBE_BACKFILL_ENQUEUE_LIMIT:-12}" \
  --caption-limit "${YOUTUBE_BACKFILL_CAPTION_LIMIT:-12}" \
  --subtitle-limit "${YOUTUBE_BACKFILL_SUBTITLE_LIMIT:-12}" \
  --browser-limit "${YOUTUBE_BACKFILL_BROWSER_LIMIT:-2}" \
  --timeout "${YOUTUBE_BACKFILL_TIMEOUT:-300}" \
  "$@"
