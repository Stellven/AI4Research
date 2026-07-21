-- ============================================================================
-- Solar Self-Evolution Executor - 自主优化执行引擎
-- Version: 1.0
-- Description: 自动决策、自主执行、闭环验证、安全回滚
-- ============================================================================

-- ============================================================================
-- 1. 优化策略定义表
-- ============================================================================

-- 优化策略模板 (系统内置 + 用户自定义)
CREATE TABLE IF NOT EXISTS evo_optimization_strategies (
    strategy_id TEXT PRIMARY KEY,
    strategy_name TEXT NOT NULL,
    strategy_type TEXT NOT NULL CHECK(strategy_type IN (
        'model_routing',      -- 模型路由优化
        'prompt_caching',     -- 提示词缓存优化
        'cost_reduction',     -- 成本降低
        'latency_reduction',  -- 延迟降低
        'quality_improvement',-- 质量提升
        'resource_scaling',   -- 资源伸缩
        'memory_management',  -- 记忆管理
        'routing_adjustment'  -- 路由调整
    )),

    -- 触发条件 (SQL WHERE 子句)
    trigger_condition TEXT NOT NULL,        -- e.g., "daily_cost_usd > 10"

    -- 执行动作 (JSON 格式)
    action_template JSON NOT NULL,          -- 执行模板

    -- 验证条件 (优化后期望达到的效果)
    success_condition TEXT,                 -- e.g., "new_cost < old_cost * 0.8"

    -- 置信度阈值 (低于此值需要人工审批)
    auto_execute_threshold REAL DEFAULT 0.8,

    -- 风险等级
    risk_level TEXT CHECK(risk_level IN ('low', 'medium', 'high', 'critical')) DEFAULT 'medium',

    -- 回滚策略
    rollback_template JSON,                 -- 回滚时执行的动作

    -- 冷却期 (同一策略两次执行的最小间隔秒数)
    cooldown_seconds INTEGER DEFAULT 3600,

    -- 启用状态
    enabled BOOLEAN DEFAULT TRUE,

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- 2. 优化执行记录表
-- ============================================================================

-- 优化执行历史
CREATE TABLE IF NOT EXISTS evo_optimization_executions (
    execution_id TEXT PRIMARY KEY,
    strategy_id TEXT NOT NULL REFERENCES evo_optimization_strategies(strategy_id),
    recommendation_id TEXT REFERENCES evo_recommendations(recommendation_id),

    -- 执行状态
    status TEXT NOT NULL CHECK(status IN (
        'pending',      -- 待执行
        'approved',     -- 已审批 (等待执行)
        'executing',    -- 执行中
        'validating',   -- 验证中
        'success',      -- 成功
        'failed',       -- 失败
        'rolled_back',  -- 已回滚
        'rejected'      -- 被拒绝
    )) DEFAULT 'pending',

    -- 执行模式
    execution_mode TEXT CHECK(execution_mode IN (
        'auto',         -- 全自动
        'supervised',   -- 监督式 (执行但需确认)
        'manual'        -- 手动触发
    )) DEFAULT 'auto',

    -- 执行前状态快照
    pre_state JSON NOT NULL,                -- 执行前的系统状态

    -- 执行的动作
    executed_action JSON,                   -- 实际执行的动作

    -- 执行后状态
    post_state JSON,                        -- 执行后的系统状态

    -- 验证结果
    validation_result JSON,                 -- 验证详情
    validation_passed BOOLEAN,

    -- 置信度
    confidence REAL NOT NULL,               -- 决策置信度

    -- 时间戳
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    approved_at DATETIME,
    executed_at DATETIME,
    validated_at DATETIME,
    completed_at DATETIME,

    -- 执行者
    executor TEXT DEFAULT 'system',         -- 'system' or 'user:<id>'
    approver TEXT,                          -- 审批者

    -- 错误信息
    error_message TEXT,

    -- 回滚信息
    rollback_reason TEXT,
    rolled_back_at DATETIME
);

-- ============================================================================
-- 3. 运行时配置表 (可动态调整的系统参数)
-- ============================================================================

CREATE TABLE IF NOT EXISTS evo_runtime_config (
    config_id TEXT PRIMARY KEY,
    config_key TEXT NOT NULL UNIQUE,
    config_value JSON NOT NULL,

    -- 元数据
    description TEXT,
    value_type TEXT CHECK(value_type IN ('string', 'number', 'boolean', 'json', 'model_alias')),

    -- 约束
    min_value REAL,
    max_value REAL,
    allowed_values JSON,                    -- 枚举值列表

    -- 变更追踪
    previous_value JSON,
    changed_by TEXT,                        -- 'system:strategy_id' or 'user:id'
    changed_at DATETIME,
    change_reason TEXT,

    -- 生效时间
    effective_from DATETIME DEFAULT CURRENT_TIMESTAMP,
    effective_until DATETIME,               -- NULL = 永久生效

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- 4. 模型路由规则表 (动态可调)
-- ============================================================================

CREATE TABLE IF NOT EXISTS evo_model_routing_rules (
    rule_id TEXT PRIMARY KEY,
    rule_name TEXT NOT NULL,
    priority INTEGER DEFAULT 50,            -- 优先级 (高优先级先匹配)

    -- 匹配条件
    condition_type TEXT CHECK(condition_type IN (
        'task_complexity',   -- 任务复杂度
        'token_budget',      -- Token 预算
        'latency_requirement', -- 延迟要求
        'quality_requirement', -- 质量要求
        'cost_budget',       -- 成本预算
        'time_of_day',       -- 时间段
        'user_preference',   -- 用户偏好
        'resource_type',     -- 资源类型
        'custom'             -- 自定义条件
    )),
    condition_expression TEXT NOT NULL,     -- SQL 表达式

    -- 路由目标
    target_model TEXT NOT NULL,             -- 目标模型 alias
    fallback_model TEXT,                    -- 降级模型

    -- 动态权重 (A/B 测试用)
    traffic_weight REAL DEFAULT 1.0,        -- 0-1, 流量权重

    -- 启用状态
    enabled BOOLEAN DEFAULT TRUE,

    -- 性能追踪
    match_count INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    avg_satisfaction REAL,

    -- 变更追踪
    created_by TEXT DEFAULT 'system',
    last_modified_by TEXT,

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- 5. 内置优化策略 (种子数据)
-- ============================================================================

-- 策略1: 高成本自动降级
INSERT OR REPLACE INTO evo_optimization_strategies (
    strategy_id, strategy_name, strategy_type,
    trigger_condition, action_template, success_condition,
    auto_execute_threshold, risk_level, rollback_template, cooldown_seconds
) VALUES (
    'strategy:auto_model_downgrade',
    '高成本自动模型降级',
    'model_routing',
    'SELECT 1 FROM evo_daily_cost_summary WHERE date_bucket = date("now") AND total_cost_usd > 15',
    '{
        "type": "update_routing_rule",
        "actions": [
            {
                "rule_id": "rule:simple_task_routing",
                "changes": {"target_model": "haiku", "enabled": true}
            }
        ],
        "config_updates": [
            {"key": "default_model_for_simple_tasks", "value": "haiku"}
        ]
    }',
    'SELECT 1 FROM evo_daily_cost_summary WHERE date_bucket = date("now", "+1 day") AND total_cost_usd < (SELECT total_cost_usd * 0.7 FROM evo_daily_cost_summary WHERE date_bucket = date("now"))',
    0.85,
    'medium',
    '{
        "type": "update_routing_rule",
        "actions": [
            {"rule_id": "rule:simple_task_routing", "changes": {"target_model": "sonnet"}}
        ]
    }',
    86400  -- 24小时冷却
);

-- 策略2: 低缓存率提示词优化
INSERT OR REPLACE INTO evo_optimization_strategies (
    strategy_id, strategy_name, strategy_type,
    trigger_condition, action_template, success_condition,
    auto_execute_threshold, risk_level, cooldown_seconds
) VALUES (
    'strategy:prompt_cache_optimization',
    '低缓存率提示词优化',
    'prompt_caching',
    'SELECT 1 FROM evo_hourly_model_usage WHERE hour_bucket >= datetime("now", "-6 hours") GROUP BY model_alias HAVING AVG(1.0 * total_cached_tokens / NULLIF(total_input_tokens, 0)) < 0.3',
    '{
        "type": "stabilize_system_prompt",
        "actions": [
            {"action": "pin_system_prompt_version", "duration_hours": 24},
            {"action": "disable_dynamic_context_injection", "scope": "non_essential"}
        ],
        "config_updates": [
            {"key": "system_prompt_cache_ttl_hours", "value": 24}
        ]
    }',
    'SELECT 1 FROM evo_hourly_model_usage WHERE hour_bucket >= datetime("now", "-1 hour") AND (1.0 * total_cached_tokens / NULLIF(total_input_tokens, 0)) > 0.5',
    0.7,
    'low',
    3600  -- 1小时冷却
);

