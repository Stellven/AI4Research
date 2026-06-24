#!/bin/bash
# Solar Session End Hook
# 会话结束前强制保存

set -e

SESSION_ID="${CLAUDE_SESSION_ID:-unknown}"
PROJECT_DIR="${PWD}"

echo "[SessionEnd] 会话即将结束，保存状态..."

# 1. 保存当前会话状态
if [ -f "$HOME/Solar/core/memory/save-session.ts" ]; then
  bun "$HOME/Solar/core/memory/save-session.ts" session-end 2>/dev/null || true
fi

# 2. 检查是否有未文档化的重要讨论
# 通过检测关键词来判断
if [ -f "$HOME/.solar/db/solar.db" ]; then
  SESSION_ID="$SESSION_ID" PROJECT_DIR="$PROJECT_DIR" python3 - <<'PY' || true
import json
import os
import sqlite3
from pathlib import Path

db = Path.home() / ".solar" / "db" / "solar.db"
session_id = os.environ.get("SESSION_ID") or "unknown"
project_dir = os.environ.get("PROJECT_DIR") or ""
memory_id = f"session_end_{session_id}"
payload = {
    "session_id": session_id,
    "project_dir": project_dir,
    "timestamp": None,
    "saved": 1,
}

conn = sqlite3.connect(str(db), timeout=5)
conn.execute(
    """
    INSERT OR REPLACE INTO evo_memory_semantic (
      memory_id, namespace, key, value, source_type, confidence
    ) VALUES (
      ?, 'system/sessions', ?, json_set(?, '$.timestamp', datetime('now')), 'system', 1.0
    )
    """,
    (memory_id, memory_id, json.dumps(payload, ensure_ascii=False)),
)
conn.commit()
conn.close()
PY
fi

# 3. 自动 git checkpoint (WIP commit)
# Disabled by default: this used git add -A on SessionEnd and could sweep
# unrelated in-progress work into unsolicited WIP commits.
auto_git_checkpoint() {
  if [ "${SOLAR_SESSION_END_GIT_CHECKPOINT:-0}" != "1" ]; then
    echo "[SessionEnd] Git checkpoint disabled (set SOLAR_SESSION_END_GIT_CHECKPOINT=1 to opt in)"
    return
  fi

  # 检查是否在 git 仓库中
  if ! git rev-parse --is-inside-work-tree &>/dev/null; then
    return
  fi

  # 检查是否有未提交的变更
  if git status --short | grep -q '^'; then
    local timestamp=$(date +"%Y-%m-%d %H:%M")
    local branch=$(git branch --show-current 2>/dev/null || echo "unknown")

    # Stage all changes
    git add -A

    # Commit with WIP message
    git commit -m "WIP: checkpoint @ $timestamp [$branch]

Auto-checkpoint by Solar SessionEnd hook.
Session: ${SESSION_ID}" --no-verify 2>/dev/null || true

    echo "[SessionEnd] ✅ Git checkpoint 已创建"
  else
    echo "[SessionEnd] Git 无需 checkpoint (无变更)"
  fi
}

# 执行自动 checkpoint
auto_git_checkpoint

echo "[SessionEnd] ✓ 会话状态已保存"
