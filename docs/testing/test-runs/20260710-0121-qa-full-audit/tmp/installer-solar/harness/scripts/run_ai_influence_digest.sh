#!/usr/bin/env bash
set -euo pipefail

HARNESS_DIR="${HARNESS_DIR:-${HOME}/Solar/harness}"
PYTHON="${PYTHON:-python3}"
ACCOUNTS="${AI_INFLUENCE_ACCOUNTS:-$HARNESS_DIR/ai-influence-digest/references/accounts_extended.txt}"
STATE_DIR="${AI_INFLUENCE_STATE_DIR:-$HOME/.solar/harness/state/ai-influence-digest}"
RAW_DIR="${AI_INFLUENCE_RAW_DIR:-$HOME/Knowledge/_raw/ai-influence-daily-digest}"
SLEEP_SECONDS="${AI_INFLUENCE_SLEEP_SECONDS:-1.0}"

exec "$PYTHON" "$HARNESS_DIR/scripts/ai_influence_daily.py" \
  --accounts "$ACCOUNTS" \
  --state-dir "$STATE_DIR" \
  --raw-dir "$RAW_DIR" \
  --sleep-between-accounts "$SLEEP_SECONDS" \
  "$@" \
  run
