#!/bin/bash
# REE First Hook - 在处理请求前检查是否有匹配的资源
# 位置: UserPromptSubmit
# 目的: 在 Claude 生成代码前，先检查 REE 是否有现成资源
# FIX v1.1: 使用 stdin JSON 格式获取用户输入

set -euo pipefail

# 从 stdin 读取 JSON 格式输入
INPUT=$(cat)
USER_INPUT=$(echo "$INPUT" | jq -r '.user_prompt // ""' 2>/dev/null)

# 如果没有输入，直接退出
[ -z "$USER_INPUT" ] && exit 0

# 快速判断：是否可能需要代码/脚本
needs_code_check() {
  local input="$1"
  # 关键词判断
  echo "$input" | grep -qiE "(查询|获取|抓取|生成|创建|运行|执行|监控|fetch|get|create|run|build|weather|天气|HN|新闻|PPT|待办|backlog)" && return 0
  return 1
}

# 如果不需要代码，直接放行
if ! needs_code_check "$USER_INPUT"; then
  exit 0
fi

# 调用 REE 匹配
MATCH_RESULT=$(cd ~/.claude/core/ree && bun tiered-router.ts route "$USER_INPUT" 2>/dev/null || echo "")

# 解析结果 (格式: "  Type: script")
if echo "$MATCH_RESULT" | grep -q "Type:"; then
  RESOURCE_TYPE=$(echo "$MATCH_RESULT" | grep "Type:" | sed 's/.*Type: *//')
  RESOURCE_NAME=$(echo "$MATCH_RESULT" | grep "ID:" | sed 's/.*ID: *//')
  MATCH_SCORE=$(echo "$MATCH_RESULT" | grep "Score:" | sed 's/.*Score: *//' | sed 's/%//')
  EXEC_CMD=$(echo "$MATCH_RESULT" | grep "Cmd:" | sed 's/.*Cmd: *//')
  LAYER=$(echo "$MATCH_RESULT" | grep "Layer:" | sed 's/.*Layer: *//')

  if [ -n "$RESOURCE_TYPE" ] && [ "$RESOURCE_TYPE" != "none" ] && [ "$RESOURCE_TYPE" != "" ]; then
    # 清理变量中的空白
    RESOURCE_TYPE=$(echo "$RESOURCE_TYPE" | tr -d '\n' | xargs)
    RESOURCE_NAME=$(echo "$RESOURCE_NAME" | tr -d '\n' | xargs)
    MATCH_SCORE=$(echo "$MATCH_SCORE" | tr -d '\n' | xargs)
    EXEC_CMD=$(echo "$EXEC_CMD" | tr -d '\n' | xargs)
    LAYER=$(echo "$LAYER" | tr -d '\n' | xargs)

    # 输出提醒
    cat << EOF

┌─────────────────────────────────────────────────────────────────┐
│  🔧 REE 匹配提醒                                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  发现匹配资源，建议复用:                                        │
│                                                                 │
│  类型: $RESOURCE_TYPE
│  名称: $RESOURCE_NAME
│  匹配层: $LAYER
│  置信度: ${MATCH_SCORE}%
│                                                                 │
│  执行命令:                                                      │
│  $EXEC_CMD
│                                                                 │
│  💡 请优先使用此资源，避免重复生成代码                          │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

EOF

    # 记录到数据库
    SCORE_NUM=$(echo "$MATCH_SCORE" | grep -oE '[0-9]+' | head -1)
    sqlite3 ~/.solar/solar.db "
      INSERT INTO sys_ree_hints (user_input, matched_type, matched_name, score, layer, created_at)
      VALUES ('$(echo "$USER_INPUT" | sed "s/'/''/g")', '$RESOURCE_TYPE', '$RESOURCE_NAME', ${SCORE_NUM:-0}, '$LAYER', datetime('now'))
    " 2>/dev/null || true
  fi
fi

exit 0
