-- Solar Metadata System - Views
-- Version: 1.0
-- Description: 核心视图定义 - 资源概览、性能仪表盘、智能决策

-- ==================== 1. 资源概览视图 ====================

-- 所有资源状态概览
CREATE VIEW IF NOT EXISTS v_resource_overview AS
SELECT
    r.resource_id,
    r.resource_type,
    r.name,
    r.version,
    r.status,
    r.description,
    COALESCE(s.invocation_count, 0) AS invocations_7d,
    COALESCE(s.success_count, 0) AS successes_7d,
    CASE WHEN COALESCE(s.invocation_count, 0) > 0
        THEN ROUND(100.0 * s.success_count / s.invocation_count, 1)
        ELSE NULL
    END AS success_rate_7d,
    COALESCE(s.total_cost_usd, 0) AS cost_7d,
    COALESCE(s.avg_latency_ms, 0) AS avg_latency_7d,
    r.updated_at
FROM sys_resources r
LEFT JOIN (
    SELECT
        resource_id,
        SUM(invocation_count) AS invocation_count,
        SUM(success_count) AS success_count,
        SUM(total_cost_usd) AS total_cost_usd,
        AVG(avg_latency_ms) AS avg_latency_ms
    FROM sys_stats_daily
    WHERE date >= date('now', '-7 days')
    GROUP BY resource_id
) s ON r.resource_id = s.resource_id
ORDER BY r.resource_type, r.name;

-- 资源健康摘要
CREATE VIEW IF NOT EXISTS v_resource_health AS
SELECT
    r.resource_id,
    r.resource_type,
    r.name,
    r.status,
    CASE
        WHEN r.status = 'disabled' THEN 'disabled'
        WHEN COALESCE(s.failure_rate, 0) > 0.3 THEN 'critical'
        WHEN COALESCE(s.failure_rate, 0) > 0.1 THEN 'warning'
        WHEN COALESCE(s.invocation_count, 0) = 0 AND r.created_at < datetime('now', '-7 days') THEN 'unused'
        ELSE 'healthy'
    END AS health_status,
    COALESCE(s.invocation_count, 0) AS invocations_24h,
    COALESCE(s.failure_rate, 0) AS failure_rate_24h,
    COALESCE(s.avg_latency_ms, 0) AS avg_latency_24h,
    s.p95_latency_ms AS p95_latency_24h
FROM sys_resources r
LEFT JOIN (
    SELECT
        resource_id,
        SUM(invocation_count) AS invocation_count,
        SUM(failure_count) AS failure_count,
        CASE WHEN SUM(invocation_count) > 0
            THEN 1.0 * SUM(failure_count) / SUM(invocation_count)
            ELSE 0
        END AS failure_rate,
        AVG(avg_latency_ms) AS avg_latency_ms,
        MAX(p95_latency_ms) AS p95_latency_ms
    FROM sys_stats_daily
    WHERE date = date('now')
    GROUP BY resource_id
) s ON r.resource_id = s.resource_id
WHERE r.status != 'deprecated'
ORDER BY
    CASE
        WHEN COALESCE(s.failure_rate, 0) > 0.3 THEN 1
        WHEN COALESCE(s.failure_rate, 0) > 0.1 THEN 2
        ELSE 3
    END,
    r.name;

-- ==================== 2. Agent 性能视图 ====================

-- Agent 7日性能仪表盘
CREATE VIEW IF NOT EXISTS v_agent_performance AS
SELECT
    a.agent_id,
    r.name AS agent_name,
    a.emoji,
    a.default_model,
    json_extract(a.phases, '$') AS phases,
    COALESCE(s.total_invocations, 0) AS total_invocations,
    COALESCE(s.success_count, 0) AS success_count,
    CASE WHEN COALESCE(s.total_invocations, 0) > 0
        THEN ROUND(100.0 * s.success_count / s.total_invocations, 1)
        ELSE NULL
    END AS success_rate,
    COALESCE(s.total_tokens, 0) AS total_tokens,
    COALESCE(s.total_cost, 0) AS total_cost_usd,
    COALESCE(s.avg_latency, 0) AS avg_latency_ms,
    COALESCE(s.p95_latency, 0) AS p95_latency_ms,
    s.daily_trend
