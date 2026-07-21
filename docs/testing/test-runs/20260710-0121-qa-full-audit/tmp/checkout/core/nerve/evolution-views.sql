-- Solar Self-Evolution System - Views
-- Version: 1.0
-- Description: 优化视图 - 成本分析、性能洞察、学习信号、推荐引擎

-- ==================== 1. 成本分析视图 ====================

-- 模型成本排行 (7天)
CREATE VIEW IF NOT EXISTS v_evo_model_cost_ranking AS
SELECT
    model_alias,
    model_name,
    provider,
    COUNT(*) AS call_count,
    SUM(total_input_tokens) AS total_input_tokens,
    SUM(total_output_tokens) AS total_output_tokens,
    SUM(total_cached_tokens) AS total_cached_tokens,
    SUM(total_cost_usd) AS total_cost_usd,
    ROUND(AVG(total_cost_usd), 4) AS avg_cost_per_call,
    ROUND(1.0 * SUM(total_cached_tokens) / NULLIF(SUM(total_input_tokens), 0), 3) AS cache_hit_rate,
    ROUND(AVG(latency_ms), 0) AS avg_latency_ms
FROM evo_llm_calls
WHERE created_at >= datetime('now', '-7 days')
GROUP BY model_alias, model_name, provider
ORDER BY total_cost_usd DESC;

-- 高成本会话分析
CREATE VIEW IF NOT EXISTS v_evo_expensive_sessions AS
SELECT
    s.session_id,
    s.project_id,
    s.mode,
    s.total_turns,
    s.total_input_tokens,
    s.total_output_tokens,
    s.total_cost_usd,
    ROUND(s.total_cost_usd / NULLIF(s.total_turns, 0), 4) AS cost_per_turn,
    s.duration_seconds,
    s.started_at,
    s.summary
FROM evo_sessions s
WHERE s.total_cost_usd > 0.5  -- 成本超过 $0.50 的会话
AND s.started_at >= datetime('now', '-7 days')
ORDER BY s.total_cost_usd DESC
LIMIT 100;

-- 按资源类型的成本分布
CREATE VIEW IF NOT EXISTS v_evo_cost_by_resource AS
SELECT
    sp.span_type AS resource_type,
    sp.span_name AS resource_name,
    COUNT(DISTINCT t.trace_id) AS trace_count,
    COUNT(*) AS call_count,
    SUM(l.total_cost_usd) AS total_cost_usd,
    ROUND(AVG(l.total_cost_usd), 4) AS avg_cost,
    ROUND(AVG(l.latency_ms), 0) AS avg_latency_ms
FROM evo_spans sp
JOIN evo_traces t ON sp.trace_id = t.trace_id
LEFT JOIN evo_llm_calls l ON sp.span_id = l.span_id
WHERE sp.started_at >= datetime('now', '-7 days')
GROUP BY sp.span_type, sp.span_name
ORDER BY total_cost_usd DESC;

-- 成本优化机会
CREATE VIEW IF NOT EXISTS v_evo_cost_optimization_opportunities AS
SELECT
    'high_cost_model_usage' AS opportunity_type,
    model_alias AS target,
    call_count,
    total_cost_usd,
    CASE
        WHEN model_alias = 'opus' AND avg_latency_ms < 1000 THEN 'Consider using Sonnet for fast queries'
        WHEN cache_hit_rate < 0.3 AND total_input_tokens > 100000 THEN 'Improve prompt caching'
        ELSE 'Review usage patterns'
    END AS recommendation,
    ROUND((total_cost_usd * 0.2), 2) AS potential_savings_usd
FROM v_evo_model_cost_ranking
WHERE total_cost_usd > 1.0

UNION ALL

SELECT
    'expensive_session' AS opportunity_type,
    session_id AS target,
    total_turns AS call_count,
    total_cost_usd,
    CASE
        WHEN cost_per_turn > 0.1 THEN 'High cost per turn - review prompts'
        WHEN total_turns > 50 THEN 'Consider session splitting'
        ELSE 'Review conversation efficiency'
    END AS recommendation,
    ROUND((total_cost_usd * 0.15), 2) AS potential_savings_usd
