-- Solar Shortcuts Integration Schema
-- Version: 1.0
-- Description: Apple Shortcuts 作为 AI OS 技能执行层

-- ==================== 快捷指令注册表 ====================

-- Shortcut 定义表
CREATE TABLE IF NOT EXISTS sys_shortcuts (
    shortcut_id TEXT PRIMARY KEY,           -- 'solar_set_reminder'
    name TEXT NOT NULL,                     -- 显示名称
    description TEXT,                       -- 功能描述
    category TEXT CHECK(category IN ('system', 'ai', 'data', 'workflow', 'custom')),

    -- 触发配置
    trigger_phrases TEXT,                   -- JSON: ["提醒我", "设置提醒"]
    siri_phrase TEXT,                       -- Siri 触发短语

    -- 参数定义
    input_schema TEXT,                      -- JSON Schema for parameters
    output_schema TEXT,                     -- JSON Schema for output

    -- 权限与安全
    permission_level INTEGER DEFAULT 0,     -- 0:只读 1:本地写 2:通信 3:敏感
    requires_confirmation BOOLEAN DEFAULT FALSE,

    -- 执行配置
    timeout_seconds INTEGER DEFAULT 30,
    can_run_background BOOLEAN DEFAULT TRUE,
    supports_siri BOOLEAN DEFAULT TRUE,

    -- 状态
    is_installed BOOLEAN DEFAULT FALSE,     -- 是否已安装到系统
    is_enabled BOOLEAN DEFAULT TRUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Shortcut 执行历史
CREATE TABLE IF NOT EXISTS sys_shortcut_executions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    shortcut_id TEXT NOT NULL REFERENCES sys_shortcuts(shortcut_id),
    user_query TEXT,                        -- 原始用户输入
    intent_json TEXT,                       -- 解析后的意图
    params_json TEXT,                       -- 执行参数
    result_json TEXT,                       -- 执行结果
    success BOOLEAN,
    error_message TEXT,
    execution_time_ms INTEGER,
    triggered_by TEXT,                      -- 'siri', 'solar', 'automation', 'manual'
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Shortcut 自动化规则
CREATE TABLE IF NOT EXISTS sys_shortcut_automations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    shortcut_id TEXT NOT NULL REFERENCES sys_shortcuts(shortcut_id),
    name TEXT NOT NULL,

    -- 触发条件
    trigger_type TEXT CHECK(trigger_type IN ('time', 'location', 'event', 'condition')),
    trigger_config TEXT,                    -- JSON: trigger 配置

    -- 执行配置
    params_template TEXT,                   -- JSON: 参数模板
    is_enabled BOOLEAN DEFAULT TRUE,
    last_triggered_at DATETIME,

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Intent 到 Shortcut 映射表
CREATE TABLE IF NOT EXISTS sys_intent_shortcut_map (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    intent_pattern TEXT NOT NULL,           -- 意图模式 (动词+对象)
    shortcut_id TEXT NOT NULL REFERENCES sys_shortcuts(shortcut_id),
    priority INTEGER DEFAULT 50,            -- 优先级
    param_mapping TEXT,                     -- JSON: 参数映射规则
    conditions TEXT,                        -- JSON: 匹配条件

    UNIQUE(intent_pattern, shortcut_id)
);

-- ==================== 索引 ====================

CREATE INDEX IF NOT EXISTS idx_shortcuts_category ON sys_shortcuts(category);
CREATE INDEX IF NOT EXISTS idx_shortcuts_installed ON sys_shortcuts(is_installed);
CREATE INDEX IF NOT EXISTS idx_executions_shortcut ON sys_shortcut_executions(shortcut_id);
CREATE INDEX IF NOT EXISTS idx_executions_time ON sys_shortcut_executions(created_at);
CREATE INDEX IF NOT EXISTS idx_automations_trigger ON sys_shortcut_automations(trigger_type);
CREATE INDEX IF NOT EXISTS idx_intent_map_pattern ON sys_intent_shortcut_map(intent_pattern);

-- ==================== 视图 ====================

-- Shortcut 执行统计
CREATE VIEW IF NOT EXISTS v_shortcut_stats AS
SELECT
    s.shortcut_id,
    s.name,
    s.category,
    COUNT(e.id) as total_executions,
    SUM(CASE WHEN e.success THEN 1 ELSE 0 END) as successful_executions,
    ROUND(AVG(CASE WHEN e.success THEN 1.0 ELSE 0.0 END) * 100, 1) as success_rate,
    ROUND(AVG(e.execution_time_ms), 0) as avg_execution_ms,
    MAX(e.created_at) as last_executed
FROM sys_shortcuts s
LEFT JOIN sys_shortcut_executions e ON s.shortcut_id = e.shortcut_id
GROUP BY s.shortcut_id;

-- 可用 Shortcuts 列表
CREATE VIEW IF NOT EXISTS v_available_shortcuts AS
SELECT
    shortcut_id,
    name,
    description,
    category,
    trigger_phrases,
    siri_phrase,
    permission_level,
    CASE permission_level
        WHEN 0 THEN '只读'
        WHEN 1 THEN '本地写入'
        WHEN 2 THEN '通信'
        WHEN 3 THEN '敏感'
    END as permission_desc
FROM sys_shortcuts
WHERE is_installed = TRUE AND is_enabled = TRUE
ORDER BY category, name;

-- 活跃自动化
CREATE VIEW IF NOT EXISTS v_active_automations AS
SELECT
    a.id,
    a.name as automation_name,
    s.name as shortcut_name,
    a.trigger_type,
    a.trigger_config,
    a.last_triggered_at
FROM sys_shortcut_automations a
JOIN sys_shortcuts s ON a.shortcut_id = s.shortcut_id
WHERE a.is_enabled = TRUE
ORDER BY a.trigger_type, a.name;

-- 意图路由表
CREATE VIEW IF NOT EXISTS v_intent_routing AS
SELECT
    m.intent_pattern,
    s.shortcut_id,
    s.name as shortcut_name,
    s.category,
    m.priority,
    m.param_mapping
FROM sys_intent_shortcut_map m
JOIN sys_shortcuts s ON m.shortcut_id = s.shortcut_id
WHERE s.is_installed = TRUE AND s.is_enabled = TRUE
ORDER BY m.priority DESC;

-- ==================== 触发器 ====================

-- 更新时间戳
CREATE TRIGGER IF NOT EXISTS tr_shortcut_updated
AFTER UPDATE ON sys_shortcuts
BEGIN
    UPDATE sys_shortcuts SET updated_at = CURRENT_TIMESTAMP
    WHERE shortcut_id = NEW.shortcut_id;
END;

-- 记录自动化触发时间
CREATE TRIGGER IF NOT EXISTS tr_automation_triggered
AFTER INSERT ON sys_shortcut_executions
WHEN NEW.triggered_by = 'automation'
BEGIN
    UPDATE sys_shortcut_automations
    SET last_triggered_at = CURRENT_TIMESTAMP
    WHERE shortcut_id = NEW.shortcut_id;
END;
