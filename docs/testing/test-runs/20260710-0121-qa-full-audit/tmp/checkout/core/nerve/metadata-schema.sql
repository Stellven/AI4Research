-- Solar Metadata System - Schema Definition
-- Version: 1.1
-- Description: 系统表 - 资源自省、智能路由、成本优化、性能追踪、自我演进
-- Updated: 2026-01-30 - 添加 Shortcuts 集成

-- ==================== 1. 资源注册表 (8张表) ====================

-- 主资源表 (所有资源的统一入口)
CREATE TABLE IF NOT EXISTS sys_resources (
    resource_id TEXT PRIMARY KEY,           -- 格式: {type}:{name}:{version}
    resource_type TEXT NOT NULL CHECK(resource_type IN ('agent', 'skill', 'hook', 'tool', 'model', 'mcp_server', 'shortcut')),
    name TEXT NOT NULL,
    version TEXT DEFAULT '1.0',
    status TEXT DEFAULT 'active' CHECK(status IN ('active', 'deprecated', 'disabled', 'experimental')),
    description TEXT,
    config JSON,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(resource_type, name, version)
);

-- Agent 表
CREATE TABLE IF NOT EXISTS sys_agents (
    agent_id TEXT PRIMARY KEY REFERENCES sys_resources(resource_id) ON DELETE CASCADE,
    emoji TEXT,                             -- 显示图标
    role TEXT,                              -- 角色描述
    phases JSON,                            -- 适用阶段列表 ["P1", "P2"]
    tools JSON,                             -- 可用工具列表 ["Read", "Write", "Edit"]
    default_model TEXT DEFAULT 'sonnet',    -- 默认模型
    priority INTEGER DEFAULT 50,            -- 优先级 (1-100, 越高越优先)
    max_concurrent INTEGER DEFAULT 1,       -- 最大并发数
    timeout_seconds INTEGER DEFAULT 300,    -- 超时时间
    retry_policy JSON                       -- 重试策略 {"max_retries": 3, "backoff_ms": 1000}
);

-- Skill 表
CREATE TABLE IF NOT EXISTS sys_skills (
    skill_id TEXT PRIMARY KEY REFERENCES sys_resources(resource_id) ON DELETE CASCADE,
    user_invocable BOOLEAN DEFAULT FALSE,   -- 用户可直接调用 (/skill)
    command TEXT,                           -- 命令名 (如 "commit", "review")
    category TEXT,                          -- 分类 (dev, office, workflow, etc.)
    linked_agent TEXT,                      -- 关联的 Agent
    path TEXT,                              -- SKILL.md 文件路径
    args_schema JSON,                       -- 参数 schema
    examples JSON                           -- 使用示例
);