FROM v_evo_expensive_sessions
WHERE total_cost_usd > 2.0
LIMIT 20;

-- ==================== 2. 性能分析视图 ====================

-- 延迟分布 (按模型)
CREATE VIEW IF NOT EXISTS v_evo_latency_distribution AS
SELECT
    model_alias,
    model_name,
    COUNT(*) AS sample_count,
    ROUND(AVG(latency_ms), 0) AS avg_latency_ms,
    MIN(latency_ms) AS min_latency_ms,
    MAX(latency_ms) AS max_latency_ms,
    -- 近似百分位数 (使用分组)
    ROUND(AVG(CASE WHEN row_num <= sample_count * 0.5 THEN latency_ms END), 0) AS approx_p50,
    ROUND(AVG(CASE WHEN row_num <= sample_count * 0.95 THEN latency_ms END), 0) AS approx_p95,
    ROUND(AVG(time_to_first_token_ms), 0) AS avg_ttft_ms,
    ROUND(AVG(tokens_per_second), 1) AS avg_tps
FROM (
    SELECT
        model_alias,
        model_name,
        latency_ms,
        time_to_first_token_ms,
        tokens_per_second,
        ROW_NUMBER() OVER (PARTITION BY model_name ORDER BY latency_ms) AS row_num,
        COUNT(*) OVER (PARTITION BY model_name) AS sample_count
    FROM evo_llm_calls
    WHERE created_at >= datetime('now', '-7 days')
) sub
GROUP BY model_alias, model_name;

-- 工具执行性能
CREATE VIEW IF NOT EXISTS v_evo_tool_performance AS
SELECT
    tool_name,
    tool_provider,
    COUNT(*) AS execution_count,
    SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS success_count,
    ROUND(100.0 * SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) / COUNT(*), 1) AS success_rate,
    ROUND(AVG(latency_ms), 0) AS avg_latency_ms,
    MAX(latency_ms) AS max_latency_ms,
    SUM(output_size_bytes) AS total_output_bytes
FROM evo_tool_calls
WHERE created_at >= datetime('now', '-7 days')
GROUP BY tool_name, tool_provider
ORDER BY execution_count DESC;

-- 慢查询分析
CREATE VIEW IF NOT EXISTS v_evo_slow_queries AS
SELECT
    t.trace_id,
    t.session_id,
    t.user_query,
    t.entry_point,
    t.latency_ms,
    t.total_cost_usd,
    json_extract(t.execution_path, '$') AS execution_path,
    l.model_name,
    l.input_tokens,
    l.output_tokens,
    t.status,
    t.started_at
FROM evo_traces t
LEFT JOIN evo_llm_calls l ON t.trace_id = l.trace_id
WHERE t.latency_ms > 5000  -- 超过 5 秒
AND t.started_at >= datetime('now', '-7 days')
ORDER BY t.latency_ms DESC
LIMIT 100;

-- ==================== 3. 使用模式分析 ====================

-- 按小时使用分布
CREATE VIEW IF NOT EXISTS v_evo_hourly_usage_pattern AS
SELECT
    strftime('%H', started_at) AS hour_of_day,
    COUNT(*) AS session_count,
    SUM(total_turns) AS total_turns,
    SUM(total_cost_usd) AS total_cost_usd,
    ROUND(AVG(total_cost_usd), 4) AS avg_session_cost
FROM evo_sessions
WHERE started_at >= datetime('now', '-30 days')
GROUP BY strftime('%H', started_at)
ORDER BY hour_of_day;

