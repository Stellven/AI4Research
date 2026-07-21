#!/bin/bash
# Solar Self Model - SessionStart Hook
# 会话开始时加载：身份 + 人格 + 铁律 + 状态 + 外部依赖检查

DB_FILE="$HOME/.solar/solar.db"
STATE_FILE="$PWD/.solar/flow-state.json"
CHECKPOINT_FILE="$HOME/.solar/checkpoint.md"
STARTUP_CHECK="$HOME/Solar/core/bootstrap/startup-check.sh"
CORE_LAWS_FILE="$HOME/.claude/rules/00-core-laws.md"

# ==================== 0. 加载核心铁律 (L0 长期记忆) ====================
CORE_LAWS=""
if [[ -f "$CORE_LAWS_FILE" ]]; then
    # 读取核心铁律文件（去掉 markdown 标题行，保留内容）
    CORE_LAWS=$(cat "$CORE_LAWS_FILE" | head -100)
    CORE_LAWS="【📜 核心铁律已加载】\\n$CORE_LAWS\\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\\n"
fi

# ==================== 1. 注入主脑人格 (战略家+治理官双签) ====================
PERSONA_INJECT=""
PERSONA_OUTPUT=$(bun ~/.claude/core/solar-farm/master-brain-persona.ts inject 2>/dev/null)
if [[ -n "$PERSONA_OUTPUT" ]]; then
    PERSONA_INJECT="【🎭 战略家+治理官双签人格已注入】\\n"
    PERSONA_INJECT+="$PERSONA_OUTPUT\\n"
    PERSONA_INJECT+="━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\\n"
fi