FROM sys_agents a
JOIN sys_resources r ON a.agent_id = r.resource_id
LEFT JOIN (
    SELECT
        resource_id,
        SUM(invocation_count) AS total_invocations,
        SUM(success_count) AS success_count,
        SUM(total_tokens) AS total_tokens,
        SUM(total_cost_usd) AS total_cost,
        AVG(avg_latency_ms) AS avg_latency,
        MAX(p95_latency_ms) AS p95_latency,
        GROUP_CONCAT(date || ':' || invocation_count, ',') AS daily_trend
    FROM sys_stats_daily
    WHERE date >= date('now', '-7 days')
    GROUP BY resource_id
) s ON a.agent_id = s.resource_id
WHERE r.status = 'active'
ORDER BY COALESCE(s.total_invocations, 0) DESC;

-- ==================== 3. Skill 排行视图 ====================

-- Skill 30日使用排行
CREATE VIEW IF NOT EXISTS v_skill_ranking AS
SELECT
    sk.skill_id,
    r.name AS skill_name,
    sk.command,
    sk.category,
    sk.user_invocable,
    COALESCE(s.total_invocations, 0) AS invocations_30d,
    COALESCE(s.success_count, 0) AS successes_30d,
    CASE WHEN COALESCE(s.total_invocations, 0) > 0
        THEN ROUND(100.0 * s.success_count / s.total_invocations, 1)
        ELSE NULL
    END AS success_rate_30d,
    COALESCE(s.unique_sessions, 0) AS unique_sessions_30d,
    RANK() OVER (ORDER BY COALESCE(s.total_invocations, 0) DESC) AS usage_rank
FROM sys_skills sk
JOIN sys_resources r ON sk.skill_id = r.resource_id
LEFT JOIN (
    SELECT
        resource_id,
        SUM(invocation_count) AS total_invocations,
        SUM(success_count) AS success_count,
        SUM(unique_sessions) AS unique_sessions
    FROM sys_stats_daily
    WHERE date >= date('now', '-30 days')
    GROUP BY resource_id
) s ON sk.skill_id = s.resource_id
WHERE r.status = 'active'
ORDER BY invocations_30d DESC;

-- ==================== 4. 模型成本视图 ====================

-- 模型成本分析
CREATE VIEW IF NOT EXISTS v_model_costs AS
SELECT
    m.model_id,
    r.name AS model_name,
    m.provider,
    m.input_price_per_mtok,
    m.output_price_per_mtok,
    COALESCE(s.total_tokens, 0) AS total_tokens_7d,
    COALESCE(s.total_cost, 0) AS total_cost_7d,
    COALESCE(s.total_invocations, 0) AS invocations_7d,
    CASE WHEN COALESCE(s.total_invocations, 0) > 0
        THEN ROUND(s.total_cost / s.total_invocations, 4)
        ELSE 0
    END AS avg_cost_per_call,
    CASE WHEN COALESCE(s.total_invocations, 0) > 0
        THEN ROUND(1.0 * s.total_tokens / s.total_invocations, 0)
        ELSE 0
    END AS avg_tokens_per_call,
    m.is_default
FROM sys_models m
JOIN sys_resources r ON m.model_id = r.resource_id
LEFT JOIN (
    SELECT
        resource_id,
        SUM(total_tokens) AS total_tokens,
        SUM(total_cost_usd) AS total_cost,
        SUM(invocation_count) AS total_invocations
    FROM sys_stats_daily
    WHERE date >= date('now', '-7 days')
    GROUP BY resource_id
) s ON m.model_id = s.resource_id
ORDER BY COALESCE(s.total_cost, 0) DESC;

-- ==================== 5. Gate 效率视图 ====================

-- Gate 通过率分析
CREATE VIEW IF NOT EXISTS v_gate_effectiveness AS
SELECT
    gate_name,
    SUM(total_attempts) AS total_attempts_30d,
    SUM(passed_count) AS passed_30d,
    SUM(failed_count) AS failed_30d,
    CASE WHEN SUM(total_attempts) > 0
        THEN ROUND(100.0 * SUM(passed_count) / SUM(total_attempts), 1)
        ELSE NULL
    END AS pass_rate_30d,
    ROUND(AVG(avg_retry_count), 2) AS avg_retries,
    (
        SELECT json_group_array(json_object('reason', key, 'count', value))
        FROM (
            SELECT
                json_each.key AS key,
                SUM(json_each.value) AS value
            FROM sys_gate_stats gs2, json_each(gs2.common_failure_reasons)
            WHERE gs2.gate_name = sys_gate_stats.gate_name
                AND gs2.date >= date('now', '-30 days')
            GROUP BY json_each.key
            ORDER BY value DESC
            LIMIT 3
        )
    ) AS top_failure_reasons
