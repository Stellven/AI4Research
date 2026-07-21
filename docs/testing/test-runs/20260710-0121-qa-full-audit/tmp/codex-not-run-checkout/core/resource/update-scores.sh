#!/bin/bash
# Solar Resource Score Updater
# 定期更新资源评分和权重
# 由 launchd 每小时执行一次

DB_PATH="$HOME/.solar/solar.db"
LOG_FILE="$HOME/.solar/logs/resource-scores.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}

mkdir -p "$(dirname "$LOG_FILE")"
log "开始更新资源评分..."

# 从 v_resource_ranking 视图更新 sys_resource_scores 表
sqlite3 "$DB_PATH" "
-- 更新评分表
INSERT OR REPLACE INTO sys_resource_scores (
    resource_id,
    total_calls,
    success_count,
    failure_count,
    success_rate,
    avg_latency_ms,
    reliability_score,
    efficiency_score,
    weight,
    rank_tier,
    recent_success_rate,
    trend,
    last_calculated
)
SELECT
    resource_id,
    total_calls,
    success_count,
    failure_count,
    success_rate,
    avg_latency_ms,
    reliability_score,
    efficiency_score,
    -- 权重限制在 0.2 到 2.0 之间
    MAX(0.2, MIN(2.0, calculated_weight)) as weight,
    rank_tier,
    success_rate_7d,
    trend,
    datetime('now')
FROM v_resource_ranking;
"

# 统计更新结果
total=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM sys_resource_scores")
s_tier=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM sys_resource_scores WHERE rank_tier='S'")
degrading=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM sys_resource_scores WHERE trend='degrading'")

log "更新完成: 共 $total 个资源, S级 $s_tier 个, 下降趋势 $degrading 个"

# 如果有下降趋势的资源，记录警告
if [ "$degrading" -gt 0 ]; then
    log "⚠️ 检测到 $degrading 个资源性能下降:"
    sqlite3 "$DB_PATH" "
        SELECT resource_id, name, success_rate, recent_success_rate
        FROM v_resource_ranking
        WHERE trend = 'degrading'
    " | while read line; do
        log "  - $line"
    done
fi

# 输出当前 Top 10
echo "📊 资源评分更新完成"
echo ""
echo "Top 10 资源:"
sqlite3 -header -column "$DB_PATH" "
    SELECT
        name,
        rank_tier as tier,
        ROUND(success_rate * 100, 1) || '%' as success,
        total_calls as calls,
        ROUND(weight, 2) as weight,
        trend
    FROM sys_resource_scores s
    JOIN sys_resources r ON s.resource_id = r.resource_id
    WHERE total_calls > 0
    ORDER BY efficiency_score DESC
    LIMIT 10
"

echo ""
echo "评级分布:"
sqlite3 -header -column "$DB_PATH" "
    SELECT rank_tier, COUNT(*) as count
    FROM sys_resource_scores
    GROUP BY rank_tier
    ORDER BY rank_tier
"
