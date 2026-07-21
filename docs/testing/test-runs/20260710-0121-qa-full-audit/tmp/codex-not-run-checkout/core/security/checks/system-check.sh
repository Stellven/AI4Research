#!/bin/bash
# Solar Security Check: 系统健康监控
# 检查磁盘、任务失败率、队列积压

DB_PATH="$HOME/.solar/solar.db"
LOG_FILE="$HOME/.solar/logs/security.log"
ALERT_EMAIL="${SOLAR_ALERT_EMAIL:-guardian@example.com}"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [SYSTEM] $1" >> "$LOG_FILE"
}

log_event() {
    local event_type=$1
    local level=$2
    local source=$3
    local description=$4
    local details=$5

    sqlite3 "$DB_PATH" "
        INSERT INTO sec_events (event_type, risk_level, source, description, details)
        VALUES ('$event_type', '$level', '$source', '$description', '$details')
    " 2>/dev/null
}

send_alert() {
    local level=$1
    local message=$2

    osascript -e "display notification \"$message\" with title \"Solar 系统预警\" subtitle \"$level\"" 2>/dev/null

    if [[ "$level" == "critical" || "$level" == "emergency" ]]; then
        echo "$message" | himalaya message write --to "$ALERT_EMAIL" --subject "⚠️ Solar 系统预警: $level" 2>/dev/null || true
    fi

    log "ALERT: [$level] $message"
}

# 检查磁盘空间
check_disk() {
    local usage=$(df -h "$HOME/.solar" 2>/dev/null | tail -1 | awk '{print $5}' | tr -d '%')

    if [ -n "$usage" ]; then
        log "磁盘使用: ${usage}%"

        if [ "$usage" -gt 90 ]; then
            log_event "system_error" "critical" "disk_check" "磁盘空间不足: ${usage}%" "{\"usage_pct\":$usage}"
            send_alert "critical" "磁盘空间严重不足！已使用 ${usage}%"
        elif [ "$usage" -gt 80 ]; then
            log_event "system_error" "warning" "disk_check" "磁盘空间警告: ${usage}%" "{\"usage_pct\":$usage}"
            send_alert "warning" "磁盘空间警告: ${usage}%"
        fi
    fi
}

# 检查任务失败率
check_failure_rate() {
    local result=$(sqlite3 "$DB_PATH" "
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed
        FROM bl_message_tasks
        WHERE created_at > datetime('now', '-1 hour')
    " 2>/dev/null)

    if [ -n "$result" ]; then
        IFS='|' read -r total failed <<< "$result"

        if [ "$total" -gt 0 ]; then
            local rate=$((failed * 100 / total))
            log "任务失败率: ${rate}% ($failed/$total)"

            if [ "$rate" -gt 30 ]; then
                log_event "system_error" "warning" "failure_check" "任务失败率过高: ${rate}%" "{\"total\":$total,\"failed\":$failed}"
                send_alert "warning" "任务失败率过高: ${rate}% ($failed/$total)"
            fi
        fi
    fi
}

# 检查队列积压
check_backlog() {
    local pending=$(sqlite3 "$DB_PATH" "
        SELECT COUNT(*) FROM bl_message_tasks
        WHERE status IN ('pending', 'queued')
    " 2>/dev/null)

    if [ -n "$pending" ] && [ "$pending" -gt 50 ]; then
        log "队列积压: $pending 条"
        log_event "system_error" "warning" "backlog_check" "消息队列积压: $pending 条" "{\"pending\":$pending}"
        send_alert "warning" "消息队列积压: $pending 条待处理"
    fi
}

# 检查数据库大小
check_db_size() {
    local size_mb=$(du -m "$DB_PATH" 2>/dev/null | cut -f1)

    if [ -n "$size_mb" ] && [ "$size_mb" -gt 500 ]; then
        log "数据库过大: ${size_mb}MB"
        log_event "system_error" "warning" "db_check" "数据库文件过大: ${size_mb}MB" "{\"size_mb\":$size_mb}"
        send_alert "warning" "数据库文件过大: ${size_mb}MB，建议清理"
    fi
}

mkdir -p "$(dirname "$LOG_FILE")"

log "开始系统健康检查..."
check_disk
check_failure_rate
check_backlog
check_db_size
log "系统健康检查完成"
