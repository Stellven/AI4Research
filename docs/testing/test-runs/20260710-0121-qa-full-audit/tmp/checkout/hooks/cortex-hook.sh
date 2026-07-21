#!/bin/bash
# Solar Cortex Hook v2.0
# 将所有用户请求接入 Cortex 中枢神经系统
# 触发: UserPromptSubmit
#
# v2.0 改进:
# - 修复正则匹配（包含匹配，支持语气词）
# - 扩充口语词库
# - 纳入口令清单

INPUT=$(cat)
USER_PROMPT=$(echo "$INPUT" | jq -r '.user_prompt // ""' 2>/dev/null)
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // ""' 2>/dev/null)

# 如果没有用户提示，直接退出
[ -z "$USER_PROMPT" ] && exit 0

# 去除首尾空格，转小写便于匹配
PROMPT_TRIMMED=$(echo "$USER_PROMPT" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
PROMPT_LOWER=$(echo "$PROMPT_TRIMMED" | tr '[:upper:]' '[:lower:]')
PROMPT_LEN=${#PROMPT_TRIMMED}

# ========================================
# 异步记录到 Cortex (不阻塞主流程)
# ========================================
(
  cd ~/.claude/core/cortex 2>/dev/null
  bun -e "
    import Cortex from './cortex';
    const cortex = new Cortex();
    cortex.process('$PROMPT_TRIMMED', { session_id: '$SESSION_ID', source: 'hook' })
      .catch(() => {});
  " >/dev/null 2>&1
) &

# ========================================
# 口令清单 (高优先级，精确匹配)
# ========================================

# Solar 启动
if echo "$PROMPT_LOWER" | grep -qiE '^(solar|打开solar|加载solar|启动solar)$'; then
    echo '<cortex-intent type="solar_start" confidence="1.0">'
    echo 'Solar启动 → /ontology load + 启动宣告'
    echo '</cortex-intent>'
    exit 0
fi

# BIOS 批准
if echo "$PROMPT_LOWER" | grep -qiE '^(批准|approved|go)$'; then
    echo '<cortex-intent type="bios_approve" confidence="1.0">'
    echo 'BIOS批准 → 执行宣告中所有主动请求'
    echo '</cortex-intent>'
    exit 0
fi

# 模式切换
if echo "$PROMPT_TRIMMED" | grep -qiE '^我要(开发|办公|研究)'; then
    MODE=$(echo "$PROMPT_TRIMMED" | grep -oiE '开发|办公|研究')
    echo "<cortex-intent type=\"mode_switch\" mode=\"$MODE\" confidence=\"1.0\">"
    echo "模式切换 → $MODE 模式"
    echo '</cortex-intent>'
    exit 0
fi

# 展示请求
if echo "$PROMPT_TRIMMED" | grep -qiE '^(我要看|我想看|给我看|展示|显示)'; then
    echo '<cortex-intent type="display" confidence="0.95">'
    echo '展示请求 → TVS 渲染'
    echo '</cortex-intent>'
    exit 0
fi

# 模式清单
if echo "$PROMPT_LOWER" | grep -qiE '^模式清单$'; then
    echo '<cortex-intent type="list_modes" confidence="1.0">'
    echo '查看模式清单 → modes.md'
    echo '</cortex-intent>'
    exit 0
fi

# 人格切换
if echo "$PROMPT_LOWER" | grep -qiE '^(切a|切b|双人格)$'; then
    echo '<cortex-intent type="personality_switch" confidence="1.0">'
    echo '人格切换'
    echo '</cortex-intent>'
    exit 0
fi

# 大脑调度
if echo "$PROMPT_LOWER" | grep -qiE '^(省钱|用claude|用glm|用deepseek)'; then
    echo '<cortex-intent type="brain_switch" confidence="0.95">'
    echo '大脑调度切换'
    echo '</cortex-intent>'
    exit 0
fi

# 保存/休息
if echo "$PROMPT_LOWER" | grep -qiE '^(保存|休息|暂停|save|pause)'; then
    echo '<cortex-intent type="save" confidence="0.95">'
    echo '保存信号 → 中途宣告 + /save'
    echo '</cortex-intent>'
    exit 0
fi

# 归档
if echo "$PROMPT_LOWER" | grep -qiE '^(归档|archive)'; then
    echo '<cortex-intent type="archive" confidence="0.95">'
    echo '归档 → 文档化 + Backlog + Favorites'
    echo '</cortex-intent>'
    exit 0
fi

# ========================================
# 学习到的模式 (从数据库动态加载)
# ========================================
DB_PATH="$HOME/.solar/solar.db"
if [ -f "$DB_PATH" ]; then
    # 查询高置信度的学习模式
    LEARNED=$(sqlite3 "$DB_PATH" "
        SELECT pattern, intent_type, confidence
        FROM sys_intent_patterns
        WHERE usage_count >= 2 AND confidence >= 0.8
        ORDER BY usage_count DESC
        LIMIT 20
    " 2>/dev/null)

    if [ -n "$LEARNED" ]; then
        while IFS='|' read -r pattern intent conf; do
            # 精确匹配学习到的模式
            if [ "$PROMPT_LOWER" = "$pattern" ] || [ "$PROMPT_TRIMMED" = "$pattern" ]; then
                echo "<cortex-intent type=\"$intent\" confidence=\"$conf\" source=\"learned\">"
                echo "学习到的模式"
                echo '</cortex-intent>'
                exit 0
            fi
        done <<< "$LEARNED"
    fi
fi

# ========================================
# 确认信号 (包含匹配，支持语气词)
# ========================================
# 支持: 好、好的、好啊、可、可以、可以的、嗯、嗯嗯、行、行吧、对、对的、是、是的、OK、yes、y
if echo "$PROMPT_LOWER" | grep -qiE '^(好|可以?|嗯+|行|对|是|ok|yes|y|没问题|可以的|好的|好啊|行吧|对的|是的|确认|通过|批准|approved)(的|啊|吧|呢)?$'; then
    echo '<cortex-intent type="confirm" confidence="0.95">'
    echo '确认信号 → 执行待批准操作'
    echo '</cortex-intent>'
    exit 0
fi

# ========================================
# 否定信号 (包含匹配，支持语气词)
# ========================================
# 支持: 不、不行、不要、不对、错了、算了、取消、停、no、n
if echo "$PROMPT_LOWER" | grep -qiE '^(不|别|错|停|算了|取消|拒绝|no|n|不行|不要|不对|不是|错了|重来|不好)(了|啊|吧|呢)?$'; then
    echo '<cortex-intent type="reject" confidence="0.95">'
    echo '否定信号 → 停止当前操作'
    echo '</cortex-intent>'
    exit 0
fi

# ========================================
# 执行/继续信号 (口语化)
# ========================================
# 支持: 继续、做、干、搞、整、冲、开始、执行、下一步、go
if echo "$PROMPT_LOWER" | grep -qiE '^(继续|做|干|搞|整|冲|开始|执行|下一步|go|next|continue|fix|干活|开干|搞起|走起)(吧|啊|呗)?$'; then
    echo '<cortex-intent type="execute" confidence="0.9">'
    echo '执行信号 → 立即执行'
    echo '</cortex-intent>'
    exit 0
fi

# ========================================
# 查询信号
# ========================================
if echo "$PROMPT_TRIMMED" | grep -qiE '^(查|找|搜|看看|有没有|哪里|什么是)'; then
    echo '<cortex-intent type="query" confidence="0.85">'
    echo '查询信号 → 检索相关信息'
    echo '</cortex-intent>'
    exit 0
fi

# ========================================
# 短输入 (兜底) - 记录到 unknown 以便学习
# ========================================
if [ "$PROMPT_LEN" -le 10 ]; then
    # 写入未识别表，供后续学习
    sqlite3 "$DB_PATH" "
        INSERT INTO sys_intent_unknown (input, context)
        VALUES ('$PROMPT_LOWER', 'short_input')
    " 2>/dev/null

    echo '<cortex-intent type="short_input" confidence="0.7">'
    echo "短输入($PROMPT_LEN字) → 结合上下文理解"
    echo '</cortex-intent>'
    exit 0
fi

# 其他输入 - 记录到 unknown 以便学习
sqlite3 "$DB_PATH" "
    INSERT INTO sys_intent_unknown (input, context)
    VALUES ('$PROMPT_LOWER', 'unmatched')
" 2>/dev/null

exit 0
