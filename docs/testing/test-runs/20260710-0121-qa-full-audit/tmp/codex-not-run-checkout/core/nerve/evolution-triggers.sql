-- ============================================================================
-- Solar Evolution Triggers - 自动聚合与维护触发器
-- Version: 1.0
-- Description: 自动统计聚合、异常检测、学习信号生成
-- ============================================================================

-- ============================================================================
-- 1. Session Statistics Auto-Update
-- ============================================================================

-- 当 Trace 完成时，自动更新 Session 统计
CREATE TRIGGER IF NOT EXISTS trg_update_session_on_trace_complete
AFTER UPDATE OF ended_at ON evo_traces
WHEN NEW.ended_at IS NOT NULL AND OLD.ended_at IS NULL
BEGIN
    UPDATE evo_sessions
    SET
        total_turns = total_turns + 1,
        total_input_tokens = total_input_tokens + NEW.total_input_tokens,
        total_output_tokens = total_output_tokens + NEW.total_output_tokens,
        total_cached_tokens = total_cached_tokens + NEW.total_cached_tokens,
        total_cost_usd = total_cost_usd + NEW.total_cost_usd,
        updated_at = CURRENT_TIMESTAMP
    WHERE session_id = NEW.session_id;
END;

-- 当 Span 完成时，自动更新 Trace 统计
CREATE TRIGGER IF NOT EXISTS trg_update_trace_on_span_complete
AFTER UPDATE OF ended_at ON evo_spans
WHEN NEW.ended_at IS NOT NULL AND OLD.ended_at IS NULL
BEGIN
    UPDATE evo_traces
    SET
        total_input_tokens = total_input_tokens + COALESCE(NEW.input_tokens, 0),
        total_output_tokens = total_output_tokens + COALESCE(NEW.output_tokens, 0),
        total_cached_tokens = total_cached_tokens + COALESCE(NEW.cached_tokens, 0),
        total_cost_usd = total_cost_usd + COALESCE(NEW.cost_usd, 0),
        updated_at = CURRENT_TIMESTAMP
    WHERE trace_id = NEW.trace_id;
END;

-- ============================================================================
-- 2. Hourly Aggregation Triggers
-- ============================================================================

-- LLM 调用插入时，自动更新小时级聚合
CREATE TRIGGER IF NOT EXISTS trg_aggregate_llm_call_hourly
AFTER INSERT ON evo_llm_calls
BEGIN
    INSERT INTO evo_hourly_model_usage (
        hour_bucket, model_alias, model_name, provider,
        call_count, total_input_tokens, total_output_tokens,
        total_cached_tokens, total_cost_usd, avg_latency_ms,
        p50_latency_ms, p95_latency_ms, error_count
    )
    VALUES (
        strftime('%Y-%m-%d %H:00:00', NEW.created_at),
        NEW.model_alias,
        NEW.model_name,
        NEW.provider,
        1,
        NEW.input_tokens,
        NEW.output_tokens,
        NEW.cached_input_tokens,
        NEW.total_cost_usd,
        NEW.latency_ms,
        NEW.latency_ms,
        NEW.latency_ms,
        CASE WHEN NEW.error_code IS NOT NULL THEN 1 ELSE 0 END
    )
    ON CONFLICT(hour_bucket, model_alias) DO UPDATE SET
        call_count = call_count + 1,
        total_input_tokens = total_input_tokens + excluded.total_input_tokens,
        total_output_tokens = total_output_tokens + excluded.total_output_tokens,
        total_cached_tokens = total_cached_tokens + excluded.total_cached_tokens,
        total_cost_usd = total_cost_usd + excluded.total_cost_usd,
        avg_latency_ms = (avg_latency_ms * call_count + excluded.avg_latency_ms) / (call_count + 1),
        error_count = error_count + excluded.error_count,
        updated_at = CURRENT_TIMESTAMP;
END;