-- 常用查询模式
CREATE VIEW IF NOT EXISTS v_evo_common_query_patterns AS
SELECT
    query_type,
    json_extract(intent, '$.action') AS intent_action,
    COUNT(*) AS occurrence_count,
    ROUND(100.0 * SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) / COUNT(*), 1) AS success_rate,
    ROUND(AVG(total_cost_usd), 4) AS avg_cost,
    ROUND(AVG(latency_ms), 0) AS avg_latency_ms
FROM evo_traces
WHERE started_at >= datetime('now', '-7 days')
AND query_type IS NOT NULL
GROUP BY query_type, json_extract(intent, '$.action')
HAVING COUNT(*) >= 5
ORDER BY occurrence_count DESC;

-- 文件类型分析
CREATE VIEW IF NOT EXISTS v_evo_file_type_analysis AS
SELECT
    file_type,
    COUNT(*) AS access_count,
    COUNT(DISTINCT file_path) AS unique_files,
    SUM(line_count) AS total_lines_processed,
    ROUND(AVG(latency_ms), 0) AS avg_latency_ms,
    SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS success_count
FROM evo_tool_calls
WHERE file_type IS NOT NULL
AND created_at >= datetime('now', '-7 days')
GROUP BY file_type
ORDER BY access_count DESC;

-- ==================== 4. 记忆系统视图 ====================

-- 热门语义记忆
CREATE VIEW IF NOT EXISTS v_evo_hot_semantic_memory AS
SELECT
    namespace,
    key,
    value,
    confidence,
    access_count,
    last_accessed_at,
    julianday('now') - julianday(last_accessed_at) AS days_since_access
FROM evo_memory_semantic
WHERE access_count > 0
ORDER BY access_count DESC, last_accessed_at DESC
LIMIT 100;

-- 重要情节记忆
CREATE VIEW IF NOT EXISTS v_evo_important_episodes AS
SELECT
    namespace,
    event_type,
    event_summary,
    importance,
    outcome,
    recall_count,
    occurred_at,
    related_resources
FROM evo_memory_episodic
WHERE importance >= 0.7
OR recall_count >= 3
ORDER BY importance DESC, occurred_at DESC
LIMIT 100;

-- 高效过程记忆 (成功率高的)
CREATE VIEW IF NOT EXISTS v_evo_effective_procedures AS
SELECT
    namespace,
    procedure_name,
    procedure_type,
    description,
    execution_count,
    success_count,
    ROUND(100.0 * success_count / NULLIF(execution_count, 0), 1) AS success_rate,
    ROUND(avg_duration_seconds, 1) AS avg_duration_sec,
    last_executed_at
FROM evo_memory_procedural
WHERE execution_count >= 3
ORDER BY
    CASE WHEN execution_count > 0 THEN 1.0 * success_count / execution_count ELSE 0 END DESC,
    execution_count DESC;

-- ==================== 5. 反馈与学习视图 ====================

-- 未处理的反馈
CREATE VIEW IF NOT EXISTS v_evo_pending_feedback AS
SELECT
    feedback_id,
    feedback_type,
    rating,
    comment,
    trace_id,
    resource_id,
    created_at,
    julianday('now') - julianday(created_at) AS days_pending
FROM evo_feedback
WHERE processed = FALSE
ORDER BY
    CASE feedback_type
        WHEN 'bug_report' THEN 1
        WHEN 'correction' THEN 2
        WHEN 'implicit_negative' THEN 3
        ELSE 4
    END,
    created_at;

-- 学习信号汇总
CREATE VIEW IF NOT EXISTS v_evo_learning_signals_summary AS
SELECT
    signal_type,
    COUNT(*) AS signal_count,
    ROUND(AVG(signal_strength), 2) AS avg_strength,
    SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending_count,
    SUM(CASE WHEN status = 'applied' THEN 1 ELSE 0 END) AS applied_count,
    MAX(created_at) AS latest_signal
FROM evo_learning_signals
WHERE created_at >= datetime('now', '-30 days')
GROUP BY signal_type
ORDER BY signal_count DESC;

