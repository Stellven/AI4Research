#!/bin/bash
# Solar Security: 每日安全审计
# 凌晨 3 点由 launchd 触发

DB_PATH="$HOME/.solar/solar.db"
LOG_FILE="$HOME/.solar/logs/security.log"
REPORT_FILE="$HOME/.solar/logs/daily-audit-$(date +%Y%m%d).txt"
ALERT_EMAIL="${SOLAR_ALERT_EMAIL:-guardian@example.com}"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [AUDIT] $1" >> "$LOG_FILE"
}

send_report() {
    local subject=$1
    local body=$2

    # 发送邮件报告
    echo "$body" | himalaya message write --to "$ALERT_EMAIL" --subject "$subject" 2>/dev/null || true

    # 桌面通知
    osascript -e "display notification \"每日安全审计已完成，报告已发送\" with title \"Solar 安全审计\"" 2>/dev/null
}

mkdir -p "$(dirname "$LOG_FILE")"
mkdir -p "$(dirname "$REPORT_FILE")"

log "开始每日安全审计..."

# 生成报告
{
    echo "=========================================="
    echo "    Solar 每日安全审计报告"
    echo "    $(date '+%Y-%m-%d %H:%M:%S')"
    echo "=========================================="
    echo ""

    echo "## 1. 安全事件统计 (过去24小时)"
    echo ""
    sqlite3 -header -column "$DB_PATH" "
        SELECT
            event_type as '事件类型',
            risk_level as '风险级别',
            COUNT(*) as '次数'
        FROM sec_events
        WHERE created_at > datetime('now', '-1 day')
        GROUP BY event_type, risk_level
        ORDER BY COUNT(*) DESC
    " 2>/dev/null || echo "暂无数据"
    echo ""

    echo "## 2. 未授权访问来源"
    echo ""
    sqlite3 -header -column "$DB_PATH" "
        SELECT
            source as '来源',
            COUNT(*) as '尝试次数'
        FROM sec_events
        WHERE event_type = 'unauthorized_access'
          AND created_at > datetime('now', '-1 day')
        GROUP BY source
        ORDER BY COUNT(*) DESC
        LIMIT 10
    " 2>/dev/null || echo "暂无数据"
    echo ""

    echo "## 3. 任务执行统计"
    echo ""
    sqlite3 -header -column "$DB_PATH" "
        SELECT
            status as '状态',
            COUNT(*) as '数量'
        FROM bl_message_tasks
        WHERE created_at > datetime('now', '-1 day')
        GROUP BY status
    " 2>/dev/null || echo "暂无数据"
    echo ""

    echo "## 4. 配额使用情况"
    echo ""
    sqlite3 -header -column "$DB_PATH" "
        SELECT
            period_type as '周期',
            used_tokens as '已用Token',
            max_tokens as '最大Token',
            usage_pct || '%' as '使用率',
            status as '状态'
        FROM v_quota_realtime
    " 2>/dev/null || echo "暂无数据"
    echo ""

    echo "## 5. 系统健康"
    echo ""
    echo "数据库大小: $(du -h "$DB_PATH" 2>/dev/null | cut -f1)"
    echo "磁盘使用: $(df -h "$HOME/.solar" 2>/dev/null | tail -1 | awk '{print $5}')"
    echo "日志大小: $(du -sh "$HOME/.solar/logs" 2>/dev/null | cut -f1)"
    echo ""

    echo "## 6. 建议"
    echo ""

    # 检查是否需要清理
    local db_size=$(du -m "$DB_PATH" 2>/dev/null | cut -f1)
    if [ -n "$db_size" ] && [ "$db_size" -gt 100 ]; then
        echo "- ⚠️ 数据库较大 (${db_size}MB)，建议定期清理历史数据"
    fi

    local log_size=$(du -sm "$HOME/.solar/logs" 2>/dev/null | cut -f1)
    if [ -n "$log_size" ] && [ "$log_size" -gt 50 ]; then
        echo "- ⚠️ 日志较大 (${log_size}MB)，建议清理旧日志"
    fi

    local failed=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM bl_message_tasks WHERE status='failed' AND created_at > datetime('now', '-1 day')" 2>/dev/null)
    if [ -n "$failed" ] && [ "$failed" -gt 10 ]; then
        echo "- ⚠️ 昨日失败任务较多 ($failed 个)，建议检查原因"
    fi

    echo ""
    echo "=========================================="
    echo "    报告生成完成"
    echo "=========================================="

} > "$REPORT_FILE"

# 发送报告
send_report "📊 Solar 每日安全审计报告 $(date +%Y-%m-%d)" "$(cat "$REPORT_FILE")"

log "每日安全审计完成，报告已发送"
