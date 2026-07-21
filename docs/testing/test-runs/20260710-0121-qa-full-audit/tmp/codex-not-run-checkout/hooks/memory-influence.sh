#!/bin/bash
# Solar Memory Decision Influence (MDI) Hook
# 在处理用户请求前，自动检索相关记忆并注入上下文
# 触发: UserPromptSubmit

DB_PATH="$HOME/.solar/solar.db"
INPUT=$(cat)
USER_PROMPT=$(echo "$INPUT" | jq -r '.user_prompt // ""' 2>/dev/null)

# 如果没有用户提示，直接退出
[ -z "$USER_PROMPT" ] && exit 0

# 记忆需求评估 - 关键词检测
NEED_EPISODIC=false
NEED_PROCEDURAL=false
NEED_SEMANTIC=false
NEED_FAVORITES=false

# 时间相关 → 需要 episodic
if echo "$USER_PROMPT" | grep -qiE "上次|之前|昨天|earlier|last time|previous|刚才"; then
    NEED_EPISODIC=true
fi

# 偏好相关 → 需要 favorites + semantic
if echo "$USER_PROMPT" | grep -qiE "喜欢|偏好|prefer|风格|style|习惯"; then
    NEED_FAVORITES=true
    NEED_SEMANTIC=true
fi

# 重复任务 → 需要 procedural
if echo "$USER_PROMPT" | grep -qiE "帮我|再次|又要|commit|pr|review|build|test"; then
    NEED_PROCEDURAL=true
fi

# 复杂任务 → 需要 semantic + episodic
if echo "$USER_PROMPT" | grep -qiE "架构|设计|方案|选择|怎么做|如何|分析|研究|规则|要求"; then
    NEED_SEMANTIC=true
    NEED_EPISODIC=true
fi

# 规则相关 → 需要 semantic
if echo "$USER_PROMPT" | grep -qiE "规则|规范|标准|铁律|原则|要求"; then
    NEED_SEMANTIC=true
fi

# 如果不需要任何记忆，直接退出
if ! $NEED_EPISODIC && ! $NEED_PROCEDURAL && ! $NEED_SEMANTIC && ! $NEED_FAVORITES; then
    exit 0
fi

# 生成检索关键词 (简单分词)
KEYWORDS=$(echo "$USER_PROMPT" | tr ' ' '\n' | grep -E '^.{2,}$' | head -5 | tr '\n' '|' | sed 's/|$//')

# 初始化结果
MEMORIES=""
INFLUENCE_ID="mdi_$(date +%s)_$(head -c 2 /dev/urandom | xxd -p)"
SOURCES_USED=""

# 1. 检索 Episodic Memory (情景记忆)
if $NEED_EPISODIC; then
    EPISODIC=$(sqlite3 "$DB_PATH" "
        SELECT content FROM evo_memory_episodic
        WHERE content LIKE '%${KEYWORDS}%'
        ORDER BY occurred_at DESC LIMIT 3
    " 2>/dev/null | head -c 500)

    if [ -n "$EPISODIC" ]; then
        MEMORIES="${MEMORIES}\n[Episodic Memory]\n${EPISODIC}"
        SOURCES_USED="${SOURCES_USED}episodic,"
    fi
fi

# 2. 检索 Procedural Memory (程序记忆)
if $NEED_PROCEDURAL; then
    PROCEDURAL=$(sqlite3 "$DB_PATH" "
        SELECT content FROM evo_memory_procedural
        WHERE content LIKE '%${KEYWORDS}%'
        ORDER BY frequency DESC LIMIT 2
    " 2>/dev/null | head -c 500)

    if [ -n "$PROCEDURAL" ]; then
        MEMORIES="${MEMORIES}\n[Procedural Memory]\n${PROCEDURAL}"
        SOURCES_USED="${SOURCES_USED}procedural,"
    fi
fi

# 3. 检索 Semantic Memory (语义记忆 - 规则和知识)
if $NEED_SEMANTIC; then
    SEMANTIC=$(sqlite3 "$DB_PATH" "
        SELECT content FROM evo_memory_semantic
        WHERE namespace LIKE 'rule%' OR namespace LIKE 'knowledge%'
        AND content LIKE '%${KEYWORDS}%'
        ORDER BY confidence DESC LIMIT 3
    " 2>/dev/null | head -c 500)

    if [ -n "$SEMANTIC" ]; then
        MEMORIES="${MEMORIES}\n[Semantic Memory]\n${SEMANTIC}"
        SOURCES_USED="${SOURCES_USED}semantic,"
    fi
fi

# 4. 检索 Favorites (偏好记忆)
if $NEED_FAVORITES; then
    FAVORITES=$(sqlite3 "$DB_PATH" "
        SELECT content FROM evo_memory_semantic
        WHERE namespace = 'favorites'
        ORDER BY confidence DESC LIMIT 2
    " 2>/dev/null | head -c 300)

    if [ -n "$FAVORITES" ]; then
        MEMORIES="${MEMORIES}\n[Favorites]\n${FAVORITES}"
        SOURCES_USED="${SOURCES_USED}favorites,"
    fi
fi

# 如果检索到了记忆，记录影响
if [ -n "$MEMORIES" ]; then
    # 记录到 evo_memory_influences 表
    sqlite3 "$DB_PATH" "
        INSERT INTO evo_memory_influences (
            session_id, request_summary, memory_retrieved,
            influence_type, created_at
        ) VALUES (
            '${CLAUDE_SESSION_ID:-unknown}',
            '$(echo "$USER_PROMPT" | head -c 200 | sed "s/'/''/g")',
            '$(echo -e "$MEMORIES" | head -c 1000 | sed "s/'/''/g")',
            'pre_decision [${SOURCES_USED%,}]',
            datetime('now')
        );
    " 2>/dev/null

    # 输出检索到的记忆 (会被 Claude 看到)
    echo "<memory-context>"
    echo "Based on your request, I found relevant memories:"
    echo -e "$MEMORIES"
    echo "</memory-context>"
fi

exit 0