-- Hook 表
CREATE TABLE IF NOT EXISTS sys_hooks (
    hook_id TEXT PRIMARY KEY REFERENCES sys_resources(resource_id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,               -- 事件类型 (PreToolUse, PostToolUse, etc.)
    matcher JSON,                           -- 匹配规则 {"tools": ["Bash"], "pattern": "*.ts"}
    command TEXT NOT NULL,                  -- 执行的命令
    timeout_ms INTEGER DEFAULT 60000,       -- 超时毫秒
    enabled BOOLEAN DEFAULT TRUE,
    blocking BOOLEAN DEFAULT TRUE           -- 是否阻塞主流程
);

-- Tool 表
CREATE TABLE IF NOT EXISTS sys_tools (
    tool_id TEXT PRIMARY KEY REFERENCES sys_resources(resource_id) ON DELETE CASCADE,
    provider TEXT NOT NULL,                 -- 提供者 (builtin, mcp, custom)
    params_schema JSON,                     -- 参数 schema
    return_schema JSON,                     -- 返回值 schema
    side_effects JSON,                      -- 副作用描述 ["file_write", "network"]
    cost_weight REAL DEFAULT 1.0,           -- 成本权重 (相对值)
    is_dangerous BOOLEAN DEFAULT FALSE      -- 是否危险操作
);

-- Model 表
CREATE TABLE IF NOT EXISTS sys_models (
    model_id TEXT PRIMARY KEY REFERENCES sys_resources(resource_id) ON DELETE CASCADE,
    provider TEXT NOT NULL,                 -- 提供商 (anthropic, openai, deepseek)
    model_name TEXT NOT NULL,               -- 实际模型名称
    context_window INTEGER,                 -- 上下文窗口大小
    max_output_tokens INTEGER,              -- 最大输出 tokens
    input_price_per_mtok REAL,              -- 输入价格 $/百万tokens
    output_price_per_mtok REAL,             -- 输出价格 $/百万tokens
    cache_read_price_per_mtok REAL,         -- 缓存读取价格
    cache_write_price_per_mtok REAL,        -- 缓存写入价格
    capabilities JSON,                      -- 能力描述 ["vision", "code", "reasoning"]
    rate_limit_rpm INTEGER,                 -- 每分钟请求限制
    rate_limit_tpm INTEGER,                 -- 每分钟 token 限制
    is_default BOOLEAN DEFAULT FALSE        -- 是否默认模型
);

-- MCP Server 表
CREATE TABLE IF NOT EXISTS sys_mcp_servers (
    server_id TEXT PRIMARY KEY REFERENCES sys_resources(resource_id) ON DELETE CASCADE,
    transport TEXT NOT NULL CHECK(transport IN ('stdio', 'http', 'sse')),
    command TEXT,                           -- stdio 启动命令
    args JSON,                              -- 命令参数
    endpoint TEXT,                          -- HTTP/SSE 端点
    tools_provided JSON,                    -- 提供的工具列表
    env JSON,                               -- 环境变量
    auto_start BOOLEAN DEFAULT TRUE         -- 是否自动启动
);

-- Shortcut 表 (Apple Shortcuts - AI OS 技能执行层)
CREATE TABLE IF NOT EXISTS sys_shortcuts (
    shortcut_id TEXT PRIMARY KEY REFERENCES sys_resources(resource_id) ON DELETE CASCADE,
    category TEXT CHECK(category IN ('system', 'ai', 'data', 'workflow', 'custom')),

    -- 触发配置
    trigger_phrases JSON,                   -- 触发短语列表 ["提醒我", "设置提醒"]
    siri_phrase TEXT,                       -- Siri 触发短语

    -- 参数定义
    input_schema JSON,                      -- 输入参数 JSON Schema
    output_schema JSON,                     -- 输出 JSON Schema

    -- 权限与安全
    permission_level INTEGER DEFAULT 0,     -- 0:只读 1:本地写 2:通信 3:敏感
    requires_confirmation BOOLEAN DEFAULT FALSE,

    -- 执行配置
    timeout_seconds INTEGER DEFAULT 30,
    can_run_background BOOLEAN DEFAULT TRUE,
    supports_siri BOOLEAN DEFAULT TRUE,

    -- 安装状态
    is_installed BOOLEAN DEFAULT FALSE,     -- 是否已安装到系统 Shortcuts.app
    icloud_url TEXT                         -- iCloud 分享链接
);

-- Shortcut 自动化规则
CREATE TABLE IF NOT EXISTS sys_shortcut_automations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    shortcut_id TEXT NOT NULL REFERENCES sys_shortcuts(shortcut_id) ON DELETE CASCADE,
    automation_name TEXT NOT NULL,

    -- 触发条件
    trigger_type TEXT NOT NULL CHECK(trigger_type IN ('time', 'location', 'event', 'condition')),
    trigger_config JSON NOT NULL,           -- {"schedule": "0 7 * * *"} 或 {"region": "home", "event": "enter"}

    -- 执行配置
    params_template JSON,                   -- 参数模板
    enabled BOOLEAN DEFAULT TRUE,
    last_triggered_at DATETIME,

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ==================== 2. 依赖关系图 (3张表) ====================

-- 资源间依赖关系
CREATE TABLE IF NOT EXISTS sys_dependencies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_resource TEXT NOT NULL REFERENCES sys_resources(resource_id) ON DELETE CASCADE,
    to_resource TEXT NOT NULL REFERENCES sys_resources(resource_id) ON DELETE CASCADE,
    dependency_type TEXT NOT NULL CHECK(dependency_type IN ('requires', 'optional', 'conflicts', 'enhances')),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(from_resource, to_resource, dependency_type)
);