FROM sys_gate_stats
WHERE date >= date('now', '-30 days')
GROUP BY gate_name
ORDER BY gate_name;

-- ==================== 6. 依赖树视图 ====================

-- 依赖关系树 (递归 CTE)
CREATE VIEW IF NOT EXISTS v_dependency_tree AS
WITH RECURSIVE dep_tree AS (
    -- 根节点 (没有被依赖的资源)
    SELECT
        r.resource_id,
        r.resource_type,
        r.name,
        0 AS depth,
        r.resource_id AS root_id
    FROM sys_resources r
    WHERE NOT EXISTS (
        SELECT 1 FROM sys_dependencies d
        WHERE d.to_resource = r.resource_id
        AND d.dependency_type = 'requires'
    )

    UNION ALL

    -- 递归子节点
    SELECT
        r.resource_id,
        r.resource_type,
        r.name,
        dt.depth + 1,
        dt.root_id
    FROM sys_resources r
    JOIN sys_dependencies d ON r.resource_id = d.to_resource
    JOIN dep_tree dt ON d.from_resource = dt.resource_id
    WHERE d.dependency_type = 'requires'
    AND dt.depth < 10  -- 防止无限递归
)
SELECT
    resource_id,
    resource_type,
    name,
    depth,
    root_id,
    SUBSTR('          ', 1, depth * 2) || name AS tree_display
FROM dep_tree
ORDER BY root_id, depth, name;

-- ==================== 7. 配额状态视图 ====================

-- 配额使用状态
CREATE VIEW IF NOT EXISTS v_quota_status AS
SELECT
    q.quota_name,
    q.resource_type,
    q.resource_id,
    q.quota_type,
    q.period,
    q.limit_value,
    q.warning_threshold,
    COALESCE(u.current_usage, 0) AS current_usage,
    ROUND(100.0 * COALESCE(u.current_usage, 0) / q.limit_value, 1) AS usage_percent,
    CASE
        WHEN COALESCE(u.current_usage, 0) >= q.limit_value THEN 'exceeded'
        WHEN COALESCE(u.current_usage, 0) >= q.limit_value * q.warning_threshold THEN 'warning'
        ELSE 'ok'
    END AS status,
    q.limit_value - COALESCE(u.current_usage, 0) AS remaining,
    q.action_on_exceed
FROM sys_quotas q
LEFT JOIN (
    -- 根据配额类型和周期计算当前使用量
    SELECT
        q2.id AS quota_id,
        CASE q2.quota_type
            WHEN 'tokens' THEN SUM(s.total_tokens)
            WHEN 'cost' THEN SUM(s.total_cost_usd)
            WHEN 'invocations' THEN SUM(s.invocation_count)
            ELSE 0
        END AS current_usage
    FROM sys_quotas q2
    LEFT JOIN sys_stats_daily s ON (
        q2.resource_id IS NULL OR s.resource_id = q2.resource_id
    )
    WHERE (
        (q2.period = 'daily' AND s.date = date('now')) OR
        (q2.period = 'weekly' AND s.date >= date('now', '-7 days')) OR
        (q2.period = 'monthly' AND s.date >= date('now', '-30 days'))
    )
    GROUP BY q2.id
) u ON q.id = u.quota_id
WHERE q.enabled = TRUE
ORDER BY usage_percent DESC;