-- 策略3: 延迟异常自动扩容
INSERT OR REPLACE INTO evo_optimization_strategies (
    strategy_id, strategy_name, strategy_type,
    trigger_condition, action_template, success_condition,
    auto_execute_threshold, risk_level, cooldown_seconds
) VALUES (
    'strategy:latency_auto_scaling',
    '延迟异常自动路由调整',
    'latency_reduction',
    'SELECT 1 FROM evo_anomalies WHERE metric_name = "latency_ms" AND severity IN ("warning", "critical") AND resolved = FALSE AND created_at >= datetime("now", "-15 minutes") GROUP BY resource_id HAVING COUNT(*) >= 3',
    '{
        "type": "adjust_routing",
        "actions": [
            {"action": "enable_fallback_model", "primary": "opus", "fallback": "sonnet"},
            {"action": "reduce_max_tokens", "reduction_percent": 20}
        ]
    }',
    'SELECT 1 FROM evo_llm_calls WHERE created_at >= datetime("now", "-5 minutes") GROUP BY model_alias HAVING AVG(latency_ms) < 3000',
    0.9,
    'low',
    900   -- 15分钟冷却
);

-- 策略4: 质量下降自动升级模型
INSERT OR REPLACE INTO evo_optimization_strategies (
    strategy_id, strategy_name, strategy_type,
    trigger_condition, action_template, success_condition,
    auto_execute_threshold, risk_level, cooldown_seconds
) VALUES (
    'strategy:quality_auto_upgrade',
    '质量下降自动升级模型',
    'quality_improvement',
    'SELECT 1 FROM evo_learning_signals WHERE signal_type = "quality_issue" AND signal_strength < -0.5 AND created_at >= datetime("now", "-1 hour") GROUP BY trace_id HAVING COUNT(*) >= 2',
    '{
        "type": "upgrade_model",
        "actions": [
            {"action": "switch_model", "from": "haiku", "to": "sonnet"},
            {"action": "switch_model", "from": "sonnet", "to": "opus"}
        ],
        "duration_hours": 2
    }',
    'SELECT 1 FROM evo_feedback WHERE rating >= 4 AND created_at >= datetime("now", "-30 minutes")',
    0.75,
    'medium',
    7200  -- 2小时冷却
);

