-- ============================================================
-- Solar 消息监听系统 Schema
-- ============================================================

-- 消息任务表
CREATE TABLE IF NOT EXISTS bl_message_tasks (
    task_id TEXT PRIMARY KEY,
    message_id TEXT,           -- iMessage 消息 ID
    sender TEXT NOT NULL,      -- 发送者 (手机号或邮箱)
    content TEXT NOT NULL,     -- 原始消息内容
    priority TEXT DEFAULT 'temporary', -- high/scheduled/temporary
    intent_type TEXT,          -- task/query/control
    intent_action TEXT,        -- 具体动作 (weather_query, list_backlog, etc.)
    intent_params TEXT,        -- JSON 格式参数
    status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'running', 'done', 'failed', 'cancelled', 'deferred')),
    result TEXT,               -- 执行结果
    error TEXT,                -- 错误信息
    execution_time_ms INTEGER, -- 执行耗时 (毫秒)
    execution_tokens INTEGER,  -- Token 消耗
    estimated_tokens INTEGER,  -- 预估 Token
    deferred_reason TEXT,      -- 延迟原因
    deferred_until DATETIME,   -- 延迟到什么时候
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    started_at DATETIME,
    completed_at DATETIME
);

-- 消息触发器白名单
CREATE TABLE IF NOT EXISTS bl_message_triggers (
    trigger_id TEXT PRIMARY KEY,
    contact_name TEXT NOT NULL,  -- 联系人名称
    contact_phone TEXT,          -- 手机号 (格式: +86xxxxxxxxxxx)
    contact_email TEXT,          -- 邮箱
    enabled BOOLEAN DEFAULT true,
    priority INTEGER DEFAULT 50, -- 优先级 0-100
    allowed_actions TEXT,        -- JSON 数组，允许的动作类型
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 消息处理统计
CREATE TABLE IF NOT EXISTS bl_message_stats (
    date TEXT PRIMARY KEY,       -- YYYY-MM-DD
    total_messages INTEGER DEFAULT 0,
    successful_tasks INTEGER DEFAULT 0,
    failed_tasks INTEGER DEFAULT 0,
    avg_execution_time_ms REAL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 常设任务表 (定期执行的任务)
CREATE TABLE IF NOT EXISTS bl_scheduled_tasks (
    task_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,          -- 任务名称
    description TEXT,            -- 任务描述
    action TEXT NOT NULL,        -- 动作类型 (moltbook_check, zhihu_analysis, etc.)
    schedule_interval_sec INTEGER NOT NULL, -- 执行间隔 (秒)
    priority INTEGER DEFAULT 50, -- 优先级 0-100
    enabled BOOLEAN DEFAULT true,
    last_executed DATETIME,      -- 最后执行时间
    next_execution DATETIME,     -- 下次执行时间
    execution_count INTEGER DEFAULT 0,
    failure_count INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_message_tasks_sender ON bl_message_tasks(sender);
CREATE INDEX IF NOT EXISTS idx_message_tasks_status ON bl_message_tasks(status);
CREATE INDEX IF NOT EXISTS idx_message_tasks_created ON bl_message_tasks(created_at);
CREATE INDEX IF NOT EXISTS idx_message_triggers_enabled ON bl_message_triggers(enabled);

-- 视图: 今日任务统计
CREATE VIEW IF NOT EXISTS v_message_tasks_today AS
SELECT
    COUNT(*) as total,
    SUM(CASE WHEN status = 'done' THEN 1 ELSE 0 END) as completed,
    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
    SUM(CASE WHEN status = 'running' THEN 1 ELSE 0 END) as running,
    AVG(execution_time_ms) as avg_time_ms
FROM bl_message_tasks
WHERE DATE(created_at) = DATE('now');

-- 初始化监护人白名单 (示例 - 需要用户配置实际联系方式)
-- 使用方式: 执行完 Schema 后，手动 INSERT 监护人信息
-- INSERT INTO bl_message_triggers (trigger_id, contact_name, contact_phone, enabled, priority, allowed_actions)
-- VALUES ('guardian', '监护人', '+8613800138000', true, 100, '["*"]');
