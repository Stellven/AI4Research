#!/bin/bash
# Solar Unified Intent Engine v2.0
# 统一意图路由: Solar 信号 > @Agent
# 触发: UserPromptSubmit
# 性能目标: <10ms (纯 shell regex，无 bun/TypeScript 调用)

source "$(dirname "${BASH_SOURCE[0]}")/hook-logger.sh"
_START_MS=$(hook_time_ms)

INPUT=$(cat)
USER_PROMPT=$(echo "$INPUT" | jq -r '.user_prompt // ""' 2>/dev/null)

# 如果没有用户提示，直接退出
[ -z "$USER_PROMPT" ] && exit 0

# 预处理: 去除首尾空格，生成小写版本
PROMPT_TRIMMED=$(echo "$USER_PROMPT" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
PROMPT_LOWER=$(echo "$PROMPT_TRIMMED" | tr '[:upper:]' '[:lower:]')

# 数据库路径
DB_PATH="$HOME/.solar/db/solar.db"

# ========================================
# Phase 1: Solar 信号 (直接输出指令，无确认)
# ========================================

# 1a. 确认词检测 + 异步反馈记录 (sqlite3 直接写入)
if echo "$PROMPT_TRIMMED" | grep -qxiE '好|可|可以|OK|确认|通过|不错|行|对|是的?|批准|approved|go|yes|y'; then
    # 异步记录反馈到 evo_feedback_v2 (不阻塞主流程)
    (
        sqlite3 "$DB_PATH" "INSERT OR IGNORE INTO evo_feedback_v2 (input, signal_type, source, created_at) VALUES ($(printf "'%s'" "$PROMPT_TRIMMED" | sed "s/'/''/g"), 'explicit_positive', 'intent_engine', datetime('now'));" 2>/dev/null
    ) &
    echo '<intent-detected type="confirm" confidence="0.95">'
    echo '用户输入为确认/批准信号。'
    echo '如果有待批准的操作或主动请求，应立即执行。'
    echo '如果是 Solar 启动后的批准，执行宣告中的所有主动请求。'
    echo '</intent-detected>'
    exit 0
fi

# 1b. 否定词检测 + 异步反馈记录
if echo "$PROMPT_TRIMMED" | grep -qxiE '不对|错了|重来|不行|不是|错误|问题|不好|差|糟糕|N|No|否|取消|拒绝|停|算了'; then
    (
        sqlite3 "$DB_PATH" "INSERT OR IGNORE INTO evo_feedback_v2 (input, signal_type, source, created_at) VALUES ($(printf "'%s'" "$PROMPT_TRIMMED" | sed "s/'/''/g"), 'explicit_negative', 'intent_engine', datetime('now'));" 2>/dev/null
    ) &
    echo '<intent-detected type="reject" confidence="0.95">'
    echo '用户输入为否定/纠正信号。'
    echo '应停止当前操作，询问用户期望的行为。'
    echo '</intent-detected>'
    exit 0
fi

# 1c. 保存/休息检测 - 触发中途宣告
if echo "$PROMPT_TRIMMED" | grep -qiE '^(保存|休息|我先走|暂停|save|pause)'; then
    echo '<intent-detected type="save" confidence="0.9">'
    echo '用户希望保存状态或暂停。应输出中途宣告并执行 /save。'
    echo '</intent-detected>'
    exit 0
fi

# 1d. 执行/继续检测 + 隐式正向反馈 (子串匹配，非整词)
if echo "$PROMPT_TRIMMED" | grep -qiE '修复|继续|开始执行|执行|fix|continue|开始|下一步|接着|next'; then
    (
        sqlite3 "$DB_PATH" "INSERT OR IGNORE INTO evo_feedback_v2 (input, signal_type, source, created_at) VALUES ($(printf "'%s'" "$PROMPT_TRIMMED" | sed "s/'/''/g"), 'implicit_positive', 'intent_engine', datetime('now'));" 2>/dev/null
    ) &
    echo '<intent-detected type="execute" confidence="0.9">'
    echo '用户希望执行上一个提议的操作。应立即开始执行，无需再次确认。'
    echo '</intent-detected>'
    exit 0
fi

# 1e. Solar 启动检测
if echo "$PROMPT_TRIMMED" | grep -qiE '^(solar|打开solar|加载solar|启动solar)$'; then
    echo '<intent-detected type="solar_start" confidence="1.0">'
    echo '用户触发 Solar 启动。必须执行 /ontology load 并显示启动宣告。'
    echo '</intent-detected>'
    exit 0
fi

# 1f. Solar-Max 项目模式检测
if echo "$PROMPT_TRIMMED" | grep -qiE '^solar-max$'; then
    echo '<intent-detected type="solar_max" confidence="1.0">'
    echo '用户触发 Solar-MAX 项目模式。切换工作目录到 ~/Solar-MAX，装载项目状态和规则。'
    echo '</intent-detected>'
    exit 0
fi

# 1g. 开发模式检测
if echo "$PROMPT_TRIMMED" | grep -qiE '^我要开发'; then
    PROJECT=$(echo "$PROMPT_TRIMMED" | sed 's/^我要开发[[:space:]]*//')
    if [ -n "$PROJECT" ] && [ "$PROJECT" != "我要开发" ]; then
        echo "<intent-detected type=\"dev_mode\" project=\"$PROJECT\" confidence=\"0.95\">"
        echo "用户希望开发项目: $PROJECT"
        echo '按项目装载流程执行：识别路径 -> 装载状态 -> 显示横幅 -> 恢复上下文'
        echo '</intent-detected>'
    else
        echo '<intent-detected type="dev_mode" confidence="0.9">'
        echo '用户希望进入开发模式。显示项目选择或询问要开发什么。'
        echo '</intent-detected>'
    fi
    exit 0
fi

# 1h. 办公模式检测
if echo "$PROMPT_TRIMMED" | grep -qiE '^我要办公'; then
    echo '<intent-detected type="office_mode" confidence="0.95">'
    echo '用户希望进入办公模式。执行 /office 显示办公助手界面。'
    echo '</intent-detected>'
    exit 0
fi

# 1i. TVS 展示检测
if echo "$PROMPT_TRIMMED" | grep -qiE '^(我要看|我想看|给我看|展示|显示|呈现)'; then
    echo '<intent-detected type="display" confidence="0.9">'
    echo '用户希望查看/展示内容。使用 TVS 渲染完整的仪表盘输出。'
    echo '</intent-detected>'
    exit 0
fi

# ========================================
# Phase 2: @Agent 触发 (直接调用，无需确认)
# ========================================

if echo "$PROMPT_TRIMMED" | grep -qiE '^@[A-Za-z]'; then
    AGENT_TAG=$(echo "$PROMPT_TRIMMED" | grep -oE '^@[A-Za-z][A-Za-z0-9_]*' | head -1)
    AGENT_UPPER=$(echo "$AGENT_TAG" | tr '[:lower:]' '[:upper:]')

    # 映射 @Agent 到 subagent_type
    # Base @Agent roster (the active agents the base kernel installs). The
    # extended roster is dispatched only when the agents-extra component
    # ships its own intents.conf entries.
    case "$AGENT_UPPER" in
        @DEV)         SUBAGENT="dev" ;;
        @QA)          SUBAGENT="qa" ;;
        @TEST)        SUBAGENT="test" ;;
        @WRITE)       SUBAGENT="write" ;;
        @PM)          SUBAGENT="pm" ;;
        @RESEARCHER)  SUBAGENT="researcher" ;;
        *)            SUBAGENT="" ;;
    esac

    if [ -n "$SUBAGENT" ]; then
        AGENT_CONTENT=$(echo "$PROMPT_TRIMMED" | sed "s/^$AGENT_TAG[[:space:]]*//")
        echo "<intent-detected type=\"agent\" agent=\"$AGENT_TAG\" subagent_type=\"$SUBAGENT\" confidence=\"0.95\">"
        echo "用户触发 $AGENT_TAG Agent。"
        echo "通过 Task tool 调用 subagent_type=\"$SUBAGENT\"。"
        if [ -n "$AGENT_CONTENT" ]; then
            echo "Agent 任务内容: $AGENT_CONTENT"
        fi
        echo '</intent-detected>'
        exit 0
    fi
