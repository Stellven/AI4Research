#!/usr/bin/env bash
set -euo pipefail

HARNESS_DIR="${HARNESS_DIR:-${HOME}/Solar/harness}"
CONFIG="${YOUTUBE_INFLUENCE_DIGEST_CONFIG:-$HARNESS_DIR/config/youtube-influence-digest.yaml}"
PYTHON="${PYTHON:-python3}"

exec "$PYTHON" "$HARNESS_DIR/scripts/youtube_influence_digest.py" --config "$CONFIG" "$@"
