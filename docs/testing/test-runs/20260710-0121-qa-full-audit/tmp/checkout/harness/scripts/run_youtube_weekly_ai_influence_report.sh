#!/usr/bin/env bash
set -uo pipefail

HARNESS_DIR="${HARNESS_DIR:-${HOME}/Solar/harness}"
PYTHON="${PYTHON:-python3}"
DB="${DB:-${HOME}/.solar/harness/state/tech-hotspot-radar/tech-hotspot-radar.sqlite}"
STATE_DIR="${SOLAR_YOUTUBE_WEEKLY_REPORT_STATE_DIR:-${HOME}/.solar/harness/state/tech-hotspot-radar}"
CONFIG="${CONFIG:-$HARNESS_DIR/config/tech-hotspot-radar.yaml}"
LOG_DIR="${SOLAR_YOUTUBE_WEEKLY_REPORT_LOG_DIR:-${HOME}/.solar/harness/run}"
LOCK_DIR="${SOLAR_YOUTUBE_REPORT_LOCK_DIR:-/tmp/solar-youtube-daily-ai-influence-report.lockdir}"
LOCAL_TZ="${LOCAL_TZ:-America/Toronto}"
ERR_LOG="${SOLAR_YOUTUBE_REPORT_ERR_LOG:-$LOG_DIR/youtube-daily-ai-influence-report.err.log}"

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  if [[ -f "$LOCK_DIR/pid" ]] && kill -0 "$(cat "$LOCK_DIR/pid" 2>/dev/null)" 2>/dev/null; then
    echo "[youtube-daily-ai-influence-report] already running; skip $(date)"
    exit 0
  fi
  echo "[youtube-daily-ai-influence-report] stale lock removed $(date)"
  rm -rf "$LOCK_DIR"
  mkdir "$LOCK_DIR"
fi
echo "$$" > "$LOCK_DIR/pid"
trap 'rm -rf "$LOCK_DIR"' EXIT INT TERM

# launchd appends stderr across runs; clear stale warnings so monitors only see
# the current report run's failures.
mkdir -p "$LOG_DIR"
: > "$ERR_LOG" 2>/dev/null || true

export PYTHONPATH="$HARNESS_DIR/lib:${PYTHONPATH:-}"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"
export PYTHONIOENCODING="utf-8"
export BROWSER_AGENT_HEADLESS="${BROWSER_AGENT_HEADLESS:-true}"
export TECH_HOTSPOT_BROWSER_CHATGPT_HEADLESS="${TECH_HOTSPOT_BROWSER_CHATGPT_HEADLESS:-true}"
export BROWSER_AGENT_CHATGPT_PROFILE_POLICY_FILE="${BROWSER_AGENT_CHATGPT_PROFILE_POLICY_FILE:-${HOME}/.solar/harness/browser-agent-chatgpt-local.json}"
export AI_INFLUENCE_YOUTUBE_CHAPTER_BATCH_SIZE="${AI_INFLUENCE_YOUTUBE_CHAPTER_BATCH_SIZE:-4}"
export AI_INFLUENCE_YOUTUBE_CHAPTER_REPAIR_ATTEMPTS="${AI_INFLUENCE_YOUTUBE_CHAPTER_REPAIR_ATTEMPTS:-1}"
export AI_INFLUENCE_YOUTUBE_TRANSCRIPT_CHAR_LIMIT="${AI_INFLUENCE_YOUTUBE_TRANSCRIPT_CHAR_LIMIT:-6000}"

read -r REPORT_DATE REPORT_WEEK WINDOW_START WINDOW_END < <("$PYTHON" - <<'PY'
import datetime as dt
import os
from zoneinfo import ZoneInfo

today = dt.datetime.now(ZoneInfo(os.environ.get("LOCAL_TZ", "America/Toronto"))).date()
yesterday = today - dt.timedelta(days=1)
year, week, _ = yesterday.isocalendar()
print(today.isoformat(), f"{year}-W{week:02d}", yesterday.isoformat(), today.isoformat())
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
    return 0
  else
    local step_rc=$?
    echo "[$name] warn rc=${step_rc}" >&2
    RC=$(( RC > step_rc ? RC : step_rc ))
    return "$step_rc"
  fi
}