fi

# ========================================
# Phase 5: 学习逻辑 (合并自 intent-learning-hook.sh)
# 不阻塞主流程，异步处理
# ========================================

# 5a. 纠正信号检测: "不对，我是要XXX" / "我说的是XXX" / "应该是XXX"
if echo "$PROMPT_LOWER" | grep -qiE '^(不对|错了|我说的是|我是要|应该是|我要的是)'; then
    # 异步处理，不阻塞
    (
        RAW_INTENT=$(echo "$PROMPT_LOWER" | sed -E 's/^(不对|错了|我说的是|我是要|应该是|我要的是)[，,]?[[:space:]]*//')

        # 映射到标准 intent 类型
        CORRECT_INTENT="$RAW_INTENT"
        case "$RAW_INTENT" in
            *执行*|*做*|*干*|*开始*|*继续*) CORRECT_INTENT="execute" ;;
            *确认*|*同意*|*通过*|*可以*|*好*) CORRECT_INTENT="confirm" ;;
            *拒绝*|*取消*|*不要*|*停*) CORRECT_INTENT="reject" ;;
            *查询*|*搜索*|*找*) CORRECT_INTENT="query" ;;
            *保存*|*休息*) CORRECT_INTENT="save" ;;
            *展示*|*显示*|*看*) CORRECT_INTENT="display" ;;
        esac

        if [ -n "$CORRECT_INTENT" ]; then
            # 获取上一次未识别的输入
            LAST_INPUT=$(sqlite3 "$DB_PATH" "
                SELECT input FROM sys_intent_unknown
                ORDER BY created_at DESC LIMIT 1
            " 2>/dev/null)

            if [ -n "$LAST_INPUT" ]; then
                # 记录纠正到数据库
                sqlite3 "$DB_PATH" "
                    INSERT INTO sys_intent_corrections (original_input, corrected_intent, created_at)
                    VALUES ('$(echo "$LAST_INPUT" | sed "s/'/''/g")', '$CORRECT_INTENT', datetime('now'));
                " 2>/dev/null

                echo "<intent-learning>"
                echo "已学习: \"$LAST_INPUT\" -> $CORRECT_INTENT"
                echo "</intent-learning>"
            fi
        fi
    ) &
    exit 0
fi

# 5b. 确认信号 (上次识别正确的正向反馈)
if echo "$PROMPT_LOWER" | grep -qiE '^(好|可以?|嗯+|行|对|是|ok|yes)(的|啊|吧)?$'; then
    (
        LAST_PATTERN=$(sqlite3 "$DB_PATH" "
            SELECT pattern FROM sys_intent_patterns
            ORDER BY updated_at DESC LIMIT 1
        " 2>/dev/null)

        LAST_INTENT=$(sqlite3 "$DB_PATH" "
            SELECT intent_type FROM sys_intent_patterns
            ORDER BY updated_at DESC LIMIT 1
        " 2>/dev/null)

        if [ -n "$LAST_PATTERN" ] && [ -n "$LAST_INTENT" ]; then
            sqlite3 "$DB_PATH" "
                UPDATE sys_intent_patterns
                SET success_count = success_count + 1,
                    confidence = MIN(0.99, confidence + 0.01)
                WHERE pattern = '$(echo "$LAST_PATTERN" | sed "s/'/''/g")'
                  AND intent_type = '$LAST_INTENT'
            " 2>/dev/null
        fi
    ) &
fi

# 5c. 教学信号: "以后XXX就是YYY" / "记住，XXX表示YYY"
if echo "$PROMPT_LOWER" | grep -qiE '^(以后|记住|学习一下|记下来)'; then
    if echo "$PROMPT_LOWER" | grep -qiE '就是|表示|意思是'; then
        (
            PATTERN=$(echo "$PROMPT_LOWER" | sed -E "s/^(以后|记住|学习一下|记下来)[，,]?[[:space:]]*['\"]?([^'\"]+)['\"]?[[:space:]]*(就是|表示|意思是).*/\2/")
            RAW_INTENT=$(echo "$PROMPT_LOWER" | sed -E "s/.*(就是|表示|意思是)[[:space:]]*//")

            # 映射到标准 intent 类型
            INTENT="$RAW_INTENT"
            case "$RAW_INTENT" in
                *执行*|*做*|*干*|*开始*|*继续*) INTENT="execute" ;;
                *确认*|*同意*|*通过*|*可以*|*好*) INTENT="confirm" ;;
                *拒绝*|*取消*|*不要*|*停*) INTENT="reject" ;;
                *查询*|*搜索*|*找*) INTENT="query" ;;
                *保存*|*休息*) INTENT="save" ;;
                *展示*|*显示*|*看*) INTENT="display" ;;
            esac

            if [ -n "$PATTERN" ] && [ -n "$INTENT" ]; then
                sqlite3 "$DB_PATH" "
                    INSERT OR REPLACE INTO sys_intent_patterns (pattern, intent_type, success_count, confidence, created_at, updated_at)
                    VALUES ('$(echo "$PATTERN" | sed "s/'/''/g")', '$INTENT', 1, 0.8, datetime('now'), datetime('now'));
                " 2>/dev/null

                echo "<intent-learning>"
                echo "已学习: \"$PATTERN\" -> $INTENT"
                echo "</intent-learning>"
            fi
        ) &
        exit 0
    fi