-- Tool 调用插入时，自动更新小时级聚合
CREATE TRIGGER IF NOT EXISTS trg_aggregate_tool_call_hourly
AFTER INSERT ON evo_tool_calls
BEGIN
    INSERT INTO evo_hourly_tool_usage (
        hour_bucket, tool_name,
        call_count, success_count, avg_latency_ms,
        total_input_chars, total_output_chars
    )
    VALUES (
        strftime('%Y-%m-%d %H:00:00', NEW.created_at),
        NEW.tool_name,
        1,
        CASE WHEN NEW.status = 'success' THEN 1 ELSE 0 END,
        NEW.latency_ms,
        COALESCE(length(NEW.input_params), 0),
        COALESCE(length(NEW.output_result), 0)
    )
    ON CONFLICT(hour_bucket, tool_name) DO UPDATE SET
        call_count = call_count + 1,
        success_count = success_count + excluded.success_count,
        avg_latency_ms = (avg_latency_ms * call_count + excluded.avg_latency_ms) / (call_count + 1),
        total_input_chars = total_input_chars + excluded.total_input_chars,
        total_output_chars = total_output_chars + excluded.total_output_chars,
        updated_at = CURRENT_TIMESTAMP;
END;

-- ============================================================================
-- 3. Daily Cost Summary Aggregation
-- ============================================================================

-- Session 结束时，自动更新日级成本汇总
CREATE TRIGGER IF NOT EXISTS trg_aggregate_session_daily
AFTER UPDATE OF ended_at ON evo_sessions
WHEN NEW.ended_at IS NOT NULL AND OLD.ended_at IS NULL
BEGIN
    INSERT INTO evo_daily_cost_summary (
        date_bucket, user_id, project_id,
        session_count, total_turns,
        total_input_tokens, total_output_tokens, total_cached_tokens,
        total_cost_usd, avg_session_duration_sec
    )
    VALUES (
        date(NEW.ended_at),
        COALESCE(NEW.user_id, 'default'),
        COALESCE(NEW.project_id, 'default'),
        1,
        NEW.total_turns,
        NEW.total_input_tokens,
        NEW.total_output_tokens,
        NEW.total_cached_tokens,
        NEW.total_cost_usd,
        (julianday(NEW.ended_at) - julianday(NEW.started_at)) * 86400
    )
    ON CONFLICT(date_bucket, user_id, project_id) DO UPDATE SET
        session_count = session_count + 1,
        total_turns = total_turns + excluded.total_turns,
        total_input_tokens = total_input_tokens + excluded.total_input_tokens,
        total_output_tokens = total_output_tokens + excluded.total_output_tokens,
        total_cached_tokens = total_cached_tokens + excluded.total_cached_tokens,
        total_cost_usd = total_cost_usd + excluded.total_cost_usd,
        avg_session_duration_sec = (avg_session_duration_sec * session_count + excluded.avg_session_duration_sec) / (session_count + 1),
        updated_at = CURRENT_TIMESTAMP;
END;

-- ============================================================================
-- 4. Memory Access Tracking
-- ============================================================================

-- 语义记忆访问追踪
CREATE TRIGGER IF NOT EXISTS trg_track_semantic_memory_access
AFTER UPDATE OF access_count ON evo_memory_semantic
BEGIN
    UPDATE evo_memory_semantic
    SET last_accessed_at = CURRENT_TIMESTAMP
    WHERE memory_id = NEW.memory_id;
END;

-- 情景记忆重要性衰减 (每次访问时计算)
CREATE TRIGGER IF NOT EXISTS trg_decay_episodic_memory
AFTER UPDATE OF recall_count ON evo_memory_episodic
BEGIN
    UPDATE evo_memory_episodic
    SET
        importance = importance * (1 - decay_rate),
        last_recalled_at = CURRENT_TIMESTAMP
    WHERE memory_id = NEW.memory_id;
END;

-- 程序记忆成功率更新
CREATE TRIGGER IF NOT EXISTS trg_update_procedural_success_rate
AFTER UPDATE OF execution_count ON evo_memory_procedural
BEGIN
    UPDATE evo_memory_procedural
    SET last_executed_at = CURRENT_TIMESTAMP
    WHERE memory_id = NEW.memory_id;
END;

-- ============================================================================
-- 5. Anomaly Detection Triggers
-- ============================================================================