-- 推荐模型 (基于配额)
CREATE VIEW IF NOT EXISTS v_recommended_model AS
SELECT
    CASE
        WHEN EXISTS (
            SELECT 1 FROM v_quota_status
            WHERE quota_type = 'cost'
            AND status IN ('exceeded', 'warning')
        ) THEN (
            SELECT model_id FROM sys_models m
            JOIN sys_resources r ON m.model_id = r.resource_id
            WHERE r.status = 'active'
            ORDER BY m.output_price_per_mtok ASC
            LIMIT 1
        )
        ELSE (
            SELECT model_id FROM sys_models
            WHERE is_default = TRUE
            LIMIT 1
        )
    END AS recommended_model,
    CASE
        WHEN EXISTS (
            SELECT 1 FROM v_quota_status
            WHERE quota_type = 'cost'
            AND status = 'exceeded'
        ) THEN 'cost_exceeded'
        WHEN EXISTS (
            SELECT 1 FROM v_quota_status
            WHERE quota_type = 'cost'
            AND status = 'warning'
        ) THEN 'cost_warning'
        ELSE 'normal'
    END AS reason;

-- ==================== 8. 路由规则汇总视图 ====================

-- 路由规则汇总
CREATE VIEW IF NOT EXISTS v_routing_summary AS
SELECT
    'model' AS routing_type,
    rule_name,
    priority,
    conditions,
    target_model AS target,
    fallback_model AS fallback,
    enabled,
    description
FROM sys_routing_model
UNION ALL
SELECT
    'agent' AS routing_type,
    rule_name,
    priority,
    conditions,
    target_agent AS target,
    fallback_agent AS fallback,
    enabled,
    description
FROM sys_routing_agent
UNION ALL
SELECT
    'tool' AS routing_type,
    rule_name,
    priority,
    conditions,
    target_tool AS target,
    fallback_tool AS fallback,
    enabled,
    description
FROM sys_routing_tool
ORDER BY routing_type, priority DESC;

-- ==================== 9. 最近演进视图 ====================

-- 最近自我演进
CREATE VIEW IF NOT EXISTS v_recent_evolutions AS
SELECT
    e.id,
    e.resource_id,
    r.name AS resource_name,
    r.resource_type,
    e.evolution_type,
    e.trigger_reason,
    e.before_state,
    e.after_state,
    e.impact_metrics,
    e.status,
    e.applied_at,
    e.rollback_at,
    CASE
        WHEN e.status = 'rolled_back' THEN 'rolled_back'
        WHEN json_extract(e.impact_metrics, '$.improvement') > 0 THEN 'positive'
        WHEN json_extract(e.impact_metrics, '$.improvement') < 0 THEN 'negative'
        ELSE 'neutral'
    END AS outcome
FROM sys_evolution_log e
JOIN sys_resources r ON e.resource_id = r.resource_id
WHERE e.applied_at >= datetime('now', '-30 days')
ORDER BY e.applied_at DESC;

-- ==================== 10. 智能优化视图 ====================

-- 低效资源 (待废弃候选)
CREATE VIEW IF NOT EXISTS v_underutilized_resources AS
SELECT
    r.resource_id,
    r.resource_type,
    r.name,
    r.status,
    r.created_at,
    COALESCE(s.total_invocations, 0) AS invocations_90d,
    julianday('now') - julianday(r.created_at) AS age_days,
    'low_usage' AS reason
FROM sys_resources r
LEFT JOIN (
    SELECT
        resource_id,
        SUM(invocation_count) AS total_invocations
    FROM sys_stats_daily
    WHERE date >= date('now', '-90 days')
    GROUP BY resource_id
) s ON r.resource_id = s.resource_id
WHERE r.status = 'active'
AND COALESCE(s.total_invocations, 0) < 5
AND r.created_at < datetime('now', '-7 days')
ORDER BY COALESCE(s.total_invocations, 0) ASC, r.created_at ASC;

-- 高成本资源
CREATE VIEW IF NOT EXISTS v_high_cost_resources AS
SELECT
    r.resource_id,
    r.resource_type,
    r.name,
    s.total_cost AS cost_7d,
    s.total_invocations AS invocations_7d,
    ROUND(s.total_cost / NULLIF(s.total_invocations, 0), 4) AS cost_per_call,
    'high_cost' AS reason
FROM sys_resources r
JOIN (
    SELECT
        resource_id,
        SUM(total_cost_usd) AS total_cost,
        SUM(invocation_count) AS total_invocations
    FROM sys_stats_daily
    WHERE date >= date('now', '-7 days')
    GROUP BY resource_id
    HAVING SUM(total_cost_usd) / NULLIF(SUM(invocation_count), 0) > 0.01
) s ON r.resource_id = s.resource_id
ORDER BY s.total_cost / NULLIF(s.total_invocations, 0) DESC;

