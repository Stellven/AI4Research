-- Solar Backlog & Message-Driven Executor Schema
-- 待办管理 + 消息驱动任务执行 + 配额感知调度

-- ============================================================
-- BACKLOG TABLES
-- ============================================================

-- Features: 大颗粒特性 (project → feature)
CREATE TABLE IF NOT EXISTS bl_features (
    feature_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    priority INTEGER DEFAULT 50,  -- 0-100, 越高越优先
    status TEXT DEFAULT 'open' CHECK(status IN ('open', 'in_progress', 'done', 'blocked', 'archived')),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    due_date DATETIME,
    tags TEXT,  -- JSON array
    metadata TEXT  -- JSON object
);

-- Tasks: 子任务 (feature → task)
CREATE TABLE IF NOT EXISTS bl_tasks (
    task_id TEXT PRIMARY KEY,
    feature_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    priority INTEGER DEFAULT 50,
    status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'in_progress', 'done', 'blocked', 'cancelled')),
    estimated_tokens INTEGER,  -- 预估 token 消耗
    actual_tokens INTEGER,     -- 实际 token 消耗
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME,
    assigned_agent TEXT,  -- @Coder, @Tester, etc.
    tags TEXT,  -- JSON array
    FOREIGN KEY (feature_id) REFERENCES bl_features(feature_id)
);

-- Session-Task Association: 会话-任务关联
CREATE TABLE IF NOT EXISTS bl_session_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    extracted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    source TEXT,  -- 'manual', 'auto_extract', 'conversation'
    context TEXT,  -- 提取时的上下文
    FOREIGN KEY (task_id) REFERENCES bl_tasks(task_id),
    UNIQUE(session_id, task_id)
);

-- ============================================================
-- MESSAGE-DRIVEN EXECUTOR TABLES
-- ============================================================

-- Message Tasks: 消息任务队列
CREATE TABLE IF NOT EXISTS bl_message_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL CHECK(source IN ('imessage', 'gmail', 'telegram', 'webhook', 'manual')),
    source_id TEXT NOT NULL,  -- 原始消息 ID，用于去重
    sender TEXT,
    content TEXT NOT NULL,
    parsed_intent TEXT,  -- 解析出的意图
    priority INTEGER DEFAULT 50,  -- 0-100
    status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'queued', 'processing', 'completed', 'failed', 'cancelled')),
    estimated_tokens INTEGER,
    actual_tokens INTEGER,
    result TEXT,  -- JSON: 执行结果
    error TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    queued_at DATETIME,
    started_at DATETIME,
    completed_at DATETIME,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    linked_feature_id TEXT,  -- 可选关联到 feature
    linked_task_id TEXT,     -- 可选关联到 task
    metadata TEXT,  -- JSON object
    UNIQUE(source, source_id),
    FOREIGN KEY (linked_feature_id) REFERENCES bl_features(feature_id),
    FOREIGN KEY (linked_task_id) REFERENCES bl_tasks(task_id)
);

-- Message Triggers: 关键词触发规则
CREATE TABLE IF NOT EXISTS bl_message_triggers (
    trigger_id TEXT PRIMARY KEY,
    pattern TEXT NOT NULL,  -- 正则或关键词
    pattern_type TEXT DEFAULT 'keyword' CHECK(pattern_type IN ('keyword', 'regex', 'intent')),
    action TEXT NOT NULL,  -- 执行的动作: 'skill', 'shortcut', 'agent', 'script'
    action_target TEXT NOT NULL,  -- 具体目标: '/weather', 'solar_get_weather', '@Coder'
    priority_boost INTEGER DEFAULT 0,  -- 优先级加成
    enabled INTEGER DEFAULT 1,
    description TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- QUOTA MANAGEMENT TABLES
-- ============================================================

-- Quota Usage: 配额使用追踪
CREATE TABLE IF NOT EXISTS bl_quota_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period_start DATETIME NOT NULL,  -- 周期开始时间
    period_type TEXT DEFAULT 'daily' CHECK(period_type IN ('hourly', 'daily', 'monthly')),
    model TEXT DEFAULT 'claude',
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    total_requests INTEGER DEFAULT 0,
    estimated_cost REAL DEFAULT 0,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(period_start, period_type, model)
);

-- Quota Reservations: 配额预留
CREATE TABLE IF NOT EXISTS bl_quota_reservations (
    reservation_id TEXT PRIMARY KEY,
    task_id INTEGER NOT NULL,  -- 关联 bl_message_tasks.id
    reserved_tokens INTEGER NOT NULL,
    reserved_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    released_at DATETIME,
    status TEXT DEFAULT 'active' CHECK(status IN ('active', 'released', 'expired')),
    FOREIGN KEY (task_id) REFERENCES bl_message_tasks(id)
);