-- 策略5: 记忆清理
INSERT OR REPLACE INTO evo_optimization_strategies (
    strategy_id, strategy_name, strategy_type,
    trigger_condition, action_template, success_condition,
    auto_execute_threshold, risk_level, cooldown_seconds
) VALUES (
    'strategy:memory_cleanup',
    '过期记忆自动清理',
    'memory_management',
    'SELECT 1 FROM evo_memory_episodic WHERE importance < 0.1 AND last_retrieved < datetime("now", "-30 days") LIMIT 1',
    '{
        "type": "cleanup_memory",
        "actions": [
            {"action": "archive_low_importance_episodic", "threshold": 0.1, "older_than_days": 30},
            {"action": "consolidate_semantic_duplicates", "similarity_threshold": 0.95},
            {"action": "prune_unused_procedural", "execution_count_below": 2, "older_than_days": 60}
        ]
    }',
    'SELECT 1 WHERE (SELECT COUNT(*) FROM evo_memory_episodic WHERE importance < 0.1) < 100',
    0.95,
    'low',
    86400  -- 24小时冷却
);

-- 策略6: 错误模式学习
INSERT OR REPLACE INTO evo_optimization_strategies (
    strategy_id, strategy_name, strategy_type,
    trigger_condition, action_template, success_condition,
    auto_execute_threshold, risk_level, cooldown_seconds
) VALUES (
    'strategy:error_pattern_learning',
    '错误模式自动学习',
    'routing_adjustment',
    'SELECT 1 FROM evo_tool_calls WHERE success = FALSE AND created_at >= datetime("now", "-1 hour") GROUP BY tool_name HAVING COUNT(*) >= 5 AND (1.0 * SUM(CASE WHEN success THEN 1 ELSE 0 END) / COUNT(*)) < 0.7',
    '{
        "type": "learn_error_pattern",
        "actions": [
            {"action": "create_procedural_memory", "pattern": "error_avoidance"},
            {"action": "add_pre_check", "tool": "$tool_name", "check_type": "input_validation"},
            {"action": "update_routing_weight", "tool": "$tool_name", "weight_delta": -0.2}
        ]
    }',
    'SELECT 1 FROM evo_tool_calls WHERE tool_name = $tool_name AND created_at >= datetime("now", "-30 minutes") AND success = TRUE LIMIT 1',
    0.8,
    'medium',
    1800  -- 30分钟冷却
);

