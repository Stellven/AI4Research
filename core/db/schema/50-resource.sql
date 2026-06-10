-- Solar Resource Metadata System
-- 系统资源元数据：本地 + 远程 + 可发现
-- 原则：系统资源优先，LLM 是最后手段

--------------------------------------------------------------------------------
-- 1. 核心资源表
--------------------------------------------------------------------------------

-- 资源主表：所有可用资源的统一视图
CREATE TABLE IF NOT EXISTS sys_resources (
    resource_id TEXT PRIMARY KEY,

    -- 分类
    layer TEXT NOT NULL,                    -- 'local' | 'remote' | 'discovered'
    category TEXT NOT NULL,                 -- 'os_service' | 'cli_tool' | 'shortcut' | 'api' | 'mcp' | 'agent' | 'skill'

    -- 基本信息
    name TEXT NOT NULL,
    description TEXT,
    keywords TEXT,                          -- JSON array: ["weather", "天气", "wttr"]

    -- 执行信息
    executor TEXT NOT NULL,                 -- 'launchd' | 'shell' | 'shortcut' | 'http' | 'mcp' | 'bun' | 'llm'
    command_template TEXT,                  -- "curl 'wttr.in/{city}?format=3'"
    config TEXT,                            -- JSON: 配置参数

    -- 成本指标 (核心！)
    cost_type TEXT DEFAULT 'free',          -- 'free' | 'token' | 'api_call' | 'money'
    cost_per_call REAL DEFAULT 0,           -- 每次调用成本
    latency_ms INTEGER DEFAULT 0,           -- 预估延迟

    -- 可用性
    availability TEXT DEFAULT 'available',  -- 'available' | 'needs_setup' | 'unavailable' | 'discovered'
    setup_command TEXT,                     -- 如何安装/启用
    requirements TEXT,                      -- JSON: 依赖项

    -- 元信息
    source TEXT,                            -- 来源: 'system_scan' | 'manual' | 'search' | 'skill_market'
    discovered_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_verified DATETIME,
    verified_by TEXT                        -- 'auto_scan' | 'manual_test' | 'usage'
);

-- 资源能力映射：资源能做什么
CREATE TABLE IF NOT EXISTS sys_resource_capabilities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    resource_id TEXT NOT NULL,

    -- 能力定义
    intent TEXT NOT NULL,                   -- 用户意图: "查天气" | "发邮件" | "设提醒"
    action TEXT NOT NULL,                   -- 动作: "query" | "create" | "send" | "update"
    object TEXT NOT NULL,                   -- 对象: "weather" | "email" | "reminder"

    -- 匹配
    match_patterns TEXT,                    -- JSON array: 正则模式
    match_score REAL DEFAULT 1.0,           -- 基础匹配分数

    -- 效果
    success_rate REAL DEFAULT 1.0,          -- 历史成功率
    avg_latency_ms INTEGER,

    FOREIGN KEY (resource_id) REFERENCES sys_resources(resource_id)
);

-- 资源使用统计
CREATE TABLE IF NOT EXISTS sys_resource_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    resource_id TEXT NOT NULL,

    -- 调用信息
    called_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    intent TEXT,
    input_summary TEXT,                     -- 输入摘要

    -- 结果
    success INTEGER DEFAULT 1,
    latency_ms INTEGER,
    cost_actual REAL,
    output_summary TEXT,                    -- 输出摘要
    error TEXT,

    -- 用于学习
    user_feedback TEXT,                     -- 'good' | 'bad' | null

    FOREIGN KEY (resource_id) REFERENCES sys_resources(resource_id)
);

--------------------------------------------------------------------------------
-- 2. 资源发现表
--------------------------------------------------------------------------------