-- LLM 调用延迟异常检测
CREATE TRIGGER IF NOT EXISTS trg_detect_latency_anomaly
AFTER INSERT ON evo_llm_calls
WHEN NEW.latency_ms > (
    SELECT COALESCE(critical_threshold, 10000)
    FROM evo_baselines
    WHERE resource_id = 'model:' || NEW.model_alias
      AND metric_name = 'latency_ms'
      AND is_active = TRUE
    LIMIT 1
)
BEGIN
    INSERT INTO evo_anomalies (
        anomaly_id, baseline_id, resource_id,
        metric_name, expected_value, actual_value,
        deviation_percent, severity, context
    )
    SELECT
        'anomaly:' || NEW.call_id,
        baseline_id,
        resource_id,
        'latency_ms',
        baseline_value,
        NEW.latency_ms,
        ROUND(100.0 * (NEW.latency_ms - baseline_value) / NULLIF(baseline_value, 0), 2),
        CASE
            WHEN NEW.latency_ms > critical_threshold THEN 'critical'
            WHEN NEW.latency_ms > warning_threshold THEN 'warning'
            ELSE 'info'
        END,
        json_object(
            'call_id', NEW.call_id,
            'model', NEW.model_name,
            'input_tokens', NEW.input_tokens,
            'trace_id', NEW.trace_id
        )
    FROM evo_baselines
    WHERE resource_id = 'model:' || NEW.model_alias
      AND metric_name = 'latency_ms'
      AND is_active = TRUE
    LIMIT 1;
END;

-- LLM 调用成本异常检测
CREATE TRIGGER IF NOT EXISTS trg_detect_cost_anomaly
AFTER INSERT ON evo_llm_calls
WHEN NEW.total_cost_usd > (
    SELECT COALESCE(critical_threshold, 1.0)
    FROM evo_baselines
    WHERE resource_id = 'model:' || NEW.model_alias
      AND metric_name = 'cost_per_call_usd'
      AND is_active = TRUE
    LIMIT 1
)
BEGIN
    INSERT INTO evo_anomalies (
        anomaly_id, baseline_id, resource_id,
        metric_name, expected_value, actual_value,
        deviation_percent, severity, context
    )
    SELECT
        'anomaly:cost:' || NEW.call_id,
        baseline_id,
        resource_id,
        'cost_per_call_usd',
        baseline_value,
        NEW.total_cost_usd,
        ROUND(100.0 * (NEW.total_cost_usd - baseline_value) / NULLIF(baseline_value, 0), 2),
        'warning',
        json_object(
            'call_id', NEW.call_id,
            'model', NEW.model_name,
            'total_tokens', NEW.input_tokens + NEW.output_tokens
        )
    FROM evo_baselines
    WHERE resource_id = 'model:' || NEW.model_alias
      AND metric_name = 'cost_per_call_usd'
      AND is_active = TRUE
    LIMIT 1;
END;

-- ============================================================================
-- 6. Learning Signal Generation
-- ============================================================================

-- 从显式反馈生成学习信号
CREATE TRIGGER IF NOT EXISTS trg_generate_learning_signal_from_feedback
AFTER INSERT ON evo_feedback
WHEN NEW.feedback_type IN ('explicit_rating', 'correction', 'preference')
BEGIN
    INSERT INTO evo_learning_signals (
        signal_id, trace_id, span_id,
        signal_type, signal_strength,
        source, context, actionable
    )
    VALUES (
        'signal:' || NEW.feedback_id,
        NEW.trace_id,
        NEW.span_id,
        CASE
            WHEN NEW.feedback_type = 'correction' THEN 'prompt_improvement'
            WHEN NEW.feedback_type = 'preference' THEN 'model_preference'
            WHEN NEW.rating <= 2 THEN 'quality_issue'
            WHEN NEW.rating >= 4 THEN 'prompt_improvement'
            ELSE 'routing_adjustment'
        END,
        CASE
            WHEN NEW.rating IS NOT NULL THEN (NEW.rating - 3.0) / 2.0  -- -1 to 1 scale
            WHEN NEW.feedback_type = 'correction' THEN 0.8
            ELSE 0.5
        END,
        'user_feedback',
        json_object(
            'feedback_id', NEW.feedback_id,
            'feedback_type', NEW.feedback_type,
            'rating', NEW.rating,
            'comment', NEW.comment
        ),
        CASE WHEN NEW.feedback_type = 'correction' THEN TRUE ELSE FALSE END
    );