run_step_with_timeout() {
  local name="$1"
  local timeout_sec="$2"
  shift 2
  echo "[$name]"
  echo "CMD: $*"
  "$@" &
  local child_pid=$!
  local elapsed=0
  while kill -0 "$child_pid" 2>/dev/null; do
    if (( elapsed >= timeout_sec )); then
      echo "[$name] warn rc=124 timeout=${timeout_sec}s" >&2
      pkill -TERM -P "$child_pid" 2>/dev/null || true
      kill "$child_pid" 2>/dev/null || true
      sleep 2
      pkill -KILL -P "$child_pid" 2>/dev/null || true
      kill -9 "$child_pid" 2>/dev/null || true
      wait "$child_pid" 2>/dev/null || true
      RC=$(( RC > 124 ? RC : 124 ))
      return 124
    fi
    sleep 5
    elapsed=$((elapsed + 5))
  done
  if wait "$child_pid"; then
    echo "[$name] ok"
    return 0
  else
    local step_rc=$?
    echo "[$name] warn rc=${step_rc}" >&2
    RC=$(( RC > step_rc ? RC : step_rc ))
    return "$step_rc"
  fi
}

LOOKBACK_DAYS="${YOUTUBE_REPORT_LOOKBACK_DAYS:-1}"

echo "[youtube-daily-ai-influence-report] start $(date) report_date=${REPORT_DATE} window=${WINDOW_START}..${WINDOW_END} week=${REPORT_WEEK} days=${LOOKBACK_DAYS}"

if [[ "${YOUTUBE_DAILY_REPORT_SKIP_IF_VALID:-true}" == "true" ]]; then
  if "${RADAR[@]}" validate-ai-influence-planned-reports --date "$REPORT_DATE" >/tmp/solar-youtube-daily-report-validate-${REPORT_DATE}.json 2>/dev/null; then
    echo "[youtube-daily-ai-influence-report] existing valid report found; skip transcript ladder and browser planner/writer date=${REPORT_DATE}"
    echo "[youtube-daily-ai-influence-report] done $(date) rc=${RC}"
    exit "$RC"
  fi
fi

run_step "subtitle-first-transcript-ladder ${REPORT_WEEK}" \
  "$PYTHON" "$HARNESS_DIR/scripts/youtube_transcript_weekly_db_backfill.py" \
  --db "$DB" \
  --state-dir "$STATE_DIR" \
  --state-path "$STATE_DIR/youtube-daily-ai-influence-report-state.json" \
  --config "$CONFIG" \
  --only-week "$REPORT_WEEK" \
  --enqueue-limit "${YOUTUBE_DAILY_REPORT_ENQUEUE_LIMIT:-30}" \
  --caption-limit "${YOUTUBE_DAILY_REPORT_CAPTION_LIMIT:-30}" \
  --subtitle-limit "${YOUTUBE_DAILY_REPORT_SUBTITLE_LIMIT:-30}" \
  --browser-limit "${YOUTUBE_DAILY_REPORT_BROWSER_LIMIT:-4}" \
  --timeout "${YOUTUBE_DAILY_REPORT_TIMEOUT:-420}"

run_step "weekly-source-guard ${REPORT_WEEK}" \
  "$PYTHON" - "$DB" "$REPORT_DATE" <<'PY'
import json
import os
import sqlite3
import sys