-- 阶段-Agent 映射
CREATE TABLE IF NOT EXISTS sys_phase_agents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phase TEXT NOT NULL,                    -- P1, P2, P3, P4, P5
    agent_id TEXT NOT NULL REFERENCES sys_agents(agent_id) ON DELETE CASCADE,
    is_primary BOOLEAN DEFAULT FALSE,       -- 是否主要 Agent
    priority INTEGER DEFAULT 50,            -- 优先级
    conditions JSON,                        -- 激活条件
    UNIQUE(phase, agent_id)
);

-- Agent-Tool 权限
CREATE TABLE IF NOT EXISTS sys_agent_tools (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT NOT NULL REFERENCES sys_agents(agent_id) ON DELETE CASCADE,
    tool_id TEXT NOT NULL REFERENCES sys_tools(tool_id) ON DELETE CASCADE,
    permission TEXT DEFAULT 'allow' CHECK(permission IN ('allow', 'deny', 'require_approval')),
    context_filter JSON,                    -- 上下文过滤条件
    UNIQUE(agent_id, tool_id)
);

-- ==================== 3. 使用统计 (5张表) ====================

-- 调用日志 (每次调用记录)
CREATE TABLE IF NOT EXISTS sys_invocations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    resource_id TEXT NOT NULL REFERENCES sys_resources(resource_id) ON DELETE CASCADE,
    invocation_type TEXT NOT NULL,          -- 调用类型
    session_id TEXT,                        -- 会话 ID
    task_id INTEGER,                        -- 任务 ID
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    latency_ms INTEGER,                     -- 延迟毫秒
    status TEXT CHECK(status IN ('success', 'failed', 'timeout', 'cancelled')),
    error_message TEXT,
    metadata JSON,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 小时级聚合
CREATE TABLE IF NOT EXISTS sys_stats_hourly (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    resource_id TEXT NOT NULL REFERENCES sys_resources(resource_id) ON DELETE CASCADE,
    hour DATETIME NOT NULL,                 -- 小时时间戳
    invocation_count INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    failure_count INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    total_cost_usd REAL DEFAULT 0,
    avg_latency_ms REAL DEFAULT 0,
    p50_latency_ms REAL DEFAULT 0,
    p95_latency_ms REAL DEFAULT 0,
    p99_latency_ms REAL DEFAULT 0,
    UNIQUE(resource_id, hour)
);

-- 日级聚合
CREATE TABLE IF NOT EXISTS sys_stats_daily (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    resource_id TEXT NOT NULL REFERENCES sys_resources(resource_id) ON DELETE CASCADE,
    date DATE NOT NULL,
    invocation_count INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    failure_count INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    total_cost_usd REAL DEFAULT 0,
    avg_latency_ms REAL DEFAULT 0,
    p50_latency_ms REAL DEFAULT 0,
    p95_latency_ms REAL DEFAULT 0,
    p99_latency_ms REAL DEFAULT 0,
    unique_sessions INTEGER DEFAULT 0,
    peak_hour INTEGER,                      -- 峰值小时 (0-23)
    UNIQUE(resource_id, date)
);

-- Gate 通过率统计
CREATE TABLE IF NOT EXISTS sys_gate_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    gate_name TEXT NOT NULL,                -- G1, G2, G3
    date DATE NOT NULL,
    total_attempts INTEGER DEFAULT 0,
    passed_count INTEGER DEFAULT 0,
    failed_count INTEGER DEFAULT 0,
    retry_count INTEGER DEFAULT 0,
    avg_retry_count REAL DEFAULT 0,
    common_failure_reasons JSON,            -- 常见失败原因统计
    UNIQUE(gate_name, date)
);

-- 阶段转换统计
CREATE TABLE IF NOT EXISTS sys_phase_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_phase TEXT NOT NULL,
    to_phase TEXT NOT NULL,
    date DATE NOT NULL,
    transition_count INTEGER DEFAULT 0,
    avg_duration_seconds REAL DEFAULT 0,
    min_duration_seconds INTEGER,
    max_duration_seconds INTEGER,
    success_rate REAL DEFAULT 0,
    UNIQUE(from_phase, to_phase, date)
);