-- ============================================================================
-- 6. 初始路由规则
-- ============================================================================

INSERT OR REPLACE INTO evo_model_routing_rules (
    rule_id, rule_name, priority, condition_type, condition_expression,
    target_model, fallback_model, enabled
) VALUES
-- 简单任务用 Haiku
('rule:simple_task_routing', '简单任务路由', 100,
 'task_complexity',
 'task_complexity <= 2 AND estimated_tokens < 1000',
 'haiku', 'sonnet', TRUE),

-- 代码生成用 Sonnet
('rule:code_generation', '代码生成路由', 90,
 'resource_type',
 'resource_type IN ("agent:coder", "tool:Edit", "tool:Write")',
 'sonnet', 'opus', TRUE),

-- 复杂推理用 Opus
('rule:complex_reasoning', '复杂推理路由', 80,
 'task_complexity',
 'task_complexity >= 4 OR query_type = "architecture"',
 'opus', 'sonnet', TRUE),

-- 低成本时段用更好模型
('rule:off_peak_upgrade', '低峰时段升级', 70,
 'time_of_day',
 'CAST(strftime("%H", "now", "localtime") AS INTEGER) BETWEEN 0 AND 6',
 'opus', 'sonnet', TRUE),

-- 预算紧张时降级
('rule:budget_constraint', '预算约束降级', 60,
 'cost_budget',
 '(SELECT total_cost_usd FROM evo_daily_cost_summary WHERE date_bucket = date("now")) > (SELECT CAST(json_extract(config_value, "$.daily_limit") AS REAL) FROM evo_runtime_config WHERE config_key = "cost_budget") * 0.8',
 'haiku', NULL, TRUE);

-- ============================================================================
-- 7. 初始运行时配置
-- ============================================================================

INSERT OR REPLACE INTO evo_runtime_config (
    config_id, config_key, config_value, description, value_type
) VALUES
('config:default_model', 'default_model', '"sonnet"', '默认模型', 'model_alias'),
('config:cost_budget', 'cost_budget', '{"daily_limit": 20, "monthly_limit": 500}', '成本预算', 'json'),
('config:auto_optimization', 'auto_optimization_enabled', 'true', '是否启用自动优化', 'boolean'),
('config:optimization_confidence', 'min_auto_execute_confidence', '0.8', '自动执行最低置信度', 'number'),
('config:cache_ttl', 'system_prompt_cache_ttl_hours', '12', '系统提示词缓存TTL', 'number'),
('config:max_retries', 'max_auto_retries', '3', '自动重试次数上限', 'number'),
('config:rollback_window', 'auto_rollback_window_hours', '2', '自动回滚观察窗口', 'number');

-- ============================================================================
-- 8. 自优化执行触发器
-- ============================================================================