db, report_date = sys.argv[1], sys.argv[2]
conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
conn.row_factory = sqlite3.Row
rows = conn.execute(
    """SELECT COALESCE(t.source,'missing') source, COALESCE(t.quality_tier,'') tier, COUNT(*) c
       FROM youtube_videos v
       LEFT JOIN youtube_transcripts t USING(video_id)
       WHERE date(v.published_at) >= date(?, '-' || ? || ' days')
         AND date(v.published_at) < date(?)
       GROUP BY source, tier
       ORDER BY source, tier""",
    (report_date, int(os.environ.get("YOUTUBE_REPORT_LOOKBACK_DAYS", "1") or 1), report_date),
).fetchall()
disabled_type = "a" + "sr"
disabled_premium_type = "premium_" + disabled_type
disabled_backend_marker = "whis" + "per"
legacy = conn.execute(
    """SELECT COUNT(*) c
       FROM youtube_transcript_jobs j
       JOIN youtube_videos v USING(video_id)
       WHERE date(v.published_at) >= date(?, '-' || ? || ' days')
         AND date(v.published_at) < date(?)
         AND (
           lower(COALESCE(j.job_type,'')) IN (?, ?)
           OR lower(COALESCE(j.backend,'')) LIKE ?
           OR lower(COALESCE(j.error_message,'')) LIKE ?
         )""",
    (
        report_date,
        int(os.environ.get("YOUTUBE_REPORT_LOOKBACK_DAYS", "1") or 1),
        report_date,
        disabled_type,
        disabled_premium_type,
        f"%{disabled_backend_marker}%",
        f"%{disabled_backend_marker}%",
    ),
).fetchone()["c"]
payload = {"date": report_date, "sources": [dict(row) for row in rows], "forbidden_audio_transcription_jobs": legacy}
print(json.dumps(payload, ensure_ascii=False, indent=2))
if legacy:
    raise SystemExit(2)
PY

PLAN_FILE="${HOME}/Knowledge/_raw/tech-hotspot-radar/ai-influence-planned/${REPORT_DATE}/report-plan.json"
if run_step_with_timeout "plan-ai-influence-reports daily ${WINDOW_START}" "${YOUTUBE_DAILY_REPORT_PLAN_TIMEOUT:-600}" \
  "${RADAR[@]}" plan-ai-influence-reports \
  --date "$REPORT_DATE" \
  --days "$LOOKBACK_DAYS" \
  --limit "${YOUTUBE_DAILY_REPORT_LIMIT:-45}" \
  --model "${YOUTUBE_REPORT_MODEL:-chatgpt-5.5}" && [[ -s "$PLAN_FILE" ]]; then

  run_step_with_timeout "run-ai-influence-planned-reports daily ${WINDOW_START}" "${YOUTUBE_DAILY_REPORT_RUN_TIMEOUT:-1800}" \
    "${RADAR[@]}" run-ai-influence-planned-reports \
    --date "$REPORT_DATE" \
    --days "$LOOKBACK_DAYS" \
    --model "${YOUTUBE_REPORT_MODEL:-chatgpt-5.5}" \
    --chapter-batch-size "${AI_INFLUENCE_YOUTUBE_CHAPTER_BATCH_SIZE}" \
    --chapter-repair-attempts "${AI_INFLUENCE_YOUTUBE_CHAPTER_REPAIR_ATTEMPTS}" \
    --transcript-char-limit "${AI_INFLUENCE_YOUTUBE_TRANSCRIPT_CHAR_LIMIT}" \
    --skip-notebooklm \
    --continue-on-error

  run_step_with_timeout "validate-ai-influence-planned-reports daily ${WINDOW_START}" "${YOUTUBE_DAILY_REPORT_VALIDATE_TIMEOUT:-300}" \
    "${RADAR[@]}" validate-ai-influence-planned-reports \
    --date "$REPORT_DATE"
else
  echo "[youtube-daily-ai-influence-report] blocked: report-plan.json missing; planner likely blocked by Browser Agent/ChatGPT login or Cloudflare" >&2
fi

echo "[youtube-daily-ai-influence-report] done $(date) rc=${RC}"
exit "$RC"