-- ==================== 4. 路由规则 (4张表) ====================

-- 模型选择规则
CREATE TABLE IF NOT EXISTS sys_routing_model (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_name TEXT NOT NULL,
    priority INTEGER DEFAULT 50,            -- 优先级 (越高越先匹配)
    conditions JSON NOT NULL,               -- 匹配条件
    target_model TEXT NOT NULL,             -- 目标模型 ID
    fallback_model TEXT,                    -- 降级模型 ID
    enabled BOOLEAN DEFAULT TRUE,
    description TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Agent 选择规则
CREATE TABLE IF NOT EXISTS sys_routing_agent (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_name TEXT NOT NULL,
    priority INTEGER DEFAULT 50,
    conditions JSON NOT NULL,               -- {"context_pattern": "*.cpp", "complexity": "high"}
    target_agent TEXT NOT NULL,             -- 目标 Agent ID
    fallback_agent TEXT,
    enabled BOOLEAN DEFAULT TRUE,
    description TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 工具选择规则
CREATE TABLE IF NOT EXISTS sys_routing_tool (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_name TEXT NOT NULL,
    priority INTEGER DEFAULT 50,
    conditions JSON NOT NULL,               -- {"operation": "search", "scope": "codebase"}
    target_tool TEXT NOT NULL,
    fallback_tool TEXT,
    enabled BOOLEAN DEFAULT TRUE,
    description TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 意图路由规则 (自然语言 → 资源映射)
CREATE TABLE IF NOT EXISTS sys_routing_intent (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    intent_pattern TEXT NOT NULL,           -- 意图模式: "remind:*", "translate:*", "weather:*"
    keywords JSON,                          -- 触发关键词: ["提醒我", "别忘了", "记得"]
    target_type TEXT NOT NULL CHECK(target_type IN ('skill', 'shortcut', 'agent', 'mcp_server', 'workflow')),
    target_id TEXT NOT NULL,                -- 目标资源 ID
    priority INTEGER DEFAULT 50,            -- 优先级 (越高越先匹配)
    param_mapping JSON,                     -- 参数映射规则: {"title": "$object", "datetime": "$time"}
    confidence_threshold REAL DEFAULT 0.7,  -- 最低置信度
    enabled BOOLEAN DEFAULT TRUE,
    description TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(intent_pattern, target_type, target_id)
);

-- ==================== 5. 约束与配额 (3张表) ====================

-- 资源配额
CREATE TABLE IF NOT EXISTS sys_quotas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    quota_name TEXT NOT NULL,
    resource_type TEXT,                     -- NULL 表示全局
    resource_id TEXT,                       -- NULL 表示该类型所有资源
    quota_type TEXT NOT NULL CHECK(quota_type IN ('tokens', 'cost', 'invocations', 'concurrent')),
    period TEXT CHECK(period IN ('hourly', 'daily', 'weekly', 'monthly', 'total')),
    limit_value REAL NOT NULL,
    warning_threshold REAL DEFAULT 0.8,     -- 警告阈值 (80%)
    action_on_exceed TEXT DEFAULT 'warn' CHECK(action_on_exceed IN ('warn', 'block', 'throttle', 'fallback')),
    fallback_config JSON,                   -- 超限时的降级配置
    enabled BOOLEAN DEFAULT TRUE,
    UNIQUE(quota_name)
);

-- 访问控制
CREATE TABLE IF NOT EXISTS sys_access_control (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_type TEXT NOT NULL CHECK(subject_type IN ('agent', 'skill', 'hook', 'phase', 'shortcut')),
    subject_id TEXT NOT NULL,
    object_type TEXT NOT NULL CHECK(object_type IN ('tool', 'model', 'mcp_server', 'skill', 'shortcut')),
    object_id TEXT NOT NULL,
    permission TEXT DEFAULT 'allow' CHECK(permission IN ('allow', 'deny', 'require_approval')),
    conditions JSON,                        -- 条件限制
    reason TEXT,                            -- 设置原因
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(subject_type, subject_id, object_type, object_id)
);

-- 速率限制
CREATE TABLE IF NOT EXISTS sys_rate_limits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    resource_id TEXT REFERENCES sys_resources(resource_id) ON DELETE CASCADE,
    window_seconds INTEGER NOT NULL,        -- 时间窗口
    max_requests INTEGER NOT NULL,          -- 最大请求数
    burst_size INTEGER,                     -- 突发容量
    current_count INTEGER DEFAULT 0,
    window_start DATETIME,
    enabled BOOLEAN DEFAULT TRUE
);

-- ==================== 6. 版本历史 (3张表) ====================

-- 资源版本快照
CREATE TABLE IF NOT EXISTS sys_resource_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    resource_id TEXT NOT NULL,
    version TEXT NOT NULL,
    snapshot JSON NOT NULL,                 -- 完整配置快照
    change_summary TEXT,
    changed_by TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    is_current BOOLEAN DEFAULT TRUE,
    UNIQUE(resource_id, version)
);