-- 从反馈提取的改进建议
CREATE VIEW IF NOT EXISTS v_evo_feedback_insights AS
SELECT
    feedback_type,
    COUNT(*) AS feedback_count,
    AVG(rating) AS avg_rating,
    -- 聚合常见问题
    json_group_array(DISTINCT comment) AS comments
FROM evo_feedback
WHERE created_at >= datetime('now', '-7 days')
AND comment IS NOT NULL
GROUP BY feedback_type
HAVING COUNT(*) >= 2;

-- ==================== 6. 实验分析视图 ====================

-- 活跃实验
CREATE VIEW IF NOT EXISTS v_evo_active_experiments AS
SELECT
    e.experiment_id,
    e.experiment_name,
    e.hypothesis,
    e.experiment_type,
    e.primary_metric,
    e.status,
    e.started_at,
    COUNT(a.id) AS sample_count,
    e.min_sample_size,
    ROUND(100.0 * COUNT(a.id) / NULLIF(e.min_sample_size, 0), 1) AS progress_percent
FROM evo_experiments e
LEFT JOIN evo_experiment_assignments a ON e.experiment_id = a.experiment_id
WHERE e.status IN ('running', 'paused')
GROUP BY e.experiment_id;

-- 实验结果分析
CREATE VIEW IF NOT EXISTS v_evo_experiment_results AS
SELECT
    e.experiment_id,
    e.experiment_name,
    a.variant_name,
    COUNT(*) AS sample_count,
    AVG(a.outcome_value) AS avg_outcome,
    MIN(a.outcome_value) AS min_outcome,
    MAX(a.outcome_value) AS max_outcome
FROM evo_experiments e
JOIN evo_experiment_assignments a ON e.experiment_id = a.experiment_id
WHERE a.outcome_value IS NOT NULL
GROUP BY e.experiment_id, a.variant_name;

-- ==================== 7. 基线与异常视图 ====================

-- 基线状态
CREATE VIEW IF NOT EXISTS v_evo_baseline_status AS
SELECT
    b.resource_id,
    b.metric_name,
    b.baseline_value,
    b.baseline_stddev,
    b.warning_threshold,
    b.critical_threshold,
    b.sample_count,
    b.last_updated_at,
    COALESCE(recent.recent_value, b.baseline_value) AS recent_value,
    ROUND((COALESCE(recent.recent_value, b.baseline_value) - b.baseline_value) / NULLIF(b.baseline_value, 0) * 100, 1) AS deviation_percent
FROM evo_baselines b
LEFT JOIN (
    -- 最近 24 小时的平均值
    SELECT
        resource_id,
        AVG(avg_latency_ms) AS recent_value  -- 简化: 只看延迟
    FROM sys_stats_daily
    WHERE date >= date('now', '-1 days')
    GROUP BY resource_id
) recent ON b.resource_id = recent.resource_id;

-- 活跃异常
CREATE VIEW IF NOT EXISTS v_evo_active_anomalies AS
SELECT
    a.anomaly_id,
    a.anomaly_type,
    a.severity,
    b.resource_id,
    b.metric_name,
    a.observed_value,
    a.expected_value,
    a.deviation_percent,
    a.possible_causes,
    a.detected_at,
    julianday('now') - julianday(a.detected_at) AS hours_since_detection
FROM evo_anomalies a
JOIN evo_baselines b ON a.baseline_id = b.baseline_id
WHERE a.resolved = FALSE
ORDER BY
    CASE a.severity
        WHEN 'critical' THEN 1
        WHEN 'warning' THEN 2
        ELSE 3
    END,
    a.detected_at DESC;

-- ==================== 8. 推荐引擎视图 ====================

-- 待处理的推荐
CREATE VIEW IF NOT EXISTS v_evo_pending_recommendations AS
SELECT
    recommendation_id,
    recommendation_type,
    title,
    description,
    confidence,
    json_extract(estimated_impact, '$.cost_saving') AS cost_saving,
    json_extract(estimated_impact, '$.latency_reduction') AS latency_reduction,
    auto_applicable,
    created_at
