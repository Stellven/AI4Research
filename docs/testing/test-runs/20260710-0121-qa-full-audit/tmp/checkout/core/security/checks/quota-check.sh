#!/bin/bash
# Solar Security Check: 配额监控
# 由 launchd 定时触发，检测配额异常

DB_PATH="$HOME/.solar/solar.db"
LOG_FILE="$HOME/.solar/logs/security.log"
ALERT_EMAIL="${SOLAR_ALERT_EMAIL:-guardian@example.com}"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [QUOTA] $1" >> "$LOG_FILE"
}

# 检查配额状态
check_quota() {
    local result=$(sqlite3 "$DB_PATH" "
        SELECT
            COALESCE(usage_pct, 0) as pct,
            COALESCE(status, 'ok') as status,
            COALESCE(used_tokens, 0) as used,
            COALESCE(max_tokens, 100000) as max
        FROM v_quota_realtime
        WHERE period_type = 'daily'
        LIMIT 1
    " 2>/dev/null)

    if [ -z "$result" ]; then
        echo "0|ok|0|100000"
    else
        echo "$result"
    fi
}

# 记录安全事件
log_event() {
    local event_type=$1
    local level=$2
    local source=$3
    local description=$4
    local details=$5

    sqlite3 "$DB_PATH" "
        INSERT INTO sec_events (event_type, risk_level, source, description, details)
        VALUES ('$event_type', '$level', '$source', '$description', '$details')
    "
}

# 发送预警
send_alert() {
    local level=$1
    local message=$2

    # 1. 桌面通知
    osascript -e "display notification \"$message\" with title \"Solar 安全预警\" subtitle \"$level\""

    # 2. 如果是 critical/emergency，发 iMessage
    if [[ "$level" == "critical" || "$level" == "emergency" ]]; then
        # 发送邮件 (通过 himalaya)
        echo "$message" | himalaya message write --to "$ALERT_EMAIL" --subject "⚠️ Solar 安全预警: $level" 2>/dev/null || true
    fi

    log "ALERT: [$level] $message"
}

# 主检测逻辑
main() {
    IFS='|' read -r pct status used max <<< "$(check_quota)"

    log "检查配额: ${pct}% used ($used/$max) - status: $status"

    case "$status" in
        "exceeded")
            log_event "quota_anomaly" "critical" "quota_check" "配额已超限: ${pct}%" "{\"used\":$used,\"max\":$max}"
            send_alert "critical" "配额已超限！已使用 ${pct}% ($used/$max tokens)"
            ;;
        "critical")
            log_event "quota_anomaly" "warning" "quota_check" "配额临界: ${pct}%" "{\"used\":$used,\"max\":$max}"
            send_alert "warning" "配额临界警告: ${pct}% ($used/$max tokens)"
            ;;
        "warning")
            log_event "quota_anomaly" "info" "quota_check" "配额警告: ${pct}%" "{\"used\":$used,\"max\":$max}"
            # warning 只记录，不发通知
            ;;
    esac
}

# 确保日志目录存在
mkdir -p "$(dirname "$LOG_FILE")"

main