-- 当建议生成时，检查是否可以自动执行
CREATE TRIGGER IF NOT EXISTS trg_auto_execute_recommendation
AFTER INSERT ON evo_recommendations
WHEN NEW.auto_applicable = TRUE
  AND NEW.confidence >= (SELECT CAST(config_value AS REAL) FROM evo_runtime_config WHERE config_key = 'min_auto_execute_confidence')
  AND (SELECT config_value FROM evo_runtime_config WHERE config_key = 'auto_optimization_enabled') = 'true'
BEGIN
    -- 查找匹配的策略
    INSERT INTO evo_optimization_executions (
        execution_id, strategy_id, recommendation_id,
        status, execution_mode, pre_state, confidence
    )
    SELECT
        'exec:' || NEW.recommendation_id,
        s.strategy_id,
        NEW.recommendation_id,
        CASE
            WHEN s.risk_level = 'low' THEN 'approved'
            WHEN s.risk_level = 'medium' AND NEW.confidence >= 0.9 THEN 'approved'
            ELSE 'pending'
        END,
        CASE
            WHEN s.risk_level IN ('low', 'medium') THEN 'auto'
            ELSE 'supervised'
        END,
        NEW.current_state,
        NEW.confidence
    FROM evo_optimization_strategies s
    WHERE s.strategy_type = NEW.recommendation_type
      AND s.enabled = TRUE
      -- 检查冷却期
      AND NOT EXISTS (
          SELECT 1 FROM evo_optimization_executions e
          WHERE e.strategy_id = s.strategy_id
            AND e.status IN ('executing', 'validating', 'success')
            AND e.created_at >= datetime('now', '-' || s.cooldown_seconds || ' seconds')
      )
    LIMIT 1;
END;

-- 当执行状态变为 approved 时，自动开始执行
CREATE TRIGGER IF NOT EXISTS trg_start_approved_execution
AFTER UPDATE OF status ON evo_optimization_executions
WHEN NEW.status = 'approved' AND OLD.status = 'pending'
BEGIN
    UPDATE evo_optimization_executions
    SET
        status = 'executing',
        approved_at = CURRENT_TIMESTAMP,
        approver = CASE WHEN NEW.execution_mode = 'auto' THEN 'system' ELSE NEW.approver END
    WHERE execution_id = NEW.execution_id;
END;

-- ============================================================================
-- 9. 验证和回滚触发器
-- ============================================================================

-- 执行完成后自动进入验证阶段
CREATE TRIGGER IF NOT EXISTS trg_start_validation
AFTER UPDATE OF executed_at ON evo_optimization_executions
WHEN NEW.executed_at IS NOT NULL AND NEW.status = 'executing'
BEGIN
    UPDATE evo_optimization_executions
    SET status = 'validating'
    WHERE execution_id = NEW.execution_id;
END;

-- 验证失败时自动回滚
CREATE TRIGGER IF NOT EXISTS trg_auto_rollback_on_failure
AFTER UPDATE OF validation_passed ON evo_optimization_executions
WHEN NEW.validation_passed = FALSE AND NEW.status = 'validating'
BEGIN
    UPDATE evo_optimization_executions
    SET
        status = 'rolled_back',
        rollback_reason = 'Validation failed: ' || COALESCE(json_extract(NEW.validation_result, '$.reason'), 'unknown'),
        rolled_back_at = CURRENT_TIMESTAMP
    WHERE execution_id = NEW.execution_id;

    -- 生成学习信号
    INSERT INTO evo_learning_signals (
        signal_id, trace_id, signal_type, signal_strength,
        source, context, actionable
    )
    VALUES (
        'signal:rollback:' || NEW.execution_id,
        NULL,
        'routing_adjustment',
        -0.5,
        'optimization_rollback',
        json_object(
            'execution_id', NEW.execution_id,
            'strategy_id', NEW.strategy_id,
            'reason', NEW.rollback_reason
        ),
        TRUE
    );
END;