# ==================== 1. 加载自我模型 ====================
SELF_MODEL=""
if [[ -f "$DB_FILE" ]]; then
    # 从数据库加载启动上下文
    STARTUP=$(sqlite3 "$DB_FILE" "SELECT * FROM v_startup_context;" 2>/dev/null)

    if [[ -n "$STARTUP" ]]; then
        # 解析返回的数据 (格式: core_rules|personality|key_learnings|rule_index)
        IFS='|' read -r RULES PERSONALITY LEARNINGS INDEX <<< "$STARTUP"

        # 提取人格名称
        PERSONA_NAME=$(echo "$PERSONALITY" | python3 -c "import sys,json; d=json.loads(sys.stdin.read() or '{}'); print(d.get('name','Solar'))" 2>/dev/null)
        PERSONA_PROMPT=$(echo "$PERSONALITY" | python3 -c "import sys,json; d=json.loads(sys.stdin.read() or '{}'); print(d.get('prompt',''))" 2>/dev/null)

        # 提取核心铁律
        CORE_RULES=$(echo "$RULES" | python3 -c "
import sys,json
rules = json.loads(sys.stdin.read() or '[]')
for r in rules:
    print(f\"• {r['name']}: {r['rule']}\")
" 2>/dev/null)

        SELF_MODEL="【Solar 自我模型已加载】\\n"
        SELF_MODEL+="人格: $PERSONA_NAME\\n"
        SELF_MODEL+="━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\\n"
        SELF_MODEL+="核心铁律:\\n$CORE_RULES\\n"
        SELF_MODEL+="━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\\n"
        if [[ -n "$PERSONA_PROMPT" ]]; then
            SELF_MODEL+="$PERSONA_PROMPT\\n"
        fi
    fi
fi

# ==================== 2. 读取 Checkpoint ====================
# 读取 checkpoint (如果存在)
CHECKPOINT_MSG=""
if [[ -f "$CHECKPOINT_FILE" ]]; then
    # 提取关键信息
    LAST_UPDATE=$(grep "上次更新:" "$CHECKPOINT_FILE" | head -1 | sed 's/.*上次更新: //')
    TASK_LINE=$(grep "任务" "$CHECKPOINT_FILE" | head -1)
    PENDING=$(grep -A10 "## 待完成" "$CHECKPOINT_FILE" | grep "^\- \[ \]" | head -3)
    REMINDER=$(grep -A5 "监护人提醒" "$CHECKPOINT_FILE" | grep "^[0-9]\." | head -2)

    if [[ -n "$LAST_UPDATE" ]]; then
        CHECKPOINT_MSG="【Checkpoint 恢复】上次: $LAST_UPDATE\\n"
        if [[ -n "$PENDING" ]]; then
            CHECKPOINT_MSG+="待完成:\\n$(echo "$PENDING" | sed 's/^/  /')\\n"
        fi
        CHECKPOINT_MSG+="详情: cat ~/.solar/checkpoint.md"
    fi
fi

# ==================== 3. 读取流程状态 (可选) ====================
PHASE=""
AGENT=""
TASK=""

if [[ -f "$STATE_FILE" ]]; then
    ACTIVE=$(jq -r '.active // false' "$STATE_FILE" 2>/dev/null)
    if [[ "$ACTIVE" == "true" ]]; then
        PHASE=$(jq -r '.flow.current_phase // ""' "$STATE_FILE")
        AGENT=$(jq -r '.flow.current_agent // ""' "$STATE_FILE")
        TASK=$(jq -r '.task.description // ""' "$STATE_FILE")
    fi
fi

# ==================== 3.5 读取 STATE.md (作战态势) ====================
GLOBAL_STATE_FILE="$HOME/.solar/STATE.md"
STATE_MD_MSG=""
if [[ -f "$GLOBAL_STATE_FILE" ]]; then
    # 提取关键信息
    MISSION=$(grep -A1 "^# Mission" "$GLOBAL_STATE_FILE" | tail -1 | head -c 100)
    IN_PROGRESS=$(grep "^- In-Progress:" "$GLOBAL_STATE_FILE" | sed 's/- In-Progress: //' | head -c 80)
    DONE_ITEMS=$(grep "^  - " "$GLOBAL_STATE_FILE" | head -5)
    NEXT_ACTIONS=$(grep "^- \[ \]" "$GLOBAL_STATE_FILE" | head -3)
    LAST_UPDATE=$(grep "Last updated:" "$GLOBAL_STATE_FILE" | sed 's/.*Last updated: //' | head -c 25)

    if [[ -n "$MISSION" ]]; then
        STATE_MD_MSG="【📋 作战态势 (STATE.md)】\\n"
        STATE_MD_MSG+="Mission: $MISSION\\n"
        if [[ -n "$DONE_ITEMS" ]]; then
            STATE_MD_MSG+="Done:\\n$(echo "$DONE_ITEMS" | sed 's/^/  /')\\n"
        fi
        if [[ -n "$IN_PROGRESS" && "$IN_PROGRESS" != "无" ]]; then
            STATE_MD_MSG+="进行中: $IN_PROGRESS\\n"
        fi
        if [[ -n "$NEXT_ACTIONS" ]]; then
            STATE_MD_MSG+="下一步:\\n$(echo "$NEXT_ACTIONS" | sed 's/^/  /')\\n"
        fi
        if [[ -n "$LAST_UPDATE" ]]; then
            STATE_MD_MSG+="更新: $LAST_UPDATE\\n"
        fi
        STATE_MD_MSG+="━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\\n"
    fi
fi

# 获取 Agent emoji
get_emoji() {
    case "$1" in
        "Researcher") echo "🔬" ;;
        "Architect") echo "🏗️" ;;
        "Coder") echo "💻" ;;
        "Tester") echo "🧪" ;;
        "Reviewer") echo "👁️" ;;
        "Docs") echo "📖" ;;
        "Ops") echo "⚙️" ;;
        "PM") echo "📊" ;;
        *) echo "🤖" ;;
    esac
}

EMOJI=$(get_emoji "$AGENT")

# 构建完整消息
MESSAGE=""

# 0. 核心铁律 (L0 长期记忆，最重要)
if [[ -n "$CORE_LAWS" ]]; then
    MESSAGE+="$CORE_LAWS\\n"
fi

# 1. 主脑人格注入
if [[ -n "$PERSONA_INJECT" ]]; then
    MESSAGE+="$PERSONA_INJECT\\n"
fi

# 2. 自我模型
if [[ -n "$SELF_MODEL" ]]; then
    MESSAGE+="$SELF_MODEL\\n"
fi

# 2. 流程状态 (如果有)
if [[ -n "$TASK" && "$TASK" != "unknown" ]]; then
    MESSAGE+="【当前任务】\\n"
    MESSAGE+="任务: $TASK\\n"
    MESSAGE+="阶段: $PHASE | Agent: $EMOJI $AGENT\\n"
    MESSAGE+="━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\\n"
fi

