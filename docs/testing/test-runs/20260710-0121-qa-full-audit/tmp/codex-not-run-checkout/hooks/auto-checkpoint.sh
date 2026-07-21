#!/bin/bash
# Solar Auto Checkpoint Hook
# 自动会话检查点 - 每30分钟触发一次

set -e

CHECKPOINT_FILE="$HOME/.solar/last-checkpoint"
CHECKPOINT_INTERVAL=1800  # 30分钟

# 检查是否到达检查点间隔
should_checkpoint() {
  if [ ! -f "$CHECKPOINT_FILE" ]; then
    return 0  # 首次运行，需要检查点
  fi

  local last_checkpoint=$(cat "$CHECKPOINT_FILE")
  local current_time=$(date +%s)
  local elapsed=$((current_time - last_checkpoint))

  if [ $elapsed -ge $CHECKPOINT_INTERVAL ]; then
    return 0  # 超过间隔，需要检查点
  else
    return 1  # 未到时间
  fi
}

# 执行检查点
if should_checkpoint; then
  echo "[Auto-Checkpoint] 触发自动会话检查点..."

  # 记录当前时间
  date +%s > "$CHECKPOINT_FILE"

  # 调用 save-session 保存会话状态
  if command -v bun &> /dev/null; then
    bun "$HOME/Solar/core/memory/save-session.ts" auto-checkpoint 2>/dev/null || true
  fi

  # 写入语义记忆
  sqlite3 "$HOME/.solar/solar.db" <<EOF
INSERT OR REPLACE INTO evo_memory_semantic (
  memory_id,
  namespace,
  key,
  value,
  source_type,
  confidence,
  created_at
) VALUES (
  'checkpoint_' || datetime('now'),
  'system/checkpoints',
  'last_auto_checkpoint',
  json_object('timestamp', datetime('now'), 'type', 'auto'),
  'system',
  1.0,
  datetime('now')
);
EOF

  echo "[Auto-Checkpoint] ✓ 完成"
fi
