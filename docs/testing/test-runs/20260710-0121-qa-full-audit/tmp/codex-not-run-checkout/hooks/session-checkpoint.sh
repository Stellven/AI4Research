#!/bin/bash
# Session Checkpoint Hook
# 自动保存会话状态，用于快速恢复

CHECKPOINT_DIR=".solar"
CHECKPOINT_FILE="$CHECKPOINT_DIR/session.md"
HISTORY_DIR="$CHECKPOINT_DIR/history"

# 确保目录存在
mkdir -p "$CHECKPOINT_DIR" "$HISTORY_DIR"

# 获取当前时间戳
TIMESTAMP=$(date +"%Y-%m-%d %H:%M:%S")
BACKUP_FILE="$HISTORY_DIR/session_$(date +%Y%m%d_%H%M%S).md"

# 备份上一次的状态
if [[ -f "$CHECKPOINT_FILE" ]]; then
    cp "$CHECKPOINT_FILE" "$BACKUP_FILE"
    # 只保留最近 10 个备份
    ls -t "$HISTORY_DIR"/session_*.md 2>/dev/null | tail -n +11 | xargs rm -f 2>/dev/null
fi

# 收集状态信息
GIT_BRANCH=$(git branch --show-current 2>/dev/null || echo "unknown")
GIT_STATUS=$(git status --short 2>/dev/null | head -20)
GIT_RECENT=$(git log --oneline -5 2>/dev/null)
RECENT_FILES=$(git diff --name-only HEAD~3 2>/dev/null | head -10)

# 读取现有 TODO（如果存在）
TODOS=""
if [[ -f ".solar/todos.md" ]]; then
    TODOS=$(cat ".solar/todos.md")
fi

# 生成检查点文件
cat > "$CHECKPOINT_FILE" << CHECKPOINT
# Solar Session Checkpoint

> 自动生成于: $TIMESTAMP
> 使用 \`/resume\` 快速恢复此会话

## 项目状态

- **分支**: $GIT_BRANCH
- **工作目录**: $(pwd)

## 最近提交

\`\`\`
$GIT_RECENT
\`\`\`

## 未提交变更

\`\`\`
$GIT_STATUS
\`\`\`

## 最近修改文件

\`\`\`
$RECENT_FILES
\`\`\`

## 待办事项

$TODOS

## 会话摘要

<!-- 由 Claude 自动更新 -->
_等待更新..._

---
*此文件由 Solar session-checkpoint hook 自动生成*
CHECKPOINT

echo "✓ Session checkpoint saved: $CHECKPOINT_FILE"
