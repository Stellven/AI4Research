#!/bin/bash
# Solar Task Guard Hook
# 检测多步骤任务，提醒使用 TaskCreate 拆解并建立依赖
# 触发: UserPromptSubmit
# 性能目标: <5ms (纯 bash + grep，无外部依赖)

source "$(dirname "${BASH_SOURCE[0]}")/hook-logger.sh"
_START_MS=$(hook_time_ms)

INPUT=$(cat)
# Claude Code's UserPromptSubmit hook sends the prompt under `.prompt`; this
# hook read `.user_prompt` (nonexistent) and silently no-op'd on every prompt.
USER_PROMPT=$(echo "$INPUT" | sed -n 's/.*"prompt"[[:space:]]*:[[:space:]]*"\(.*\)"/\1/p' 2>/dev/null)

# 如果没有提取到用户提示，尝试 jq（备用，仅 macOS 自带）
if [ -z "$USER_PROMPT" ]; then
    USER_PROMPT=$(echo "$INPUT" | jq -r '.prompt // .user_prompt // ""' 2>/dev/null)
fi

[ -z "$USER_PROMPT" ] && exit 0

# 预处理
PROMPT_TRIMMED=$(echo "$USER_PROMPT" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')

# ── 快速排除 ──

# 消息太短，跳过
[ ${#PROMPT_TRIMMED} -lt 10 ] && exit 0

# 简单对话词，直接跳过
echo "$PROMPT_TRIMMED" | grep -qxiE '^(好|OK|可以|行|对|是的?|继续|谢谢|好的?|嗯|收到|明白|没问题|done|yes|yep|nah|no|谢谢|辛苦了|next|go)$' && exit 0

# ── 多步骤信号检测 ──

TRIGGERED=false

# 模式 1: "第X步" 组合（如 "第一步"、"第二步"、"第1步"）
if echo "$PROMPT_TRIMMED" | grep -qE '第[一二三四五六七八九十百千\d]+步'; then
    TRIGGERED=true
fi

# 模式 2: 数字序号序列 "1." 后跟 "2." 或 "1)" 后跟 "2)"
if [ "$TRIGGERED" = false ]; then
    if echo "$PROMPT_TRIMMED" | grep -qE '[1][\.\)]' && echo "$PROMPT_TRIMMED" | grep -qE '[2][\.\)]'; then
        TRIGGERED=true
    fi
fi

# 模式 3: 序列连接词 + 动词（"然后"/"之后"/"接着"/"最后" 后跟动作词）
if [ "$TRIGGERED" = false ]; then
    if echo "$PROMPT_TRIMMED" | grep -qE '(然后|之后|接着|最后|随后|继而|下一步|完成后再)[[:space:]]*(实现|开发|搭建|部署|写|创建|配置|测试|运行|构建|安装|修改|更新)'; then
        TRIGGERED=true
    fi
fi

# 模式 4: 多个动作动词在同一句中（隐含多步）
# "先X再Y" / "X然后Y" / "先X后Y"
if [ "$TRIGGERED" = false ]; then
    if echo "$PROMPT_TRIMMED" | grep -qE '先.{1,10}(再|然后|接着|后).{1,10}'; then
        TRIGGERED=true
    fi
fi

# 模式 5: 复合任务动词 + "然后" / "之后" / "接着"（弱信号，但动词强时有效）
if [ "$TRIGGERED" = false ]; then
    if echo "$PROMPT_TRIMMED" | grep -qE '(实现|开发|搭建|部署|完成|构建).{1,6}(然后|之后|接着|最后|还要|再)'; then
        TRIGGERED=true
    fi
fi

# ── 输出提醒 ──

if [ "$TRIGGERED" = true ]; then
    cat << 'REMINDER'
<task-create-reminder>
检测到可能的多步骤任务。请使用 TaskCreate 拆解并建立依赖关系 (addBlockedBy)。
参考: rules/task-create-protocol.md
</task-create-reminder>
REMINDER
    hook_log "UserPromptSubmit" "task-guard" "ok" "$(( $(hook_time_ms) - _START_MS ))" "triggered=yes"
else
    hook_log "UserPromptSubmit" "task-guard" "skip" "$(( $(hook_time_ms) - _START_MS ))" "triggered=no"
fi

exit 0