-- 阶段瓶颈分析
CREATE VIEW IF NOT EXISTS v_phase_bottlenecks AS
SELECT
    from_phase,
    to_phase,
    SUM(transition_count) AS total_transitions,
    ROUND(AVG(avg_duration_seconds), 1) AS avg_duration_sec,
    MAX(max_duration_seconds) AS max_duration_sec,
    ROUND(AVG(success_rate), 1) AS avg_success_rate,
    CASE
        WHEN AVG(avg_duration_seconds) > 60 THEN 'slow'
        WHEN AVG(success_rate) < 0.8 THEN 'unreliable'
        ELSE 'normal'
    END AS status
FROM sys_phase_stats
WHERE date >= date('now', '-7 days')
GROUP BY from_phase, to_phase
HAVING AVG(avg_duration_seconds) > 30 OR AVG(success_rate) < 0.9
ORDER BY AVG(avg_duration_seconds) DESC;

-- 自演进候选检测
CREATE VIEW IF NOT EXISTS v_evolution_candidates AS
SELECT
    r.resource_id,
    r.resource_type,
    r.name,
    s.invocations_7d,
    s.success_rate,
    s.latency_variance,
    CASE
        WHEN s.success_rate < 0.7 THEN 'low_success_rate'
        WHEN s.latency_variance > 1000 THEN 'high_variance'
        WHEN s.success_rate < 0.9 AND s.latency_variance > 500 THEN 'needs_tuning'
        ELSE NULL
    END AS candidate_reason,
    json_object(
        'suggested_action',
        CASE
            WHEN s.success_rate < 0.7 THEN 'retry_policy_adjustment'
            WHEN s.latency_variance > 1000 THEN 'timeout_adjustment'
            ELSE 'parameter_tuning'
        END
    ) AS suggested_evolution
FROM sys_resources r
JOIN (
    SELECT
        resource_id,
        SUM(invocation_count) AS invocations_7d,
        CASE WHEN SUM(invocation_count) > 0
            THEN 1.0 * SUM(success_count) / SUM(invocation_count)
            ELSE 1.0
        END AS success_rate,
        -- 计算延迟方差 (使用 p95-p50 作为近似)
        AVG(p95_latency_ms - p50_latency_ms) AS latency_variance
    FROM sys_stats_daily
    WHERE date >= date('now', '-7 days')
    GROUP BY resource_id
    HAVING SUM(invocation_count) >= 10
) s ON r.resource_id = s.resource_id
WHERE s.success_rate < 0.9 OR s.latency_variance > 500
ORDER BY
    CASE
        WHEN s.success_rate < 0.7 THEN 1
        WHEN s.latency_variance > 1000 THEN 2
        ELSE 3
    END,
    s.invocations_7d DESC;

-- 用户可调用的 Skills
CREATE VIEW IF NOT EXISTS v_user_invocable_skills AS
SELECT
    sk.skill_id,
    r.name AS skill_name,
    sk.command,
    sk.category,
    sk.linked_agent,
    r.description,
    COALESCE(s.invocations_7d, 0) AS invocations_7d,
    COALESCE(s.success_rate, 100) AS success_rate_7d
FROM sys_skills sk
JOIN sys_resources r ON sk.skill_id = r.resource_id
LEFT JOIN (
    SELECT
        resource_id,
        SUM(invocation_count) AS invocations_7d,
        CASE WHEN SUM(invocation_count) > 0
            THEN ROUND(100.0 * SUM(success_count) / SUM(invocation_count), 1)
            ELSE 100
        END AS success_rate
    FROM sys_stats_daily
    WHERE date >= date('now', '-7 days')
    GROUP BY resource_id
) s ON sk.skill_id = s.resource_id
WHERE sk.user_invocable = TRUE
AND r.status = 'active'
ORDER BY sk.category, sk.command;

-- ==================== 11. Shortcuts 视图 ====================