# 2.5 STATE.md 作战态势
if [[ -n "$STATE_MD_MSG" ]]; then
    MESSAGE+="$STATE_MD_MSG\\n"
fi

# 3. Checkpoint (如果有)
if [[ -n "$CHECKPOINT_MSG" ]]; then
    MESSAGE+="$CHECKPOINT_MSG\\n"
fi

# ==================== 4. 外部依赖检查 ====================
DEPS_MSG=""
if [[ -x "$STARTUP_CHECK" ]]; then
    DEPS_OUTPUT=$("$STARTUP_CHECK" 2>/dev/null)
    if [[ -n "$DEPS_OUTPUT" ]]; then
        DEPS_MSG="$DEPS_OUTPUT\\n"
    fi
fi

# 4. 外部依赖状态 (如果有需要处理的)
if [[ -n "$DEPS_MSG" ]]; then
    MESSAGE+="$DEPS_MSG"
fi

# ==================== 5. 加载行为纹理 (首层) ====================
TEXTURE_MSG=""
TEXTURE_COUNT=0
if [[ -x "$HOME/.claude/hooks/texture-inject.sh" ]]; then
    TEXTURE_OUTPUT=$("$HOME/.claude/hooks/texture-inject.sh" head 2>/dev/null)
    if [[ -n "$TEXTURE_OUTPUT" ]]; then
        TEXTURE_MSG="$TEXTURE_OUTPUT\\n"
    fi
    # 统计纹理数量
    TEXTURE_COUNT=$(sqlite3 "$DB_FILE" "SELECT COUNT(*) FROM behavior_textures" 2>/dev/null || echo "0")
fi

# 检查中层和尾层 hook 是否激活
MID_REFRESH_ACTIVE="❌"
TAIL_TEXTURE_ACTIVE="❌"
if [[ -x "$HOME/.claude/hooks/mid-refresh.sh" ]]; then
    MID_REFRESH_ACTIVE="✅"
fi
if [[ -x "$HOME/.claude/hooks/identity-reminder.sh" ]]; then
    TAIL_TEXTURE_ACTIVE="✅"
fi

# 输出纹理状态面板
MESSAGE+="━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\\n"
MESSAGE+="【🧵 三层纹理穿插机制】\\n"
MESSAGE+="┌─────────────────────────────────────┐\\n"
MESSAGE+="│ 首层(SessionStart): ✅ 人格+法则     │\\n"
MESSAGE+="│ 中层(每3轮刷新):    $MID_REFRESH_ACTIVE 防挤出机制     │\\n"
MESSAGE+="│ 尾层(每轮结尾):     $TAIL_TEXTURE_ACTIVE Recency Bias  │\\n"
MESSAGE+="│ 纹理样本数:         ${TEXTURE_COUNT}条              │\\n"
MESSAGE+="└─────────────────────────────────────┘\\n"

if [[ -n "$TEXTURE_MSG" ]]; then
    MESSAGE+="$TEXTURE_MSG"
fi

# ==================== 6. 加载相关记忆 (Memory Hook) ====================
MEMORY_MSG=""
# 获取项目上下文 (当前目录名)
PROJECT_CONTEXT=$(basename "$PWD")
MEMORY_OUTPUT=$(bun ~/.claude/core/memory/memory-hook.ts load "$PROJECT_CONTEXT" 2>/dev/null)
if [[ -n "$MEMORY_OUTPUT" && "$MEMORY_OUTPUT" != *"用法:"* ]]; then
    MEMORY_MSG="$MEMORY_OUTPUT\\n"
fi

if [[ -n "$MEMORY_MSG" ]]; then
    MESSAGE+="━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\\n"
    MESSAGE+="$MEMORY_MSG"
fi

# 如果什么都没有，至少输出自我模型
if [[ -z "$MESSAGE" ]]; then
    MESSAGE="Solar 已就绪"
fi

# ==================== 7. CronCreate 建议 (会话内定时自检) ====================
MESSAGE+="━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\\n"
MESSAGE+="【⏰ 定时自检建议】\\n"
MESSAGE+="建议: 使用 CronCreate 创建每 30 分钟自检 (cron: */30 * * * *)\\n"
MESSAGE+="用途: 读取 STATE.md 检查 In-Progress 是否需要更新\\n"

# 使用正确的 Claude Code 钩子格式
jq -n --arg ctx "$MESSAGE" '{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": $ctx
  }
}'