-- 验证成功时完成执行
CREATE TRIGGER IF NOT EXISTS trg_complete_successful_execution
AFTER UPDATE OF validation_passed ON evo_optimization_executions
WHEN NEW.validation_passed = TRUE AND NEW.status = 'validating'
BEGIN
    UPDATE evo_optimization_executions
    SET
        status = 'success',
        completed_at = CURRENT_TIMESTAMP
    WHERE execution_id = NEW.execution_id;

    -- 更新策略成功率 (用于动态调整置信度阈值)
    -- 生成正向学习信号
    INSERT INTO evo_learning_signals (
        signal_id, trace_id, signal_type, signal_strength,
        source, context, actionable
    )
    VALUES (
        'signal:success:' || NEW.execution_id,
        NULL,
        'cost_optimization',
        0.3,
        'optimization_success',
        json_object(
            'execution_id', NEW.execution_id,
            'strategy_id', NEW.strategy_id,
            'improvement', json_extract(NEW.validation_result, '$.improvement')
        ),
        FALSE
    );
END;

-- ============================================================================
-- 10. 配置变更追踪
-- ============================================================================

CREATE TRIGGER IF NOT EXISTS trg_track_config_change
AFTER UPDATE ON evo_runtime_config
WHEN OLD.config_value != NEW.config_value
BEGIN
    UPDATE evo_runtime_config
    SET
        previous_value = OLD.config_value,
        changed_at = CURRENT_TIMESTAMP
    WHERE config_id = NEW.config_id;

    -- 记录到演进日志
    INSERT INTO sys_evolution_log (
        evolution_id, resource_id, evolution_type,
        old_value, new_value, trigger_source, auto_applied
    )
    VALUES (
        'evo:config:' || NEW.config_key || ':' || strftime('%s', 'now'),
        'config:' || NEW.config_key,
        'parameter_adjustment',
        OLD.config_value,
        NEW.config_value,
        NEW.changed_by,
        CASE WHEN NEW.changed_by LIKE 'system:%' THEN TRUE ELSE FALSE END
    );
END;

-- ============================================================================
-- 11. 优化效果评估视图
-- ============================================================================

CREATE VIEW IF NOT EXISTS v_evo_optimization_effectiveness AS
SELECT
    s.strategy_id,
    s.strategy_name,
    s.strategy_type,
    COUNT(e.execution_id) AS total_executions,
    SUM(CASE WHEN e.status = 'success' THEN 1 ELSE 0 END) AS successful,
    SUM(CASE WHEN e.status = 'rolled_back' THEN 1 ELSE 0 END) AS rolled_back,
    SUM(CASE WHEN e.status = 'failed' THEN 1 ELSE 0 END) AS failed,
    ROUND(100.0 * SUM(CASE WHEN e.status = 'success' THEN 1 ELSE 0 END) / NULLIF(COUNT(e.execution_id), 0), 1) AS success_rate,
    AVG(e.confidence) AS avg_confidence,
    MAX(e.completed_at) AS last_success,
    s.auto_execute_threshold,
    s.risk_level
FROM evo_optimization_strategies s
LEFT JOIN evo_optimization_executions e ON s.strategy_id = e.strategy_id
GROUP BY s.strategy_id;

-- 待执行/待审批的优化
CREATE VIEW IF NOT EXISTS v_evo_pending_optimizations AS
SELECT
    e.execution_id,
    e.strategy_id,
    s.strategy_name,
    s.risk_level,
    e.status,
    e.execution_mode,
    e.confidence,
    e.pre_state,
    e.created_at,
    ROUND((julianday('now') - julianday(e.created_at)) * 24, 1) AS hours_pending
FROM evo_optimization_executions e
JOIN evo_optimization_strategies s ON e.strategy_id = s.strategy_id
WHERE e.status IN ('pending', 'approved', 'executing', 'validating')
ORDER BY
    CASE e.status
        WHEN 'validating' THEN 1
        WHEN 'executing' THEN 2
        WHEN 'approved' THEN 3
        WHEN 'pending' THEN 4
    END,
    e.created_at;

-- 模型路由效果
CREATE VIEW IF NOT EXISTS v_evo_routing_effectiveness AS
SELECT
    r.rule_id,
    r.rule_name,
    r.target_model,
    r.match_count,
    r.success_count,
    ROUND(100.0 * r.success_count / NULLIF(r.match_count, 0), 1) AS success_rate,
    r.avg_satisfaction,
    r.enabled,
    r.traffic_weight,
    r.priority
