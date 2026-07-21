#!/usr/bin/env bash
set -euo pipefail

HARNESS_DIR="${HARNESS_DIR:-$HOME/.solar/harness}"
THUNDER_DIR="${THUNDER_DIR:-$HOME/ThunderOMLX}"
SOURCE_MODEL_DIR="${THUNDEROMLX_SOURCE_MODEL_DIR:-/Volumes/toshiba/models}"
MODEL_VIEW_DIR="${THUNDEROMLX_MODEL_VIEW_DIR:-$HARNESS_DIR/model-views/qwen-only}"
MODEL_DIR="${THUNDEROMLX_MODEL_DIR:-$MODEL_VIEW_DIR}"
SSD_CACHE_DIR="${THUNDEROMLX_SSD_CACHE_DIR:-/Volumes/RAID0-Main/omlx-cache/ssd-qwen36}"
SSD_CACHE_MAX_SIZE="${THUNDEROMLX_SSD_CACHE_MAX_SIZE:-460GB}"
HOT_CACHE_MAX_SIZE="${THUNDEROMLX_HOT_CACHE_MAX_SIZE:-8GB}"
INITIAL_CACHE_BLOCKS="${THUNDEROMLX_INITIAL_CACHE_BLOCKS:-256}"
HOST="${THUNDEROMLX_HOST:-127.0.0.1}"
PORT="${THUNDEROMLX_PORT:-8002}"
SESSION="${THUNDEROMLX_TMUX_SESSION:-thunderomlx-qwen36}"
LOG_FILE="${THUNDEROMLX_LOG_FILE:-$HARNESS_DIR/logs/thunderomlx-8002.log}"
AUTO_PREWARM="${THUNDEROMLX_AUTO_PREWARM:-0}"
PREWARM_IDLE_MINUTES="${THUNDEROMLX_PREWARM_IDLE_MINUTES:-5}"
TARGET_MODEL="${THUNDEROMLX_TARGET_MODEL:-Qwen3.6-35b-a3b}"

mkdir -p "$SSD_CACHE_DIR" "$HARNESS_DIR/logs" "$MODEL_DIR"

ln -sfn "$SOURCE_MODEL_DIR/Qwen3.6-35b-a3b" "$MODEL_DIR/Qwen3.6-35b-a3b"
ln -sfn "$SOURCE_MODEL_DIR/Qwen3.6-35B-A3B-DFlash" "$MODEL_DIR/Qwen3.6-35B-A3B-DFlash"

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
    loaded = [
        item.get("id")
        for item in ((health.get("engine_pool") or {}).get("models") or [])
        if item.get("loaded")
    ]
    bad_loaded = [item for item in loaded if item not in {target, "Qwen3.6-35B-A3B-DFlash"}]
    if bad_loaded:
        raise SystemExit(1)
except Exception:
    raise SystemExit(1)
PY
}

if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1 && ! target_ready; then
  echo "ThunderOMLX $HOST:$PORT is not Qwen-only ready; restarting listener." >&2
  lsof -tiTCP:"$PORT" -sTCP:LISTEN | xargs -r kill
  sleep 2
fi

if ! lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  tmux kill-session -t "$SESSION" 2>/dev/null || true
  tmux new-session -d -s "$SESSION" \
    "cd '$THUNDER_DIR' && exec ./venv/bin/omlx serve --serve-profile knowledge-batch --model-dir '$MODEL_DIR' --host '$HOST' --port '$PORT' --max-model-memory 35GB --max-process-memory disabled --max-num-seqs 1 --completion-batch-size 1 --paged-ssd-cache-dir '$SSD_CACHE_DIR' --paged-ssd-cache-max-size '$SSD_CACHE_MAX_SIZE' --hot-cache-max-size '$HOT_CACHE_MAX_SIZE' --initial-cache-blocks '$INITIAL_CACHE_BLOCKS' 2>&1 | tee -a '$LOG_FILE'"
fi

for _ in $(seq 1 90); do
  if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1 && target_ready; then
    if [[ "$AUTO_PREWARM" == "1" || "$AUTO_PREWARM" == "true" ]]; then
      if ! python3 "$HARNESS_DIR/scripts/thunderomlx_auto_prewarm.py" --idle-minutes "$PREWARM_IDLE_MINUTES"; then
        echo "WARN: ThunderOMLX is listening on $HOST:$PORT but auto prewarm failed; continuing." >&2
      fi
    else
      echo "ThunderOMLX Qwen-only is ready on $HOST:$PORT; auto prewarm disabled (THUNDEROMLX_AUTO_PREWARM=$AUTO_PREWARM)." >&2
    fi
    exit 0
  fi
  sleep 2
done

tmux capture-pane -t "$SESSION" -p -S -120 2>/dev/null | tail -120 >&2 || true
echo "ThunderOMLX did not listen on $HOST:$PORT" >&2
exit 1