-- Quota Limits: 配额限制配置
CREATE TABLE IF NOT EXISTS bl_quota_limits (
    limit_id TEXT PRIMARY KEY,
    period_type TEXT NOT NULL CHECK(period_type IN ('hourly', 'daily', 'monthly')),
    model TEXT DEFAULT 'claude',
    max_tokens INTEGER,
    max_requests INTEGER,
    max_cost REAL,
    warning_threshold REAL DEFAULT 0.8,  -- 80% 警告
    critical_threshold REAL DEFAULT 0.95,  -- 95% 临界
    enabled INTEGER DEFAULT 1,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(period_type, model)
);

-- ============================================================
-- INDEXES
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_bl_features_project ON bl_features(project_id);
CREATE INDEX IF NOT EXISTS idx_bl_features_status ON bl_features(status);
CREATE INDEX IF NOT EXISTS idx_bl_tasks_feature ON bl_tasks(feature_id);
CREATE INDEX IF NOT EXISTS idx_bl_tasks_status ON bl_tasks(status);
CREATE INDEX IF NOT EXISTS idx_bl_message_tasks_status ON bl_message_tasks(status);
CREATE INDEX IF NOT EXISTS idx_bl_message_tasks_source ON bl_message_tasks(source, source_id);
CREATE INDEX IF NOT EXISTS idx_bl_message_tasks_priority ON bl_message_tasks(priority DESC, created_at ASC);
CREATE INDEX IF NOT EXISTS idx_bl_quota_usage_period ON bl_quota_usage(period_start, period_type);
CREATE INDEX IF NOT EXISTS idx_bl_quota_reservations_active ON bl_quota_reservations(status) WHERE status = 'active';

-- ============================================================
-- VIEWS
-- ============================================================

-- 项目 Backlog 概览
CREATE VIEW IF NOT EXISTS v_project_backlog AS
SELECT
    f.project_id,
    f.feature_id,
    f.title AS feature_title,
    f.status AS feature_status,
    f.priority AS feature_priority,
    COUNT(t.task_id) AS total_tasks,
    SUM(CASE WHEN t.status = 'done' THEN 1 ELSE 0 END) AS completed_tasks,
    SUM(CASE WHEN t.status = 'in_progress' THEN 1 ELSE 0 END) AS active_tasks,
    SUM(CASE WHEN t.status = 'pending' THEN 1 ELSE 0 END) AS pending_tasks,
    ROUND(100.0 * SUM(CASE WHEN t.status = 'done' THEN 1 ELSE 0 END) / NULLIF(COUNT(t.task_id), 0), 1) AS progress_pct,
    f.created_at,
    f.due_date
FROM bl_features f
LEFT JOIN bl_tasks t ON f.feature_id = t.feature_id
GROUP BY f.feature_id
ORDER BY f.priority DESC, f.created_at DESC;

-- Feature 进度详情
CREATE VIEW IF NOT EXISTS v_feature_details AS
SELECT
    t.task_id,
    t.title AS task_title,
    t.status AS task_status,
    t.priority,
    t.assigned_agent,
    t.estimated_tokens,
    t.actual_tokens,
    t.created_at,
    t.completed_at,
    f.feature_id,
    f.title AS feature_title,
    f.project_id
FROM bl_tasks t
JOIN bl_features f ON t.feature_id = f.feature_id
ORDER BY f.priority DESC, t.priority DESC, t.created_at ASC;

-- 可执行任务队列
CREATE VIEW IF NOT EXISTS v_message_queue AS
SELECT
    m.id,
    m.source,
    m.sender,
    m.content,
    m.parsed_intent,
    m.priority,
    m.status,
    m.estimated_tokens,
    m.retry_count,
    m.max_retries,
    m.created_at,
    ROUND((julianday('now') - julianday(m.created_at)) * 24 * 60, 1) AS wait_minutes
FROM bl_message_tasks m
WHERE m.status IN ('pending', 'queued')
ORDER BY m.priority DESC, m.created_at ASC;

-- 实时配额状态
CREATE VIEW IF NOT EXISTS v_quota_realtime AS
SELECT
    l.period_type,
    l.model,
    l.max_tokens,
    l.max_requests,
    COALESCE(u.input_tokens + u.output_tokens, 0) AS used_tokens,
    COALESCE(u.total_requests, 0) AS used_requests,
    COALESCE(
        (SELECT SUM(reserved_tokens) FROM bl_quota_reservations WHERE status = 'active'),
        0
    ) AS reserved_tokens,
    ROUND(100.0 * COALESCE(u.input_tokens + u.output_tokens, 0) / NULLIF(l.max_tokens, 0), 2) AS usage_pct,
    l.warning_threshold * 100 AS warning_pct,
    l.critical_threshold * 100 AS critical_pct,
    CASE
        WHEN COALESCE(u.input_tokens + u.output_tokens, 0) >= l.max_tokens THEN 'exceeded'
        WHEN COALESCE(u.input_tokens + u.output_tokens, 0) >= l.max_tokens * l.critical_threshold THEN 'critical'
        WHEN COALESCE(u.input_tokens + u.output_tokens, 0) >= l.max_tokens * l.warning_threshold THEN 'warning'
        ELSE 'ok'
    END AS status