FROM evo_model_routing_rules r
ORDER BY r.priority DESC;

-- 自优化系统健康度
CREATE VIEW IF NOT EXISTS v_evo_self_optimization_health AS
SELECT
    -- 策略健康
    (SELECT COUNT(*) FROM evo_optimization_strategies WHERE enabled = TRUE) AS active_strategies,
    (SELECT COUNT(*) FROM evo_optimization_executions WHERE status = 'success' AND completed_at >= datetime('now', '-24 hours')) AS optimizations_24h,
    (SELECT COUNT(*) FROM evo_optimization_executions WHERE status = 'rolled_back' AND rolled_back_at >= datetime('now', '-24 hours')) AS rollbacks_24h,

    -- 路由健康
    (SELECT COUNT(*) FROM evo_model_routing_rules WHERE enabled = TRUE) AS active_routing_rules,
    (SELECT AVG(avg_satisfaction) FROM evo_model_routing_rules WHERE match_count > 10) AS avg_routing_satisfaction,

    -- 配置健康
    (SELECT COUNT(*) FROM evo_runtime_config WHERE changed_at >= datetime('now', '-24 hours')) AS config_changes_24h,

    -- 学习健康
    (SELECT COUNT(*) FROM evo_learning_signals WHERE created_at >= datetime('now', '-24 hours')) AS learning_signals_24h,
    (SELECT AVG(signal_strength) FROM evo_learning_signals WHERE created_at >= datetime('now', '-24 hours')) AS avg_signal_strength,

    -- 自动化程度
    (SELECT ROUND(100.0 * COUNT(CASE WHEN execution_mode = 'auto' THEN 1 END) / NULLIF(COUNT(*), 0), 1) FROM evo_optimization_executions WHERE created_at >= datetime('now', '-7 days')) AS auto_execution_rate_7d;

-- ============================================================================
-- 索引
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_evo_exec_strategy ON evo_optimization_executions(strategy_id);
CREATE INDEX IF NOT EXISTS idx_evo_exec_status ON evo_optimization_executions(status);
CREATE INDEX IF NOT EXISTS idx_evo_exec_created ON evo_optimization_executions(created_at);
CREATE INDEX IF NOT EXISTS idx_evo_routing_priority ON evo_model_routing_rules(priority DESC, enabled);
CREATE INDEX IF NOT EXISTS idx_evo_config_key ON evo_runtime_config(config_key);

-- ============================================================================
-- 自优化执行器摘要
-- ============================================================================
/*
┌─────────────────────────────────────────────────────────────────────────────┐
│                    Solar Self-Optimization Executor                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐  │
│  │ 建议生成     │ -> │ 策略匹配     │ -> │ 置信度检查   │ -> │ 自动执行     │  │
│  │ evo_recom.  │    │ strategies  │    │ threshold   │    │ executions  │  │
│  └─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘  │
│                                                                  ↓          │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐  │
│  │ 学习信号     │ <- │ 回滚/成功    │ <- │ 效果验证     │ <- │ 状态更新     │  │
│  │ learning    │    │ rollback    │    │ validation  │    │ config      │  │
│  └─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘  │
│                                                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│ 内置策略 (6个):                                                              │
│   1. auto_model_downgrade    - 高成本自动降级模型                            │
│   2. prompt_cache_optimization - 低缓存率优化提示词                          │
│   3. latency_auto_scaling    - 延迟异常自动调整路由                          │
│   4. quality_auto_upgrade    - 质量下降自动升级模型                          │
│   5. memory_cleanup          - 过期记忆自动清理                              │
│   6. error_pattern_learning  - 错误模式自动学习                              │
├─────────────────────────────────────────────────────────────────────────────┤
│ 安全机制:                                                                    │
│   • 置信度阈值 (默认 0.8)                                                    │
│   • 风险等级分层 (low/medium/high/critical)                                  │
│   • 冷却期防止频繁执行                                                       │
│   • 验证窗口确认效果                                                         │
│   • 自动回滚失败优化                                                         │
│   • 所有变更记录到演进日志                                                   │
└─────────────────────────────────────────────────────────────────────────────┘
*/