END;

-- 从隐式信号生成学习信号 (重试 = 负面信号)
CREATE TRIGGER IF NOT EXISTS trg_generate_learning_signal_from_retry
AFTER UPDATE OF retry_count ON evo_traces
WHEN NEW.retry_count > OLD.retry_count
BEGIN
    INSERT INTO evo_learning_signals (
        signal_id, trace_id,
        signal_type, signal_strength,
        source, context, actionable
    )
    VALUES (
        'signal:retry:' || NEW.trace_id || ':' || NEW.retry_count,
        NEW.trace_id,
        'quality_issue',
        -0.3 * NEW.retry_count,  -- 越多重试，信号越强
        'implicit_retry',
        json_object(
            'retry_count', NEW.retry_count,
            'user_query', NEW.user_query
        ),
        TRUE
    );
END;

-- ============================================================================
-- 7. Auto-Recommendation Generation
-- ============================================================================

-- 当模型成本超过阈值时，自动生成切换建议
CREATE TRIGGER IF NOT EXISTS trg_recommend_model_switch
AFTER INSERT ON evo_daily_cost_summary
WHEN NEW.total_cost_usd > 10.0  -- 日成本超过 $10
BEGIN
    INSERT OR IGNORE INTO evo_recommendations (
        recommendation_id, recommendation_type,
        resource_id, current_state, recommended_state,
        estimated_impact, confidence, evidence,
        auto_applicable
    )
    VALUES (
        'rec:cost:' || NEW.date_bucket || ':' || NEW.user_id,
        'cost_reduction',
        'user:' || NEW.user_id,
        json_object('daily_cost_usd', NEW.total_cost_usd),
        json_object(
            'action', 'switch_to_haiku_for_simple_tasks',
            'target_cost_usd', NEW.total_cost_usd * 0.7
        ),
        json_object(
            'cost_savings_usd', NEW.total_cost_usd * 0.3,
            'savings_percent', 30
        ),
        0.7,
        json_object(
            'trigger', 'daily_cost_threshold',
            'threshold_usd', 10.0,
            'actual_usd', NEW.total_cost_usd
        ),
        FALSE  -- 需要人工审批
    );
END;

-- 当缓存命中率低时，建议优化系统提示词
CREATE TRIGGER IF NOT EXISTS trg_recommend_caching_optimization
AFTER INSERT ON evo_hourly_model_usage
WHEN NEW.call_count >= 10  -- 至少 10 次调用
  AND (1.0 * NEW.total_cached_tokens / NULLIF(NEW.total_input_tokens, 0)) < 0.3  -- 缓存率 < 30%
BEGIN
    INSERT OR IGNORE INTO evo_recommendations (
        recommendation_id, recommendation_type,
        resource_id, current_state, recommended_state,
        estimated_impact, confidence, evidence,
        auto_applicable
    )
    VALUES (
        'rec:cache:' || NEW.hour_bucket || ':' || NEW.model_alias,
        'caching_opportunity',
        'model:' || NEW.model_alias,
        json_object(
            'cache_hit_rate', 1.0 * NEW.total_cached_tokens / NULLIF(NEW.total_input_tokens, 0),
            'total_input_tokens', NEW.total_input_tokens
        ),
        json_object(
            'action', 'stabilize_system_prompt',
            'target_cache_rate', 0.6
        ),
        json_object(
            'potential_token_savings', NEW.total_input_tokens * 0.3,
            'potential_cost_savings_percent', 15
        ),
        0.6,
        json_object(
            'hour_bucket', NEW.hour_bucket,
            'call_count', NEW.call_count,
            'model', NEW.model_alias
        ),
        FALSE
    );
END;

-- ============================================================================
-- 8. Resource Usage Tracking (sys_invocations integration)
-- ============================================================================

