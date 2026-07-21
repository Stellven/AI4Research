-- Solar Metadata System - Triggers
-- Version: 1.0
-- Description: 自动化触发器 - 更新时间戳、统计聚合、自演进检测

-- ==================== 1. 时间戳自动更新 ====================

-- sys_resources 更新时间
CREATE TRIGGER IF NOT EXISTS tr_resources_updated_at
AFTER UPDATE ON sys_resources
BEGIN
    UPDATE sys_resources
    SET updated_at = CURRENT_TIMESTAMP
    WHERE resource_id = NEW.resource_id;
END;

-- ==================== 2. 资源注册自动同步 ====================

-- 插入 Agent 时自动创建主资源记录
CREATE TRIGGER IF NOT EXISTS tr_agent_insert_resource
BEFORE INSERT ON sys_agents
WHEN NOT EXISTS (SELECT 1 FROM sys_resources WHERE resource_id = NEW.agent_id)
BEGIN
    INSERT INTO sys_resources (resource_id, resource_type, name, version, status)
    VALUES (
        NEW.agent_id,
        'agent',
        SUBSTR(NEW.agent_id, INSTR(NEW.agent_id, ':') + 1),
        '1.0',
        'active'
    );
END;

-- 插入 Skill 时自动创建主资源记录
CREATE TRIGGER IF NOT EXISTS tr_skill_insert_resource
BEFORE INSERT ON sys_skills
WHEN NOT EXISTS (SELECT 1 FROM sys_resources WHERE resource_id = NEW.skill_id)
BEGIN
    INSERT INTO sys_resources (resource_id, resource_type, name, version, status)
    VALUES (
        NEW.skill_id,
        'skill',
        SUBSTR(NEW.skill_id, INSTR(NEW.skill_id, ':') + 1),
        '1.0',
        'active'
    );
END;

-- 插入 Hook 时自动创建主资源记录
CREATE TRIGGER IF NOT EXISTS tr_hook_insert_resource
BEFORE INSERT ON sys_hooks
WHEN NOT EXISTS (SELECT 1 FROM sys_resources WHERE resource_id = NEW.hook_id)
BEGIN
    INSERT INTO sys_resources (resource_id, resource_type, name, version, status)
    VALUES (
        NEW.hook_id,
        'hook',
        SUBSTR(NEW.hook_id, INSTR(NEW.hook_id, ':') + 1),
        '1.0',
        'active'
    );
END;

-- 插入 Tool 时自动创建主资源记录
CREATE TRIGGER IF NOT EXISTS tr_tool_insert_resource
BEFORE INSERT ON sys_tools
WHEN NOT EXISTS (SELECT 1 FROM sys_resources WHERE resource_id = NEW.tool_id)
BEGIN
    INSERT INTO sys_resources (resource_id, resource_type, name, version, status)
    VALUES (
        NEW.tool_id,
        'tool',
        SUBSTR(NEW.tool_id, INSTR(NEW.tool_id, ':') + 1),
        '1.0',
        'active'
    );
END;

-- 插入 Model 时自动创建主资源记录
CREATE TRIGGER IF NOT EXISTS tr_model_insert_resource
BEFORE INSERT ON sys_models
WHEN NOT EXISTS (SELECT 1 FROM sys_resources WHERE resource_id = NEW.model_id)
BEGIN
    INSERT INTO sys_resources (resource_id, resource_type, name, version, status)
    VALUES (
        NEW.model_id,
        'model',
        SUBSTR(NEW.model_id, INSTR(NEW.model_id, ':') + 1),
        '1.0',
        'active'
    );
END;

-- 插入 MCP Server 时自动创建主资源记录
CREATE TRIGGER IF NOT EXISTS tr_mcp_insert_resource
BEFORE INSERT ON sys_mcp_servers
WHEN NOT EXISTS (SELECT 1 FROM sys_resources WHERE resource_id = NEW.server_id)
BEGIN
    INSERT INTO sys_resources (resource_id, resource_type, name, version, status)
    VALUES (
        NEW.server_id,
        'mcp_server',
        SUBSTR(NEW.server_id, INSTR(NEW.server_id, ':') + 1),
        '1.0',
        'active'
    );
END;

-- ==================== 3. 调用日志自动聚合 ====================

