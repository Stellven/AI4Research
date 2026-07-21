#!/bin/bash
# Hook: UserPromptSubmit — 检测 /next, 自动注入 dispatch.md
# 让协调器的 /next 短触发词自动读取并执行 dispatch 文件

SPRINTS_DIR="$HOME/.solar/harness/sprints"
LAST_SID_FILE="$HOME/.solar/harness/.next-last-sid"

# 读取用户输入
PROMPT=""
if [[ -n "$CLAUDE_USER_PROMPT" ]]; then
  PROMPT="$CLAUDE_USER_PROMPT"
elif [[ -n "$1" ]]; then
  PROMPT="$1"
fi

# 匹配 @next (不用 /next 避免被 Claude 当 skill 命令)
[[ "$PROMPT" != "@next" ]] && exit 0

# 找最新的 dispatch.md
DISPATCH=$(ls -t "$SPRINTS_DIR"/*.dispatch.md 2>/dev/null | head -1)
if [[ -z "$DISPATCH" ]]; then
  echo "⚠️ 无待处理 dispatch 文件"
  exit 0
fi

# 提取 sprint ID
SID=$(basename "$DISPATCH" .dispatch.md)

# 幂等检查: 如果已经处理过同一个 sprint 的 dispatch, 跳过
if [[ -f "$LAST_SID_FILE" ]]; then
  LAST_SID=$(cat "$LAST_SID_FILE" 2>/dev/null)
  if [[ "$LAST_SID" == "$SID" ]]; then
    # 同一个 dispatch, 可能是重复触发, 仍然注入但不重复标记
    :
  fi
fi

# 记录当前处理的 SID (幂等)
echo "$SID" > "$LAST_SID_FILE"

# 读取 dispatch 内容
CONTENT=$(cat "$DISPATCH")

# 直接输出 dispatch 内容作为上下文 (不用 intent 标签, 所有化身都能读)
cat << EOF
<system-reminder>
[Solar Harness 协调器派发 — $SID]
$(cat "$DISPATCH")
</system-reminder>
EOF
