#!/bin/bash
# Solar Native Evolver - 纯 macOS 原生实现
# 不依赖 bun/node，只用系统自带工具

DB="$HOME/.solar/solar.db"
LOG="$HOME/.solar/logs/native-evolver.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG"
}

log "========== Native Evolver 开始 =========="

# ==================== 1. 健康检查 ====================

# 检查待执行的优化数量
PENDING=$(sqlite3 "$DB" "
    SELECT COUNT(*) FROM evo_optimization_strategies s
    WHERE s.enabled = 1
    AND NOT EXISTS (
        SELECT 1 FROM evo_optimization_executions e
        WHERE e.strategy_id = s.strategy_id
        AND e.executed_at > datetime('now', '-1 day')
    );
" 2>/dev/null || echo "0")

log "待执行优化: $PENDING"

# 检查今日成本
TODAY_COST=$(sqlite3 "$DB" "
    SELECT COALESCE(SUM(total_cost_usd), 0)
    FROM evo_daily_cost_summary
    WHERE date_bucket = date('now');
" 2>/dev/null || echo "0")

log "今日成本: \$$TODAY_COST"

# ==================== 2. 执行优化策略 ====================

# 策略1: 高成本自动降级
if (( $(echo "$TODAY_COST > 15" | bc -l) )); then
    log "触发: 高成本自动降级"
    sqlite3 "$DB" "
        UPDATE evo_model_routing_rules
        SET target_model = 'haiku'
        WHERE rule_id = 'rule:simple_task_routing';

        INSERT INTO evo_optimization_executions (
            execution_id, strategy_id, status, result_summary, executed_at
        ) VALUES (
            'exec_native_' || strftime('%s', 'now'),
            'strategy:auto_model_downgrade',
            'success',
            '成本超限，已降级到 haiku',
            datetime('now')
        );
    "
    log "已执行模型降级"
fi

# 策略2: 记忆清理 (每周日)
if [[ $(date +%u) -eq 7 ]]; then
    log "触发: 每周记忆清理"

    # 清理低重要性情景记忆
    CLEANED=$(sqlite3 "$DB" "
        DELETE FROM evo_memory_episodic
        WHERE importance < 0.1
        AND occurred_at < datetime('now', '-30 days');
        SELECT changes();
    " 2>/dev/null || echo "0")

    log "清理了 $CLEANED 条过期记忆"

    sqlite3 "$DB" "
        INSERT INTO evo_optimization_executions (
            execution_id, strategy_id, status, result_summary, executed_at
        ) VALUES (
            'exec_native_' || strftime('%s', 'now'),
            'strategy:memory_cleanup',
            'success',
            '清理了 $CLEANED 条过期记忆',
            datetime('now')
        );
    "
fi

# 策略3: 每日快照
log "创建每日快照"
SNAPSHOT_ID="snap_$(date +%s)_native"
VERSION=$(sqlite3 "$DB" "SELECT COALESCE(MAX(version_number), 0) + 1 FROM ont_snapshots;" 2>/dev/null || echo "1")

PREFS_STATE=$(sqlite3 "$DB" "
    SELECT json_group_array(json_object(
        'dimension_id', dimension_id,
        'value', COALESCE(current_value, default_value),
        'confidence', confidence,
        'sample_count', sample_count
    ))
    FROM ont_preference_dimensions;
" 2>/dev/null || echo "[]")

sqlite3 "$DB" "
    INSERT INTO ont_snapshots (
        snapshot_id, version_number, snapshot_type,
        preferences_state, trigger_reason,
        total_confidence, active_dimensions, learned_signals
    ) VALUES (
        '$SNAPSHOT_ID',
        $VERSION,
        'auto',
        '$PREFS_STATE',
        'Native Evolver 每日快照',
        (SELECT SUM(confidence) FROM ont_preference_dimensions),
        (SELECT COUNT(*) FROM ont_preference_dimensions WHERE confidence > 0),
        (SELECT COALESCE(SUM(sample_count), 0) FROM ont_preference_dimensions)
    );
" 2>/dev/null

log "快照已创建: v$VERSION"

# ==================== 3. 记录学习事件 ====================

sqlite3 "$DB" "
    INSERT INTO ont_learning_events (
        event_id, event_type, details, source_type
    ) VALUES (
        'evt_native_' || strftime('%s', 'now'),
        'self_optimization',
        json_object(
            'source', 'native_evolver',
            'pending_before', $PENDING,
            'cost_today', $TODAY_COST,
            'snapshot_version', $VERSION
        ),
        'system'
    );
" 2>/dev/null

# ==================== 4. macOS 通知 (可选) ====================

if [[ "$PENDING" -gt 0 ]] || (( $(echo "$TODAY_COST > 10" | bc -l) )); then
    osascript -e "display notification \"待优化: $PENDING | 成本: \$$TODAY_COST\" with title \"Solar Evolver\" sound name \"Glass\""
fi

log "========== Native Evolver 完成 =========="

# 输出摘要
echo "Native Evolver 执行完成"
echo "  待优化: $PENDING"
echo "  今日成本: \$$TODAY_COST"
echo "  快照版本: v$VERSION"
