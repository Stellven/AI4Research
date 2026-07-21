#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-${HOME}/Solar/harness}"
CONFIG="${YOUTUBE_INFLUENCE_CONFIG:-$ROOT/config/youtube-influence-digest.yaml}"
LOG_DIR="${ROOT}/logs"
mkdir -p "$LOG_DIR"

exec /usr/bin/env python3 "$ROOT/scripts/youtube_influence_digest.py" \
  --config "$CONFIG" \
  --asr-run-once \
  --force-host \
  --asr-limit "${YOUTUBE_ASR_LIMIT:-1}"