-- 将 evo_tool_calls 同步到 sys_invocations (元数据系统集成)
CREATE TRIGGER IF NOT EXISTS trg_sync_tool_call_to_invocations
AFTER INSERT ON evo_tool_calls
BEGIN
    INSERT INTO sys_invocations (
        resource_id, invocation_type,
        session_id,
        latency_ms, status, error_message,
        metadata
    )
    VALUES (
        'tool:' || NEW.tool_name || ':1.0',
        'tool_call',
        (SELECT session_id FROM evo_traces WHERE trace_id = NEW.trace_id),
        NEW.latency_ms,
        NEW.status,
        NEW.error_message,
        json_object(
            'call_id', NEW.call_id,
            'trace_id', NEW.trace_id,
            'input_summary', substr(NEW.input_params, 1, 500),
            'output_summary', substr(NEW.output_result, 1, 500)
        )
    );
END;

-- ============================================================================
-- 9. Experiment Tracking
-- ============================================================================

-- 实验分配后更新参与人数
CREATE TRIGGER IF NOT EXISTS trg_update_experiment_participant_count
AFTER INSERT ON evo_experiment_assignments
BEGIN
    UPDATE evo_experiments
    SET
        participants_count = participants_count + 1,
        updated_at = CURRENT_TIMESTAMP
    WHERE experiment_id = NEW.experiment_id;
END;

-- ============================================================================
-- 10. Data Retention & Cleanup (scheduled via external job)
-- ============================================================================

-- 注意: SQLite 不支持定时任务，以下 SQL 需要通过外部 cron job 执行

-- 清理 90 天前的 Span 详情 (保留聚合数据)
-- DELETE FROM evo_spans WHERE created_at < datetime('now', '-90 days');

-- 清理 180 天前的详细 LLM 调用记录
-- DELETE FROM evo_llm_calls WHERE created_at < datetime('now', '-180 days');

-- 归档 365 天前的 Session
-- UPDATE evo_sessions SET status = 'archived' WHERE ended_at < datetime('now', '-365 days');

-- ============================================================================
-- 11. Indexes for Trigger Performance
-- ============================================================================

-- 触发器查询优化索引
CREATE INDEX IF NOT EXISTS idx_evo_baselines_lookup
ON evo_baselines(resource_id, metric_name, is_active);

CREATE INDEX IF NOT EXISTS idx_evo_traces_session
ON evo_traces(session_id);

CREATE INDEX IF NOT EXISTS idx_evo_spans_trace
ON evo_spans(trace_id);

CREATE INDEX IF NOT EXISTS idx_evo_llm_calls_trace
ON evo_llm_calls(trace_id);

CREATE INDEX IF NOT EXISTS idx_evo_tool_calls_trace
ON evo_tool_calls(trace_id);

CREATE INDEX IF NOT EXISTS idx_evo_feedback_trace
ON evo_feedback(trace_id);

-- ============================================================================
-- 触发器摘要
-- ============================================================================
/*
| 触发器 | 触发时机 | 功能 |
|--------|----------|------|
| trg_update_session_on_trace_complete | Trace 完成 | 更新 Session 统计 |
| trg_update_trace_on_span_complete | Span 完成 | 更新 Trace 统计 |
| trg_aggregate_llm_call_hourly | LLM 调用插入 | 小时级聚合 |
| trg_aggregate_tool_call_hourly | Tool 调用插入 | 小时级聚合 |
| trg_aggregate_session_daily | Session 结束 | 日级成本汇总 |
| trg_track_semantic_memory_access | 语义记忆访问 | 访问时间追踪 |
| trg_decay_episodic_memory | 情景记忆检索 | 重要性衰减 |
| trg_update_procedural_success_rate | 程序执行 | 成功率更新 |
| trg_detect_latency_anomaly | LLM 调用插入 | 延迟异常检测 |
| trg_detect_cost_anomaly | LLM 调用插入 | 成本异常检测 |
| trg_generate_learning_signal_from_feedback | 反馈插入 | 学习信号生成 |
| trg_generate_learning_signal_from_retry | 重试发生 | 负面信号生成 |
| trg_recommend_model_switch | 日成本超阈值 | 模型切换建议 |
| trg_recommend_caching_optimization | 缓存率低 | 缓存优化建议 |
| trg_sync_tool_call_to_invocations | Tool 调用 | 元数据同步 |
| trg_update_experiment_participant_count | 实验分配 | 参与人数更新 |
*/