-- 自我演进历史
CREATE TABLE IF NOT EXISTS sys_evolution_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    resource_id TEXT NOT NULL REFERENCES sys_resources(resource_id) ON DELETE CASCADE,
    evolution_type TEXT NOT NULL CHECK(evolution_type IN ('parameter_tuning', 'model_switch', 'routing_update', 'quota_adjust')),
    before_state JSON NOT NULL,
    after_state JSON NOT NULL,
    trigger_reason TEXT,                    -- 触发原因
    impact_metrics JSON,                    -- 影响指标
    applied_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    rollback_at DATETIME,                   -- 回滚时间 (如果有)
    status TEXT DEFAULT 'applied' CHECK(status IN ('applied', 'rolled_back', 'pending', 'failed'))
);

-- Schema 版本
CREATE TABLE IF NOT EXISTS sys_schema_migrations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version TEXT NOT NULL UNIQUE,
    description TEXT,
    applied_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    checksum TEXT                           -- SQL 内容的 hash
);

-- ==================== 7. 偏好学习 (2张表) ====================

-- 用户偏好
CREATE TABLE IF NOT EXISTS sys_preferences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    preference_type TEXT NOT NULL,          -- agent, skill, model, workflow
    preference_key TEXT NOT NULL,
    preference_value JSON NOT NULL,
    context JSON,                           -- 上下文条件
    confidence REAL DEFAULT 0.5,            -- 置信度 (0-1)
    usage_count INTEGER DEFAULT 1,
    last_used_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(preference_type, preference_key, context)
);

-- 上下文模式
CREATE TABLE IF NOT EXISTS sys_context_patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern_type TEXT NOT NULL,             -- file_extension, directory, keyword, time
    pattern_value TEXT NOT NULL,            -- "*.cpp", "/tests/*", "benchmark"
    recommended_resources JSON NOT NULL,    -- 推荐资源列表 [{"type": "skill", "id": "build"}]
    confidence REAL DEFAULT 0.5,
    hit_count INTEGER DEFAULT 0,
    miss_count INTEGER DEFAULT 0,
    last_hit_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(pattern_type, pattern_value)
);

-- ==================== 索引 ====================

-- 资源表索引
CREATE INDEX IF NOT EXISTS idx_resources_type ON sys_resources(resource_type);
CREATE INDEX IF NOT EXISTS idx_resources_status ON sys_resources(status);
CREATE INDEX IF NOT EXISTS idx_resources_name ON sys_resources(name);

-- Skills 索引
CREATE INDEX IF NOT EXISTS idx_skills_command ON sys_skills(command);
CREATE INDEX IF NOT EXISTS idx_skills_category ON sys_skills(category);
CREATE INDEX IF NOT EXISTS idx_skills_user_invocable ON sys_skills(user_invocable);

-- Hooks 索引
CREATE INDEX IF NOT EXISTS idx_hooks_event ON sys_hooks(event_type);
CREATE INDEX IF NOT EXISTS idx_hooks_enabled ON sys_hooks(enabled);