FROM bl_quota_limits l
LEFT JOIN bl_quota_usage u ON l.period_type = u.period_type
    AND l.model = u.model
    AND u.period_start = date('now')
WHERE l.enabled = 1;

-- 调度决策视图
CREATE VIEW IF NOT EXISTS v_scheduler_decision AS
SELECT
    q.status AS quota_status,
    CASE q.status
        WHEN 'exceeded' THEN 0
        WHEN 'critical' THEN 1
        WHEN 'warning' THEN 2
        ELSE 4
    END AS max_concurrent,
    q.usage_pct,
    q.max_tokens - q.used_tokens - q.reserved_tokens AS available_tokens,
    (SELECT COUNT(*) FROM bl_message_tasks WHERE status = 'processing') AS current_processing,
    (SELECT COUNT(*) FROM bl_message_tasks WHERE status IN ('pending', 'queued')) AS pending_tasks
FROM v_quota_realtime q
WHERE q.period_type = 'daily'
LIMIT 1;

-- ============================================================
-- TRIGGERS
-- ============================================================

-- 自动更新 updated_at
CREATE TRIGGER IF NOT EXISTS tr_bl_features_updated
AFTER UPDATE ON bl_features
BEGIN
    UPDATE bl_features SET updated_at = CURRENT_TIMESTAMP WHERE feature_id = NEW.feature_id;
END;

CREATE TRIGGER IF NOT EXISTS tr_bl_tasks_updated
AFTER UPDATE ON bl_tasks
BEGIN
    UPDATE bl_tasks SET updated_at = CURRENT_TIMESTAMP WHERE task_id = NEW.task_id;
END;

-- 任务完成时记录时间
CREATE TRIGGER IF NOT EXISTS tr_bl_tasks_completed
AFTER UPDATE OF status ON bl_tasks
WHEN NEW.status = 'done' AND OLD.status != 'done'
BEGIN
    UPDATE bl_tasks SET completed_at = CURRENT_TIMESTAMP WHERE task_id = NEW.task_id;
END;

-- 消息任务状态变更时间戳
CREATE TRIGGER IF NOT EXISTS tr_bl_message_tasks_queued
AFTER UPDATE OF status ON bl_message_tasks
WHEN NEW.status = 'queued' AND OLD.status != 'queued'
BEGIN
    UPDATE bl_message_tasks SET queued_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS tr_bl_message_tasks_processing
AFTER UPDATE OF status ON bl_message_tasks
WHEN NEW.status = 'processing' AND OLD.status != 'processing'
BEGIN
    UPDATE bl_message_tasks SET started_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS tr_bl_message_tasks_completed
AFTER UPDATE OF status ON bl_message_tasks
WHEN NEW.status IN ('completed', 'failed') AND OLD.status NOT IN ('completed', 'failed')
BEGIN
    UPDATE bl_message_tasks SET completed_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

-- ============================================================
-- DEFAULT DATA
-- ============================================================

-- 默认配额限制
INSERT OR IGNORE INTO bl_quota_limits (limit_id, period_type, model, max_tokens, max_requests, warning_threshold, critical_threshold)
VALUES
    ('daily_claude', 'daily', 'claude', 1000000, 1000, 0.8, 0.95),
    ('hourly_claude', 'hourly', 'claude', 100000, 100, 0.8, 0.95);

-- 默认触发规则
INSERT OR IGNORE INTO bl_message_triggers (trigger_id, pattern, pattern_type, action, action_target, priority_boost, description)
VALUES
    ('urgent', '紧急|urgent|ASAP', 'regex', 'skill', '/backlog', 30, '紧急任务优先处理'),
    ('weather', '天气|weather', 'keyword', 'shortcut', 'solar_get_weather', 0, '天气查询'),
    ('reminder', '提醒|remind', 'keyword', 'shortcut', 'solar_set_reminder', 0, '设置提醒'),
    ('solar_tag', '#solar', 'keyword', 'agent', '@Coder', 10, 'Solar 项目相关'),
    ('review', '审查|review|检查', 'keyword', 'agent', '@Reviewer', 5, '代码审查');