-- 搜索发现的资源（待评估）
CREATE TABLE IF NOT EXISTS sys_resource_discoveries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- 来源
    search_query TEXT,
    source_type TEXT NOT NULL,              -- 'web_search' | 'skill_market' | 'mcp_registry' | 'github' | 'api_directory'
    source_url TEXT,

    -- 发现的资源
    name TEXT NOT NULL,
    description TEXT,
    category TEXT,

    -- 评估
    relevance_score REAL,                   -- 与需求的相关度
    quality_score REAL,                     -- 质量评分
    cost_estimate TEXT,                     -- 'free' | 'freemium' | 'paid'

    -- 状态
    status TEXT DEFAULT 'discovered',       -- 'discovered' | 'evaluating' | 'adopted' | 'rejected'
    adopted_as TEXT,                        -- 如果采纳，对应的 resource_id
    rejection_reason TEXT,

    discovered_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    evaluated_at DATETIME
);

-- 资源搜索历史（学习用户需要什么）
CREATE TABLE IF NOT EXISTS sys_resource_search_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    user_intent TEXT NOT NULL,              -- 用户原始意图
    search_query TEXT,                      -- 搜索词
    search_source TEXT,                     -- 搜索来源

    results_count INTEGER,
    best_match_id TEXT,
    best_match_score REAL,

    -- 结果
    action_taken TEXT,                      -- 'found_local' | 'found_remote' | 'discovered_new' | 'no_match'
    resource_used TEXT,

    searched_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

--------------------------------------------------------------------------------
-- 3. 资源优先级与路由
--------------------------------------------------------------------------------

-- 资源优先级规则
CREATE TABLE IF NOT EXISTS sys_resource_priority (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- 匹配条件
    intent_pattern TEXT,                    -- 正则匹配意图
    context_pattern TEXT,                   -- 上下文条件

    -- 优先级
    layer_priority TEXT NOT NULL,           -- JSON array: ["local", "remote", "discovered"]
    category_priority TEXT NOT NULL,        -- JSON array: ["shortcut", "cli_tool", "api", "mcp", "agent"]

    -- 约束
    max_cost REAL,                          -- 最大允许成本
    max_latency_ms INTEGER,                 -- 最大允许延迟

    -- 生效
    enabled INTEGER DEFAULT 1,
    priority_order INTEGER DEFAULT 100
);

-- 默认优先级（插入基础数据）
INSERT OR IGNORE INTO sys_resource_priority (id, intent_pattern, layer_priority, category_priority, max_latency_ms) VALUES
(1, '.*', '["local", "remote", "discovered"]', '["shortcut", "os_service", "cli_tool", "api", "mcp", "skill", "agent"]', 5000);

--------------------------------------------------------------------------------
-- 4. 核心视图
--------------------------------------------------------------------------------

-- 可用资源视图（按成本排序）
CREATE VIEW IF NOT EXISTS v_available_resources AS
SELECT
    r.*,
    COALESCE(u.call_count, 0) as call_count,
    COALESCE(u.success_rate, 1.0) as actual_success_rate,
    COALESCE(u.avg_latency, r.latency_ms) as actual_latency_ms,
    -- 综合评分: 成本低 + 延迟低 + 成功率高 = 分数高
    (1.0 / (1 + r.cost_per_call)) * 0.3 +
    (1.0 / (1 + r.latency_ms / 1000.0)) * 0.3 +
    COALESCE(u.success_rate, 1.0) * 0.4 as efficiency_score
FROM sys_resources r
LEFT JOIN (
    SELECT
        resource_id,
        COUNT(*) as call_count,
        AVG(success) as success_rate,
        AVG(latency_ms) as avg_latency
    FROM sys_resource_usage
    WHERE called_at > datetime('now', '-30 days')
    GROUP BY resource_id
) u ON r.resource_id = u.resource_id
WHERE r.availability = 'available'
ORDER BY
    CASE r.layer
        WHEN 'local' THEN 1
        WHEN 'remote' THEN 2
        ELSE 3
    END,
    efficiency_score DESC;

-- 资源选择决策视图
CREATE VIEW IF NOT EXISTS v_resource_selection AS
SELECT
    c.intent,
    c.action,
    c.object,
    r.resource_id,
    r.name,
    r.layer,
    r.category,
    r.cost_type,
    r.cost_per_call,
    r.latency_ms,
    c.success_rate,
    -- 选择分数
    c.match_score *
    (1.0 / (1 + r.cost_per_call)) *
    (1.0 / (1 + r.latency_ms / 1000.0)) *
    c.success_rate as selection_score
