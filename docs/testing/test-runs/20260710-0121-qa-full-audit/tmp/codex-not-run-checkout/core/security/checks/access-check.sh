#!/bin/bash
# Solar Security Check: 访问安全监控
# 检查异常访问、可疑活动

DB_PATH="$HOME/.solar/solar.db"
LOG_FILE="$HOME/.solar/logs/security.log"
ALERT_EMAIL="${SOLAR_ALERT_EMAIL:-guardian@example.com}"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [ACCESS] $1" >> "$LOG_FILE"
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

    osascript -e "display notification \"$message\" with title \"Solar 安全预警\" subtitle \"$level\"" 2>/dev/null

    if [[ "$level" == "critical" || "$level" == "emergency" ]]; then
        echo "$message" | himalaya message write --to "$ALERT_EMAIL" --subject "🚨 Solar 安全预警: $level" 2>/dev/null || true
    fi

    log "ALERT: [$level] $message"
}

# 检查异常访问频率
check_rate_limit() {
    local result=$(sqlite3 "$DB_PATH" "
        SELECT sender, COUNT(*) as cnt
        FROM bl_message_tasks
        WHERE created_at > datetime('now', '-5 minutes')
        GROUP BY sender
        HAVING COUNT(*) > 20
        LIMIT 1
    " 2>/dev/null)

    if [ -n "$result" ]; then
        IFS='|' read -r sender count <<< "$result"
        log "异常访问频率: $sender ($count 次/5分钟)"
        log_event "rate_limit" "warning" "$sender" "异常访问频率: $count 次/5分钟" "{\"sender\":\"$sender\",\"count\":$count}"
        send_alert "warning" "检测到异常访问: $sender ($count 次/5分钟)"
    fi
}

# 检查未授权访问尝试
check_unauthorized() {
    local count=$(sqlite3 "$DB_PATH" "
        SELECT COUNT(*) FROM sec_events
        WHERE event_type = 'unauthorized_access'
          AND created_at > datetime('now', '-10 minutes')
    " 2>/dev/null)

    if [ -n "$count" ] && [ "$count" -gt 5 ]; then
        log "多次未授权访问: $count 次/10分钟"
        log_event "unauthorized_access" "critical" "access_check" "多次未授权访问尝试: $count 次" "{\"count\":$count}"
        send_alert "critical" "检测到多次未授权访问尝试: $count 次/10分钟"
    fi
}

# 检查最近的安全事件
check_recent_events() {
    local critical_count=$(sqlite3 "$DB_PATH" "
        SELECT COUNT(*) FROM sec_events
        WHERE risk_level IN ('critical', 'emergency')
          AND created_at > datetime('now', '-1 hour')
          AND alert_sent = 0
    " 2>/dev/null)

    if [ -n "$critical_count" ] && [ "$critical_count" -gt 0 ]; then
        log "发现 $critical_count 个未处理的严重事件"
        # 标记为已处理，避免重复报警
        sqlite3 "$DB_PATH" "
            UPDATE sec_events SET alert_sent = 1
            WHERE risk_level IN ('critical', 'emergency')
              AND created_at > datetime('now', '-1 hour')
              AND alert_sent = 0
        " 2>/dev/null
    fi
}

mkdir -p "$(dirname "$LOG_FILE")"

log "开始访问安全检查..."
check_rate_limit
check_unauthorized
check_recent_events
log "访问安全检查完成"
