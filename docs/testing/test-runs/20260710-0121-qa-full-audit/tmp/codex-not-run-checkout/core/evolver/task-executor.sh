#!/bin/bash
# Solar Task Executor - 执行 Solar 写入的任务
# Solar 写入任务到数据库，这个脚本读取并执行

DB="$HOME/.solar/solar.db"
LOG="$HOME/.solar/logs/task-executor.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG"
}

# 创建任务表 (如果不存在)
sqlite3 "$DB" "
CREATE TABLE IF NOT EXISTS sys_task_queue (
    task_id TEXT PRIMARY KEY,
    task_type TEXT NOT NULL,       -- 'shortcut', 'notify', 'shell', 'sql'
    task_payload JSON NOT NULL,    -- 任务参数
    status TEXT DEFAULT 'pending', -- 'pending', 'running', 'completed', 'failed'
    priority INTEGER DEFAULT 5,    -- 1-10, 越高越优先
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    executed_at DATETIME,
    result TEXT
);
CREATE INDEX IF NOT EXISTS idx_task_queue_status ON sys_task_queue(status, priority DESC);
"

log "========== Task Executor 开始 =========="

# 获取待执行任务
TASKS=$(sqlite3 -json "$DB" "
    SELECT task_id, task_type, task_payload
    FROM sys_task_queue
    WHERE status = 'pending'
    ORDER BY priority DESC, created_at ASC
    LIMIT 10;
" 2>/dev/null)

if [[ -z "$TASKS" || "$TASKS" == "[]" ]]; then
    log "无待执行任务"
    exit 0
fi

# 处理每个任务
echo "$TASKS" | jq -c '.[]' | while read -r task; do
    TASK_ID=$(echo "$task" | jq -r '.task_id')
    TASK_TYPE=$(echo "$task" | jq -r '.task_type')
    PAYLOAD=$(echo "$task" | jq -r '.task_payload')

    log "执行任务: $TASK_ID ($TASK_TYPE)"

    # 标记为运行中
    sqlite3 "$DB" "UPDATE sys_task_queue SET status = 'running' WHERE task_id = '$TASK_ID';"

    RESULT=""
    STATUS="completed"

    case "$TASK_TYPE" in
        "shortcut")
            # 执行 Apple Shortcut
            SHORTCUT_NAME=$(echo "$PAYLOAD" | jq -r '.name')
            SHORTCUT_INPUT=$(echo "$PAYLOAD" | jq -r '.input // empty')
            if [[ -n "$SHORTCUT_INPUT" ]]; then
                RESULT=$(shortcuts run "$SHORTCUT_NAME" -i "$SHORTCUT_INPUT" 2>&1) || STATUS="failed"
            else
                RESULT=$(shortcuts run "$SHORTCUT_NAME" 2>&1) || STATUS="failed"
            fi
            ;;

        "notify")
            # macOS 通知
            TITLE=$(echo "$PAYLOAD" | jq -r '.title')
            MESSAGE=$(echo "$PAYLOAD" | jq -r '.message')
            SOUND=$(echo "$PAYLOAD" | jq -r '.sound // "Glass"')
            osascript -e "display notification \"$MESSAGE\" with title \"$TITLE\" sound name \"$SOUND\"" 2>&1
            RESULT="通知已发送"
            ;;

        "shell")
            # 执行 shell 命令
            COMMAND=$(echo "$PAYLOAD" | jq -r '.command')
            RESULT=$(eval "$COMMAND" 2>&1) || STATUS="failed"
            ;;

        "sql")
            # 执行 SQL
            SQL=$(echo "$PAYLOAD" | jq -r '.sql')
            RESULT=$(sqlite3 "$DB" "$SQL" 2>&1) || STATUS="failed"
            ;;

        "reminder")
            # 创建提醒 (通过 Shortcuts)
            TITLE=$(echo "$PAYLOAD" | jq -r '.title')
            DUE=$(echo "$PAYLOAD" | jq -r '.due // empty')
            if shortcuts list | grep -q "solar_set_reminder"; then
                RESULT=$(shortcuts run "solar_set_reminder" -i "{\"title\":\"$TITLE\",\"due\":\"$DUE\"}" 2>&1) || STATUS="failed"
            else
                # 回退到 osascript
                osascript -e "tell application \"Reminders\" to make new reminder with properties {name:\"$TITLE\"}" 2>&1
                RESULT="提醒已创建 (AppleScript)"
            fi
            ;;

        *)
            log "未知任务类型: $TASK_TYPE"
            STATUS="failed"
            RESULT="未知任务类型"
            ;;
    esac

    # 更新任务状态
    ESCAPED_RESULT=$(echo "$RESULT" | sed "s/'/''/g")
    sqlite3 "$DB" "
        UPDATE sys_task_queue
        SET status = '$STATUS',
            executed_at = datetime('now'),
            result = '$ESCAPED_RESULT'
        WHERE task_id = '$TASK_ID';
    "

    log "任务 $TASK_ID 完成: $STATUS"
done

log "========== Task Executor 完成 =========="