FROM sys_resource_capabilities c
JOIN sys_resources r ON c.resource_id = r.resource_id
WHERE r.availability = 'available'
ORDER BY selection_score DESC;

-- 待发现资源（用户需要但没有的能力）
CREATE VIEW IF NOT EXISTS v_capability_gaps AS
SELECT
    user_intent,
    COUNT(*) as request_count,
    MAX(searched_at) as last_requested,
    GROUP_CONCAT(DISTINCT search_source) as tried_sources
FROM sys_resource_search_log
WHERE action_taken = 'no_match'
GROUP BY user_intent
ORDER BY request_count DESC;

-- 资源健康状态
CREATE VIEW IF NOT EXISTS v_resource_health AS
SELECT
    r.resource_id,
    r.name,
    r.layer,
    r.category,
    r.availability,
    r.last_verified,
    julianday('now') - julianday(r.last_verified) as days_since_verified,
    COALESCE(u.recent_success_rate, 1.0) as recent_success_rate,
    COALESCE(u.recent_calls, 0) as recent_calls,
    CASE
        WHEN r.availability != 'available' THEN 'unavailable'
        WHEN julianday('now') - julianday(r.last_verified) > 7 THEN 'stale'
        WHEN COALESCE(u.recent_success_rate, 1.0) < 0.5 THEN 'degraded'
        ELSE 'healthy'
    END as health_status
FROM sys_resources r
LEFT JOIN (
    SELECT
        resource_id,
        AVG(success) as recent_success_rate,
        COUNT(*) as recent_calls
    FROM sys_resource_usage
    WHERE called_at > datetime('now', '-7 days')
    GROUP BY resource_id
) u ON r.resource_id = u.resource_id;

--------------------------------------------------------------------------------
-- 5. 学习原则表
--------------------------------------------------------------------------------

-- Solar 学习到的原则
CREATE TABLE IF NOT EXISTS sys_learned_principles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    principle_id TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,

    -- 来源
    learned_from TEXT,                      -- 场景/对话
    learned_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    -- 应用
    applies_to TEXT,                        -- JSON array: 适用场景
    implementation TEXT,                    -- 如何实现

    -- 验证
    validated INTEGER DEFAULT 0,
    validation_result TEXT,

    -- 优先级
    importance TEXT DEFAULT 'normal'        -- 'critical' | 'high' | 'normal' | 'low'
);

-- 插入今天学到的原则
INSERT OR IGNORE INTO sys_learned_principles (principle_id, title, description, learned_from, applies_to, implementation, importance) VALUES
('resource_first', '系统资源优先原则',
 '凡是消耗资源的任务，首先检查底层系统是否支持，通过简单编程使用系统资源，LLM 是最后手段',
 '2026-02-03 安全检测系统设计',
 '["task_execution", "automation", "monitoring"]',
 '1. 查询 sys_resources 找本地资源\n2. 本地没有则搜索远程资源\n3. 远程没有则发现新资源\n4. 都没有才用 LLM',
 'critical');

--------------------------------------------------------------------------------
-- 索引
--------------------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_resources_layer ON sys_resources(layer);
CREATE INDEX IF NOT EXISTS idx_resources_category ON sys_resources(category);
CREATE INDEX IF NOT EXISTS idx_resources_availability ON sys_resources(availability);
CREATE INDEX IF NOT EXISTS idx_capabilities_intent ON sys_resource_capabilities(intent);
CREATE INDEX IF NOT EXISTS idx_usage_resource ON sys_resource_usage(resource_id);
CREATE INDEX IF NOT EXISTS idx_usage_time ON sys_resource_usage(called_at);
CREATE INDEX IF NOT EXISTS idx_discoveries_status ON sys_resource_discoveries(status);
CREATE INDEX IF NOT EXISTS idx_search_log_intent ON sys_resource_search_log(user_intent);