FROM evo_recommendations
WHERE status = 'pending'
ORDER BY confidence DESC, created_at;

-- 推荐效果追踪
CREATE VIEW IF NOT EXISTS v_evo_recommendation_effectiveness AS
SELECT
    recommendation_type,
    COUNT(*) AS total_recommendations,
    SUM(CASE WHEN status = 'applied' THEN 1 ELSE 0 END) AS applied_count,
    AVG(CASE
        WHEN status = 'applied' AND actual_impact IS NOT NULL
        THEN json_extract(actual_impact, '$.achieved_percent')
        ELSE NULL
    END) AS avg_achieved_percent
FROM evo_recommendations
WHERE created_at >= datetime('now', '-90 days')
GROUP BY recommendation_type;

-- ==================== 9. 综合仪表盘视图 ====================

-- 系统健康摘要
CREATE VIEW IF NOT EXISTS v_evo_system_health AS
SELECT
    -- 今日统计
    (SELECT COUNT(*) FROM evo_sessions WHERE date(started_at) = date('now')) AS sessions_today,
    (SELECT SUM(total_cost_usd) FROM evo_sessions WHERE date(started_at) = date('now')) AS cost_today_usd,
    (SELECT COUNT(*) FROM evo_traces WHERE date(started_at) = date('now') AND status = 'failed') AS errors_today,

    -- 7 天趋势
    (SELECT COUNT(*) FROM evo_sessions WHERE started_at >= datetime('now', '-7 days')) AS sessions_7d,
    (SELECT SUM(total_cost_usd) FROM evo_sessions WHERE started_at >= datetime('now', '-7 days')) AS cost_7d_usd,
    (SELECT ROUND(AVG(latency_ms), 0) FROM evo_traces WHERE started_at >= datetime('now', '-7 days')) AS avg_latency_7d_ms,

    -- 活跃问题
    (SELECT COUNT(*) FROM evo_anomalies WHERE resolved = FALSE AND severity = 'critical') AS critical_anomalies,
    (SELECT COUNT(*) FROM evo_feedback WHERE processed = FALSE) AS pending_feedback,
    (SELECT COUNT(*) FROM evo_recommendations WHERE status = 'pending') AS pending_recommendations,
    (SELECT COUNT(*) FROM evo_experiments WHERE status = 'running') AS active_experiments;

-- 每日摘要报告
CREATE VIEW IF NOT EXISTS v_evo_daily_report AS
SELECT
    date(s.started_at) AS report_date,

    -- 会话统计
    COUNT(DISTINCT s.session_id) AS session_count,
    SUM(s.total_turns) AS total_turns,
    ROUND(AVG(s.total_turns), 1) AS avg_turns_per_session,

    -- Token 统计
    SUM(s.total_input_tokens) AS total_input_tokens,
    SUM(s.total_output_tokens) AS total_output_tokens,
    SUM(s.total_cached_tokens) AS total_cached_tokens,
    ROUND(1.0 * SUM(s.total_cached_tokens) / NULLIF(SUM(s.total_input_tokens), 0), 3) AS cache_hit_rate,

    -- 成本统计
    SUM(s.total_cost_usd) AS total_cost_usd,
    ROUND(AVG(s.total_cost_usd), 4) AS avg_cost_per_session,

    -- 性能统计
    ROUND(AVG(t.latency_ms), 0) AS avg_trace_latency_ms,
    ROUND(100.0 * SUM(CASE WHEN t.status = 'success' THEN 1 ELSE 0 END) / NULLIF(COUNT(t.trace_id), 0), 1) AS success_rate

FROM evo_sessions s
LEFT JOIN evo_traces t ON s.session_id = t.session_id
WHERE s.started_at >= datetime('now', '-30 days')
GROUP BY date(s.started_at)
ORDER BY report_date DESC;
