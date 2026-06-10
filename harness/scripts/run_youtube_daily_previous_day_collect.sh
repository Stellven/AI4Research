#!/usr/bin/env bash
set -uo pipefail

HARNESS_DIR="${HARNESS_DIR:-${HOME}/Solar/harness}"
PYTHON="${PYTHON:-python3}"
DB="${DB:-${HOME}/.solar/harness/state/tech-hotspot-radar/tech-hotspot-radar.sqlite}"
STATE_DIR="${STATE_DIR:-${HOME}/.solar/harness/state/tech-hotspot-radar}"
CONFIG="${CONFIG:-$HARNESS_DIR/config/tech-hotspot-radar.yaml}"
LOG_DIR="${LOG_DIR:-${HOME}/.solar/harness/run}"
LOCK_DIR="${LOCK_DIR:-$STATE_DIR/youtube-daily-previous-day.lockdir}"
LOCAL_TZ="${LOCAL_TZ:-America/Toronto}"

mkdir -p "$LOG_DIR" "$STATE_DIR"
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  if [[ -f "$LOCK_DIR/pid" ]] && kill -0 "$(cat "$LOCK_DIR/pid" 2>/dev/null)" 2>/dev/null; then
    echo "[youtube-daily-previous-day] already running; skip $(date)"
    exit 0
  fi
  echo "[youtube-daily-previous-day] stale lock removed $(date)"
  rm -rf "$LOCK_DIR"
  mkdir "$LOCK_DIR"
fi
echo "$$" > "$LOCK_DIR/pid"
trap 'rm -rf "$LOCK_DIR"' EXIT INT TERM

export PYTHONPATH="$HARNESS_DIR/lib:${PYTHONPATH:-}"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"
export PYTHONIOENCODING="utf-8"
export BROWSER_AGENT_HEADLESS="${BROWSER_AGENT_HEADLESS:-false}"
export TECH_HOTSPOT_BROWSER_CHATGPT_HEADLESS="${TECH_HOTSPOT_BROWSER_CHATGPT_HEADLESS:-false}"
export BROWSER_AGENT_CHATGPT_PROFILE_POLICY_FILE="${BROWSER_AGENT_CHATGPT_PROFILE_POLICY_FILE:-${HOME}/.solar/harness/browser-agent-chatgpt-local.json}"

read -r YESTERDAY_DATE YESTERDAY_WEEK < <("$PYTHON" - <<'PY'
import datetime as dt
import os
from zoneinfo import ZoneInfo

today = dt.datetime.now(ZoneInfo(os.environ.get("LOCAL_TZ", "America/Toronto"))).date()
day = today - dt.timedelta(days=1)
year, week, _ = day.isocalendar()
print(day.isoformat(), f"{year}-W{week:02d}")
PY
)

RADAR=( "$PYTHON" "$HARNESS_DIR/scripts/tech_hotspot_radar.py" --config "$CONFIG" --db "$DB" )
RC=0

run_step() {
  local name="$1"
  shift
  echo "[$name]"
  echo "CMD: $*"
  if "$@"; then
    echo "[$name] ok"
  else
    local step_rc=$?
    echo "[$name] warn rc=${step_rc}" >&2
    RC=$(( RC > step_rc ? RC : step_rc ))
  fi
}

echo "[youtube-daily-previous-day] start $(date) yesterday=${YESTERDAY_DATE} week=${YESTERDAY_WEEK}"

run_step "collect-youtube-metadata" \
  "${RADAR[@]}" collect-youtube \
  --per-channel-limit "${YOUTUBE_DAILY_PER_CHANNEL_LIMIT:-5}" \
  --force

run_step "subtitle-first-transcript-ladder ${YESTERDAY_WEEK}" \
  "$PYTHON" "$HARNESS_DIR/scripts/youtube_transcript_weekly_db_backfill.py" \
  --db "$DB" \
  --state-dir "$STATE_DIR" \
  --state-path "$STATE_DIR/youtube-daily-previous-day-state.json" \
  --config "$CONFIG" \
  --only-week "$YESTERDAY_WEEK" \
  --enqueue-limit "${YOUTUBE_DAILY_ENQUEUE_LIMIT:-20}" \
  --caption-limit "${YOUTUBE_DAILY_CAPTION_LIMIT:-20}" \
  --subtitle-limit "${YOUTUBE_DAILY_SUBTITLE_LIMIT:-20}" \
  --browser-limit "${YOUTUBE_DAILY_BROWSER_LIMIT:-3}" \
  --timeout "${YOUTUBE_DAILY_TIMEOUT:-300}"

run_step "daily-summary ${YESTERDAY_DATE}" \
  "$PYTHON" - "$DB" "$YESTERDAY_DATE" <<'PY'
import json
import sqlite3
import sys

db, day = sys.argv[1], sys.argv[2]
conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
conn.row_factory = sqlite3.Row
videos = conn.execute("SELECT COUNT(*) c FROM youtube_videos WHERE date(published_at)=date(?)", (day,)).fetchone()["c"]
tiers = {
    row["tier"] or "": row["c"]
    for row in conn.execute(
        """SELECT COALESCE(t.quality_tier,'') tier, COUNT(*) c
           FROM youtube_transcripts t
           JOIN youtube_videos v USING(video_id)
           WHERE date(v.published_at)=date(?)
           GROUP BY tier""",
        (day,),
    )
}
jobs = {
    row["status"] or "": row["c"]
    for row in conn.execute(
        """SELECT COALESCE(j.status,'') status, COUNT(*) c
           FROM youtube_transcript_jobs j
           JOIN youtube_videos v USING(video_id)
           WHERE date(v.published_at)=date(?)
           GROUP BY status""",
        (day,),
    )
}
asr_jobs = conn.execute(
    """SELECT COUNT(*) c
       FROM youtube_transcript_jobs j
       JOIN youtube_videos v USING(video_id)
       WHERE date(v.published_at)=date(?)
         AND (lower(COALESCE(j.job_type,'')) LIKE '%asr%' OR lower(COALESCE(j.backend,'')) LIKE '%asr%')""",
    (day,),
).fetchone()["c"]
print(json.dumps({
    "date": day,
    "videos": videos,
    "usable": sum(tiers.get(k, 0) for k in ("T0", "T1", "T2")),
    "metadata_t3": tiers.get("T3", 0) + tiers.get("metadata", 0) + tiers.get("metadata_only", 0),
    "pending": jobs.get("pending", 0) + jobs.get("queued", 0),
    "failed": jobs.get("failed", 0),
    "running": jobs.get("running", 0),
    "asr_jobs": asr_jobs,
}, ensure_ascii=False, indent=2))
PY

echo "[youtube-daily-previous-day] done $(date) rc=${RC}"
if [[ "${ALLOW_PARTIAL_SUCCESS:-1}" == "1" && "$RC" != "0" ]]; then
  echo "[youtube-daily-previous-day] completed with warnings; ALLOW_PARTIAL_SUCCESS=1 so exiting 0"
  exit 0
fi
exit "$RC"