-- 调用记录插入后自动更新小时统计
CREATE TRIGGER IF NOT EXISTS tr_invocation_hourly_stats
AFTER INSERT ON sys_invocations
BEGIN
    INSERT INTO sys_stats_hourly (
        resource_id,
        hour,
        invocation_count,
        success_count,
        failure_count,
        total_tokens,
        total_cost_usd,
        avg_latency_ms
    )
    VALUES (
        NEW.resource_id,
        strftime('%Y-%m-%d %H:00:00', NEW.created_at),
        1,
        CASE WHEN NEW.status = 'success' THEN 1 ELSE 0 END,
        CASE WHEN NEW.status = 'failed' THEN 1 ELSE 0 END,
        COALESCE(NEW.input_tokens, 0) + COALESCE(NEW.output_tokens, 0),
        COALESCE(json_extract(NEW.metadata, '$.cost_usd'), 0),
        COALESCE(NEW.latency_ms, 0)
    )
    ON CONFLICT(resource_id, hour) DO UPDATE SET
        invocation_count = invocation_count + 1,
        success_count = success_count + CASE WHEN NEW.status = 'success' THEN 1 ELSE 0 END,
        failure_count = failure_count + CASE WHEN NEW.status = 'failed' THEN 1 ELSE 0 END,
        total_tokens = total_tokens + COALESCE(NEW.input_tokens, 0) + COALESCE(NEW.output_tokens, 0),
        total_cost_usd = total_cost_usd + COALESCE(json_extract(NEW.metadata, '$.cost_usd'), 0),
        avg_latency_ms = (avg_latency_ms * (invocation_count - 1) + COALESCE(NEW.latency_ms, 0)) / invocation_count;
END;

-- 调用记录插入后自动更新日统计
CREATE TRIGGER IF NOT EXISTS tr_invocation_daily_stats
AFTER INSERT ON sys_invocations
BEGIN
    INSERT INTO sys_stats_daily (
        resource_id,
        date,
        invocation_count,
        success_count,
        failure_count,
        total_tokens,
        total_cost_usd,
        avg_latency_ms,
        unique_sessions
    )
    VALUES (
        NEW.resource_id,
        date(NEW.created_at),
        1,
        CASE WHEN NEW.status = 'success' THEN 1 ELSE 0 END,
        CASE WHEN NEW.status = 'failed' THEN 1 ELSE 0 END,
        COALESCE(NEW.input_tokens, 0) + COALESCE(NEW.output_tokens, 0),
        COALESCE(json_extract(NEW.metadata, '$.cost_usd'), 0),
        COALESCE(NEW.latency_ms, 0),
        1
    )
    ON CONFLICT(resource_id, date) DO UPDATE SET
        invocation_count = invocation_count + 1,
        success_count = success_count + CASE WHEN NEW.status = 'success' THEN 1 ELSE 0 END,
        failure_count = failure_count + CASE WHEN NEW.status = 'failed' THEN 1 ELSE 0 END,
        total_tokens = total_tokens + COALESCE(NEW.input_tokens, 0) + COALESCE(NEW.output_tokens, 0),
        total_cost_usd = total_cost_usd + COALESCE(json_extract(NEW.metadata, '$.cost_usd'), 0),
        avg_latency_ms = (avg_latency_ms * (invocation_count - 1) + COALESCE(NEW.latency_ms, 0)) / invocation_count;
END;

-- ==================== 4. 偏好学习自动更新 ====================

-- 调用成功时更新偏好置信度
CREATE TRIGGER IF NOT EXISTS tr_preference_confidence_update
AFTER INSERT ON sys_invocations
WHEN NEW.status = 'success'
BEGIN
    UPDATE sys_preferences
    SET
        confidence = MIN(1.0, confidence + 0.01),
        usage_count = usage_count + 1,
        last_used_at = CURRENT_TIMESTAMP
    WHERE preference_type = (
        SELECT resource_type FROM sys_resources WHERE resource_id = NEW.resource_id
    )
    AND preference_value = json_quote(NEW.resource_id);
END;

-- ==================== 5. 上下文模式命中更新 ====================

-- 更新上下文模式命中计数
CREATE TRIGGER IF NOT EXISTS tr_context_pattern_hit
AFTER INSERT ON sys_invocations
WHEN NEW.status = 'success' AND NEW.metadata IS NOT NULL
BEGIN
    UPDATE sys_context_patterns
    SET
        hit_count = hit_count + 1,
        confidence = MIN(1.0, confidence + 0.005),
        last_hit_at = CURRENT_TIMESTAMP
    WHERE json_extract(NEW.metadata, '$.matched_pattern') = pattern_value;
END;

-- ==================== 6. 版本快照自动创建 ====================