-- Shortcuts 索引
CREATE INDEX IF NOT EXISTS idx_shortcuts_category ON sys_shortcuts(category);
CREATE INDEX IF NOT EXISTS idx_shortcuts_installed ON sys_shortcuts(is_installed);
CREATE INDEX IF NOT EXISTS idx_shortcuts_siri ON sys_shortcuts(supports_siri);

-- Shortcut Automations 索引
CREATE INDEX IF NOT EXISTS idx_shortcut_auto_trigger ON sys_shortcut_automations(trigger_type);
CREATE INDEX IF NOT EXISTS idx_shortcut_auto_enabled ON sys_shortcut_automations(enabled);

-- 依赖索引
CREATE INDEX IF NOT EXISTS idx_deps_from ON sys_dependencies(from_resource);
CREATE INDEX IF NOT EXISTS idx_deps_to ON sys_dependencies(to_resource);
CREATE INDEX IF NOT EXISTS idx_deps_type ON sys_dependencies(dependency_type);

-- 调用日志索引
CREATE INDEX IF NOT EXISTS idx_invocations_resource ON sys_invocations(resource_id);
CREATE INDEX IF NOT EXISTS idx_invocations_created ON sys_invocations(created_at);
CREATE INDEX IF NOT EXISTS idx_invocations_status ON sys_invocations(status);
CREATE INDEX IF NOT EXISTS idx_invocations_session ON sys_invocations(session_id);

-- 统计索引
CREATE INDEX IF NOT EXISTS idx_stats_hourly_hour ON sys_stats_hourly(hour);
CREATE INDEX IF NOT EXISTS idx_stats_daily_date ON sys_stats_daily(date);
CREATE INDEX IF NOT EXISTS idx_gate_stats_date ON sys_gate_stats(date);
CREATE INDEX IF NOT EXISTS idx_phase_stats_date ON sys_phase_stats(date);

-- 路由索引
CREATE INDEX IF NOT EXISTS idx_routing_model_priority ON sys_routing_model(priority DESC);
CREATE INDEX IF NOT EXISTS idx_routing_agent_priority ON sys_routing_agent(priority DESC);
CREATE INDEX IF NOT EXISTS idx_routing_tool_priority ON sys_routing_tool(priority DESC);
CREATE INDEX IF NOT EXISTS idx_routing_intent_priority ON sys_routing_intent(priority DESC);
CREATE INDEX IF NOT EXISTS idx_routing_intent_pattern ON sys_routing_intent(intent_pattern);
CREATE INDEX IF NOT EXISTS idx_routing_intent_target ON sys_routing_intent(target_type, target_id);

-- 配额索引
CREATE INDEX IF NOT EXISTS idx_quotas_type ON sys_quotas(quota_type);
CREATE INDEX IF NOT EXISTS idx_quotas_resource ON sys_quotas(resource_id);

-- 演进日志索引
CREATE INDEX IF NOT EXISTS idx_evolution_resource ON sys_evolution_log(resource_id);
CREATE INDEX IF NOT EXISTS idx_evolution_type ON sys_evolution_log(evolution_type);
CREATE INDEX IF NOT EXISTS idx_evolution_applied ON sys_evolution_log(applied_at);

-- 偏好索引
CREATE INDEX IF NOT EXISTS idx_preferences_type ON sys_preferences(preference_type);
CREATE INDEX IF NOT EXISTS idx_preferences_confidence ON sys_preferences(confidence DESC);

-- 上下文模式索引
CREATE INDEX IF NOT EXISTS idx_patterns_type ON sys_context_patterns(pattern_type);
CREATE INDEX IF NOT EXISTS idx_patterns_confidence ON sys_context_patterns(confidence DESC);

-- 记录 schema 版本
INSERT OR IGNORE INTO sys_schema_migrations (version, description)
VALUES ('1.0.0', 'Initial metadata system schema');

INSERT OR IGNORE INTO sys_schema_migrations (version, description)
VALUES ('1.1.0', 'Add Shortcuts integration: sys_shortcuts, sys_shortcut_automations, sys_routing_intent');