fi

# ========================================
# Phase 6: Dashboard 查看请求
# 触发词: dashboard/仪表盘/状况/看指标
# ========================================

if echo "$PROMPT_TRIMMED" | grep -qiE 'dashboard|仪表盘|solar.*状况|看指标|solar.*dashboard'; then
    echo '<intent-detected type="show_dashboard" confidence="0.95">'
    echo '用户请求查看 Solar 运行状况。'
    echo '请执行: ~/.claude/scripts/solar-dashboard.sh 查看完整仪表盘。'
    echo '然后根据仪表盘数据，给出系统健康状况分析。'
    echo '</intent-detected>'
    exit 0
fi

# ========================================
# Phase 7: 完成信号检测
# 检测用户显式标记任务完成，写入 session 日志并通知 Solar
# ========================================

if echo "$PROMPT_TRIMMED" | grep -qiE '完成了|搞定了|做好了|弄完了|搞好了|写完了|改完了|改好了|任务完成|已完成|执行完毕'; then
    # 排除误报: "完成前"/"完成之前" 是验证意图，不是完成信号
    if ! echo "$PROMPT_TRIMMED" | grep -qiE '完成[前之]'; then
        (
            SESSION_ID=$(cat ~/.solar/.session-id 2>/dev/null || printf '%s_%s' "$(date +%s)" "$$")
            TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
            DESC=$(echo "$PROMPT_TRIMMED" | sed 's/[。！!.,]//g' | head -c 50)
            printf '{"ts":"%s","event":"task_completed","task":"%s","agent":"user","source":"user_signal","duration_hint":"completed","session_id":"%s"}\n' \
                "$TS" "$DESC" "$SESSION_ID" >> ~/.solar/session-state.jsonl 2>/dev/null
        ) &
        echo '<intent-detected type="task_completed" confidence="0.85">'
        echo '用户标记任务完成。Solar 应读取 ~/.solar/session-state.jsonl 分析最近完成的任务，并推荐下一步操作。'
        echo '</intent-detected>'
        exit 0
    fi
fi

if echo "$PROMPT_TRIMMED" | grep -qiE '\b(done|finished|complete)\b'; then
    (
        SESSION_ID=$(cat ~/.solar/.session-id 2>/dev/null || printf '%s_%s' "$(date +%s)" "$$")
        TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
        DESC=$(echo "$PROMPT_TRIMMED" | sed 's/[。！!.,]//g' | head -c 50)
        printf '{"ts":"%s","event":"task_completed","task":"%s","agent":"user","source":"user_signal","duration_hint":"completed","session_id":"%s"}\n' \
            "$TS" "$DESC" "$SESSION_ID" >> ~/.solar/session-state.jsonl 2>/dev/null
    ) &
    echo '<intent-detected type="task_completed" confidence="0.85">'
    echo '用户标记任务完成。Solar 应读取 ~/.solar/session-state.jsonl 分析最近完成的任务，并推荐下一步操作。'
    echo '</intent-detected>'
    exit 0
fi

# ========================================
# 无匹配，正常退出
# ========================================

_END_MS=$(hook_time_ms)
hook_log "UserPromptSubmit" "intent-engine" "ok" "$(($_END_MS - $_START_MS))" "intent=none"

exit 0