-- 可用 Shortcuts 列表
CREATE VIEW IF NOT EXISTS v_available_shortcuts AS
SELECT
    sc.shortcut_id,
    r.name AS shortcut_name,
    r.description,
    sc.category,
    sc.trigger_phrases,
    sc.siri_phrase,
    sc.permission_level,
    CASE sc.permission_level
        WHEN 0 THEN '只读'
        WHEN 1 THEN '本地写入'
        WHEN 2 THEN '通信'
        WHEN 3 THEN '敏感'
    END AS permission_desc,
    sc.requires_confirmation,
    sc.supports_siri,
    sc.is_installed,
    COALESCE(s.invocations_7d, 0) AS invocations_7d,
    COALESCE(s.success_rate, 100) AS success_rate_7d
FROM sys_shortcuts sc
JOIN sys_resources r ON sc.shortcut_id = r.resource_id
LEFT JOIN (
    SELECT
        resource_id,
        SUM(invocation_count) AS invocations_7d,
        CASE WHEN SUM(invocation_count) > 0
            THEN ROUND(100.0 * SUM(success_count) / SUM(invocation_count), 1)
            ELSE 100
        END AS success_rate
    FROM sys_stats_daily
    WHERE date >= date('now', '-7 days')
    GROUP BY resource_id
) s ON sc.shortcut_id = s.resource_id
WHERE r.status = 'active'
ORDER BY sc.category, r.name;

-- Shortcut 执行统计
CREATE VIEW IF NOT EXISTS v_shortcut_stats AS
SELECT
    sc.shortcut_id,
    r.name AS shortcut_name,
    sc.category,
    COALESCE(s.total_executions, 0) AS total_executions,
    COALESCE(s.successful_executions, 0) AS successful_executions,
    COALESCE(s.success_rate, 100) AS success_rate,
    COALESCE(s.avg_execution_ms, 0) AS avg_execution_ms,
    s.last_executed
FROM sys_shortcuts sc
JOIN sys_resources r ON sc.shortcut_id = r.resource_id
LEFT JOIN (
    SELECT
        resource_id,
        SUM(invocation_count) AS total_executions,
        SUM(success_count) AS successful_executions,
        CASE WHEN SUM(invocation_count) > 0
            THEN ROUND(100.0 * SUM(success_count) / SUM(invocation_count), 1)
            ELSE 100
        END AS success_rate,
        ROUND(AVG(avg_latency_ms), 0) AS avg_execution_ms,
        MAX(date) AS last_executed
    FROM sys_stats_daily
    GROUP BY resource_id
) s ON sc.shortcut_id = s.resource_id
ORDER BY COALESCE(s.total_executions, 0) DESC;

-- 活跃自动化
CREATE VIEW IF NOT EXISTS v_active_automations AS
SELECT
    a.id,
    a.automation_name,
    r.name AS shortcut_name,
    a.trigger_type,
    a.trigger_config,
    a.params_template,
    a.enabled,
    a.last_triggered_at,
    a.created_at
FROM sys_shortcut_automations a
JOIN sys_shortcuts sc ON a.shortcut_id = sc.shortcut_id
JOIN sys_resources r ON sc.shortcut_id = r.resource_id
WHERE a.enabled = TRUE
ORDER BY a.trigger_type, a.automation_name;

-- 意图路由表
CREATE VIEW IF NOT EXISTS v_intent_routing AS
SELECT
    ri.intent_pattern,
    ri.keywords,
    ri.target_type,
    ri.target_id,
    r.name AS target_name,
    r.description AS target_description,
    ri.priority,
    ri.param_mapping,
    ri.confidence_threshold,
    ri.enabled
FROM sys_routing_intent ri
JOIN sys_resources r ON ri.target_id = r.resource_id
WHERE ri.enabled = TRUE
AND r.status = 'active'
ORDER BY ri.priority DESC;

-- 按类别统计 Shortcuts
CREATE VIEW IF NOT EXISTS v_shortcut_category_stats AS
SELECT
    sc.category,
    COUNT(*) AS shortcut_count,
    SUM(CASE WHEN sc.is_installed THEN 1 ELSE 0 END) AS installed_count,
    SUM(CASE WHEN sc.supports_siri THEN 1 ELSE 0 END) AS siri_enabled_count,
    AVG(sc.permission_level) AS avg_permission_level
FROM sys_shortcuts sc
JOIN sys_resources r ON sc.shortcut_id = r.resource_id
WHERE r.status = 'active'
GROUP BY sc.category
ORDER BY shortcut_count DESC;