-- 资源更新时创建版本快照
CREATE TRIGGER IF NOT EXISTS tr_resource_version_snapshot
AFTER UPDATE ON sys_resources
WHEN OLD.config IS NOT NEW.config OR OLD.status IS NOT NEW.status
BEGIN
    -- 将旧版本标记为非当前
    UPDATE sys_resource_versions
    SET is_current = FALSE
    WHERE resource_id = NEW.resource_id AND is_current = TRUE;

    -- 创建新版本快照
    INSERT INTO sys_resource_versions (
        resource_id,
        version,
        snapshot,
        change_summary,
        is_current
    )
    VALUES (
        NEW.resource_id,
        NEW.version || '.' || (
            SELECT COALESCE(MAX(CAST(SUBSTR(version, LENGTH(NEW.version) + 2) AS INTEGER)), 0) + 1
            FROM sys_resource_versions
            WHERE resource_id = NEW.resource_id
        ),
        json_object(
            'resource_id', NEW.resource_id,
            'resource_type', NEW.resource_type,
            'name', NEW.name,
            'version', NEW.version,
            'status', NEW.status,
            'config', json(NEW.config)
        ),
        'Auto snapshot on update',
        TRUE
    );
END;

-- ==================== 7. 配额超限检测 ====================

-- 调用后检查配额并记录警告
CREATE TRIGGER IF NOT EXISTS tr_quota_check
AFTER INSERT ON sys_invocations
BEGIN
    -- 插入警告消息到 messages 表 (如果配额超限)
    INSERT INTO messages (type, source, content, level)
    SELECT
        'quota',
        'metadata_system',
        json_object(
            'quota_name', q.quota_name,
            'resource_id', NEW.resource_id,
            'current_usage', COALESCE(
                (SELECT SUM(invocation_count) FROM sys_stats_daily
                 WHERE resource_id = NEW.resource_id AND date = date('now')),
                0
            ),
            'limit', q.limit_value,
            'action', q.action_on_exceed
        ),
        'warn'
    FROM sys_quotas q
    WHERE q.enabled = TRUE
    AND q.resource_id = NEW.resource_id
    AND (
        SELECT SUM(invocation_count) FROM sys_stats_daily
        WHERE resource_id = NEW.resource_id AND date = date('now')
    ) >= q.limit_value * q.warning_threshold;
END;

-- ==================== 8. 速率限制更新 ====================

-- 请求时更新速率限制计数
CREATE TRIGGER IF NOT EXISTS tr_rate_limit_update
AFTER INSERT ON sys_invocations
BEGIN
    UPDATE sys_rate_limits
    SET
        current_count = CASE
            WHEN window_start IS NULL OR
                 datetime(window_start, '+' || window_seconds || ' seconds') < datetime('now')
            THEN 1
            ELSE current_count + 1
        END,
        window_start = CASE
            WHEN window_start IS NULL OR
                 datetime(window_start, '+' || window_seconds || ' seconds') < datetime('now')
            THEN datetime('now')
            ELSE window_start
        END
    WHERE resource_id = NEW.resource_id AND enabled = TRUE;
END;

-- ==================== 9. 自演进检测触发器 ====================

-- 高失败率自动记录演进候选
CREATE TRIGGER IF NOT EXISTS tr_evolution_candidate_detection
AFTER INSERT ON sys_stats_daily
WHEN NEW.invocation_count >= 10
AND (1.0 * NEW.failure_count / NEW.invocation_count) > 0.2
BEGIN
    INSERT OR IGNORE INTO sys_evolution_log (
        resource_id,
        evolution_type,
        before_state,
        after_state,
        trigger_reason,
        status
    )
    VALUES (
        NEW.resource_id,
        'parameter_tuning',
        json_object(
            'failure_rate', 1.0 * NEW.failure_count / NEW.invocation_count,
            'avg_latency_ms', NEW.avg_latency_ms
        ),
        json_object('suggested', 'retry_policy_adjustment'),
        'High failure rate detected: ' || ROUND(100.0 * NEW.failure_count / NEW.invocation_count, 1) || '%',
        'pending'
    );
END;

-- ==================== 10. 清理触发器 ====================

-- 自动清理超过 90 天的调用日志
CREATE TRIGGER IF NOT EXISTS tr_cleanup_old_invocations
AFTER INSERT ON sys_invocations
WHEN (SELECT COUNT(*) FROM sys_invocations) > 100000
BEGIN
    DELETE FROM sys_invocations
    WHERE created_at < datetime('now', '-90 days')
    AND id NOT IN (
        SELECT id FROM sys_invocations
        ORDER BY created_at DESC
        LIMIT 50000
    );
END;

-- 自动清理超过 365 天的小时统计
CREATE TRIGGER IF NOT EXISTS tr_cleanup_old_hourly_stats
AFTER INSERT ON sys_stats_hourly
WHEN (SELECT COUNT(*) FROM sys_stats_hourly) > 50000
BEGIN
    DELETE FROM sys_stats_hourly
    WHERE hour < datetime('now', '-365 days');
END;
