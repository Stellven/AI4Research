#!/usr/bin/env bash
# remote-inbox-watcher.sh — PostToolUse hook: 轮询 mac mini outbox, 新事件写入本机 inbox
# 触发: 每次 tool use 后执行, ssh 读 mac mini outbox 末尾, 本地去重后通知

set -euo pipefail

STATE_DIR="$HOME/.solar/state"
INBOX="$STATE_DIR/remote-inbox.jsonl"
LAST_SEEN="$STATE_DIR/.remote-inbox-last-seen"
LOCK="$STATE_DIR/.remote-inbox.lock"
EXEC_MODE_FILE="$STATE_DIR/exec-mode.json"

# 只在远程模式激活时运行
if [[ ! -f "$EXEC_MODE_FILE" ]]; then exit 0; fi
MODE=$(jq -r '.mode // "local"' "$EXEC_MODE_FILE" 2>/dev/null || echo "local")
if [[ "$MODE" != "remote" ]]; then exit 0; fi

# 频率控制: 最多每 60s 轮询一次
if [[ -f "$LAST_SEEN" ]]; then
    LAST_TS=$(stat -f%m "$LAST_SEEN" 2>/dev/null || echo 0)
    NOW=$(date +%s)
    AGE=$(( NOW - LAST_TS ))
    if (( AGE < 60 )); then exit 0; fi
fi

# 避免并发
if [[ -f "$LOCK" ]]; then
    LOCK_AGE=$(($(date +%s) - $(stat -f%m "$LOCK" 2>/dev/null || echo 0)))
    if (( LOCK_AGE < 120 )); then exit 0; fi
    rm -f "$LOCK"
fi
touch "$LOCK"
trap 'rm -f "$LOCK"' EXIT

# 获取 mac mini host
NET_JSON=$("$HOME/.solar/bin/solar-net-detect" 2>/dev/null || echo '{}')
HOST=$(echo "$NET_JSON" | jq -r '.mac_mini_host // empty')
if [[ -z "$HOST" ]]; then exit 0; fi

# SSH 读 mac mini outbox 末尾
REMOTE_OUTBOX="$HOME/.solar/state/remote-outbox.jsonl"
LINES=$(ssh -o BatchMode=yes -o ConnectTimeout=5 "${SOLAR_REMOTE_USER:-solar}@${HOST}" \
    "tail -1 '$REMOTE_OUTBOX' 2>/dev/null" 2>/dev/null || true)

if [[ -z "$LINES" ]]; then
    touch "$LAST_SEEN"
    exit 0
fi

# 去重: 对比最后一条的 sprint_id + event
LAST_KEY=$(echo "$LINES" | jq -r '[.sprint_id, .event, .ts // .timestamp] | join("|")' 2>/dev/null || echo "")
if [[ -z "$LAST_KEY" ]]; then
    touch "$LAST_SEEN"
    exit 0
fi

if [[ -f "$INBOX" ]]; then
    LOCAL_LAST=$(tail -1 "$INBOX" | jq -r '[.sprint_id, .event, .ts // .timestamp] | join("|")' 2>/dev/null || echo "")
    if [[ "$LAST_KEY" == "$LOCAL_LAST" ]]; then
        touch "$LAST_SEEN"
        exit 0
    fi
fi

# 新事件 → 追加到本机 inbox
mkdir -p "$STATE_DIR"
echo "$LINES" >> "$INBOX"
touch "$LAST_SEEN"

# 桌面通知
SMSG=$(echo "$LINES" | jq -r '"\(.sprint_id // "?") \(.event // "?")"' 2>/dev/null || echo "remote event")
osascript -e "display notification \"${SMSG}\" with title \"Solar Remote\" sound name \"Glass\"" 2>/dev/null || true

# 输出标记供 Claude 读取
echo "<remote-notification>$LINES</remote-notification>"
