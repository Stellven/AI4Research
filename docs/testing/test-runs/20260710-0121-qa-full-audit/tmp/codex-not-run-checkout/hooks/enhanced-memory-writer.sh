#!/bin/bash
# Solar Enhanced Memory Writer
# 在 SessionEnd 时增强写入 episodic 和 procedural 记忆
# 触发: SessionEnd

DB_PATH="$HOME/.solar/solar.db"
SESSION_ID="${CLAUDE_SESSION_ID:-unknown}"

# 1. 写入 session 结束的 episodic 记忆
MEMORY_ID="ep_$(date +%s)_$(head -c 2 /dev/urandom | xxd -p)"

# 获取本次会话统计
TOOL_STATS=$(sqlite3 "$DB_PATH" "
SELECT tool_name, COUNT(*) as cnt
FROM evo_tool_calls
WHERE created_at >= datetime('now', '-2 hour')
GROUP BY tool_name
ORDER BY cnt DESC
LIMIT 5;
" 2>/dev/null | tr '\n' ',' | sed 's/,$//')

# 写入 episodic 记忆
if [ -n "$TOOL_STATS" ]; then
    sqlite3 "$DB_PATH" "
    INSERT OR IGNORE INTO evo_memory_episodic (
        memory_id, namespace, event_type, content,
        context, emotional_valence, importance_score, occurred_at
    ) VALUES (
        '$MEMORY_ID',
        'session',
        'session_end',
        'Session ended. Tools used: $TOOL_STATS',
        '{\"session_id\": \"$SESSION_ID\"}',
        0.5,
        0.6,
        datetime('now')
    );
    " 2>/dev/null
fi

# 2. 更新 procedural 记忆执行计数
# 获取本次会话使用的工具
TOOLS_USED=$(sqlite3 "$DB_PATH" "
SELECT DISTINCT tool_name FROM evo_tool_calls
WHERE created_at >= datetime('now', '-2 hour');
" 2>/dev/null)

for TOOL in $TOOLS_USED; do
    sqlite3 "$DB_PATH" "
    UPDATE evo_memory_procedural
    SET execution_count = execution_count + 1,
        last_executed_at = datetime('now')
    WHERE procedure_name = '$TOOL';
    " 2>/dev/null
done

# 3. 如果学到新模式，写入 episodic
# 检查是否有新的规则文件
NEW_RULES=$(find ~/.claude/rules -name "*.md" -mmin -120 2>/dev/null | wc -l | tr -d ' ')
if [ "$NEW_RULES" -gt 0 ]; then
    PATTERN_ID="ep_pattern_$(date +%s)"
    sqlite3 "$DB_PATH" "
    INSERT OR IGNORE INTO evo_memory_episodic (
        memory_id, namespace, event_type, content,
        importance_score, occurred_at
    ) VALUES (
        '$PATTERN_ID',
        'learning',
        'pattern_learned',
        'Learned $NEW_RULES new rules/patterns in this session',
        0.8,
        datetime('now')
    );
    " 2>/dev/null
fi

# 4. 如果完成了任务，写入 episodic
TASKS_DONE=$(sqlite3 "$DB_PATH" "
SELECT COUNT(*) FROM ses_task_records
WHERE start_time >= datetime('now', '-2 hour') AND status = 'completed';
" 2>/dev/null)

if [ "$TASKS_DONE" -gt 0 ]; then
    TASK_ID="ep_task_$(date +%s)"
    sqlite3 "$DB_PATH" "
    INSERT OR IGNORE INTO evo_memory_episodic (
        memory_id, namespace, event_type, content,
        importance_score, occurred_at
    ) VALUES (
        '$TASK_ID',
        'task',
        'task_completed',
        'Completed $TASKS_DONE tasks in this session',
        0.7,
        datetime('now')
    );
    " 2>/dev/null
fi

exit 0
