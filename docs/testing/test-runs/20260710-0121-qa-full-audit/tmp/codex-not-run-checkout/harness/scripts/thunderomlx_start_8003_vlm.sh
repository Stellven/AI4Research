#!/usr/bin/env bash
set -euo pipefail

HARNESS_DIR="${HARNESS_DIR:-$HOME/.solar/harness}"
THUNDER_DIR="${THUNDER_DIR:-$HOME/ThunderOMLX}"
SOURCE_MODEL_DIR="${THUNDEROMLX_VLM_SOURCE_MODEL_DIR:-/Volumes/toshiba/models}"
MODEL_VIEW_DIR="${THUNDEROMLX_VLM_MODEL_VIEW_DIR:-$HARNESS_DIR/model-views/vlm-only}"
MODEL_DIR="${THUNDEROMLX_VLM_MODEL_DIR:-$MODEL_VIEW_DIR}"
SSD_CACHE_DIR="${THUNDEROMLX_VLM_SSD_CACHE_DIR:-/Volumes/RAID0-Main/omlx-cache/ssd-vlm}"
SSD_CACHE_MAX_SIZE="${THUNDEROMLX_VLM_SSD_CACHE_MAX_SIZE:-180GB}"
HOT_CACHE_MAX_SIZE="${THUNDEROMLX_VLM_HOT_CACHE_MAX_SIZE:-4GB}"
HOST="${THUNDEROMLX_VLM_HOST:-127.0.0.1}"
PORT="${THUNDEROMLX_VLM_PORT:-8003}"
SESSION="${THUNDEROMLX_VLM_TMUX_SESSION:-thunderomlx-vlm}"
LOG_FILE="${THUNDEROMLX_VLM_LOG_FILE:-$HARNESS_DIR/logs/thunderomlx-8003-vlm.log}"
TARGET_MODEL="${THUNDEROMLX_VLM_TARGET_MODEL:-gemma-4-31B}"

mkdir -p "$SSD_CACHE_DIR" "$HARNESS_DIR/logs" "$MODEL_DIR"
ln -sfn "$SOURCE_MODEL_DIR/$TARGET_MODEL" "$MODEL_DIR/$TARGET_MODEL"

target_ready() {
  python3 - "$HOST" "$PORT" "$TARGET_MODEL" <<'PY'
import json, sys, urllib.request
host, port, target = sys.argv[1], sys.argv[2], sys.argv[3]
base = f"http://{host}:{port}"
headers = {"x-api-key": "local-thunderomlx", "Authorization": "Bearer local-thunderomlx"}
try:
    req = urllib.request.Request(base + "/health", headers=headers)
    with urllib.request.urlopen(req, timeout=3) as resp:
        health = json.loads(resp.read().decode("utf-8", "replace"))
    if health.get("status") != "healthy":
        raise SystemExit(1)
    req = urllib.request.Request(base + "/v1/models", headers=headers)
    with urllib.request.urlopen(req, timeout=3) as resp:
        models = json.loads(resp.read().decode("utf-8", "replace"))
    ids = {item.get("id") for item in models.get("data") or []}
    if target not in ids:
        raise SystemExit(1)
except Exception:
    raise SystemExit(1)
PY
}

if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1 && ! target_ready; then
  echo "ThunderOMLX VLM $HOST:$PORT is not target ready; restarting listener." >&2
  lsof -tiTCP:"$PORT" -sTCP:LISTEN | xargs -r kill
  sleep 2
fi

if ! lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  tmux kill-session -t "$SESSION" 2>/dev/null || true
  tmux new-session -d -s "$SESSION" \
    "cd '$THUNDER_DIR' && exec ./venv/bin/omlx serve --model-dir '$MODEL_DIR' --host '$HOST' --port '$PORT' --max-model-memory 22GB --max-process-memory disabled --max-num-seqs 1 --completion-batch-size 1 --paged-ssd-cache-dir '$SSD_CACHE_DIR' --paged-ssd-cache-max-size '$SSD_CACHE_MAX_SIZE' --hot-cache-max-size '$HOT_CACHE_MAX_SIZE' 2>&1 | tee -a '$LOG_FILE'"
fi

for _ in $(seq 1 90); do
  if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1 && target_ready; then
    echo "ThunderOMLX VLM is ready on $HOST:$PORT model=$TARGET_MODEL." >&2
    exit 0
  fi
  sleep 2
done

tmux capture-pane -t "$SESSION" -p -S -120 2>/dev/null | tail -120 >&2 || true
echo "ThunderOMLX VLM did not become ready on $HOST:$PORT" >&2
exit 1
