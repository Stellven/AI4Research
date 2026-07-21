-- Solar Core - SQLite Schema
-- Version: 3.0
-- Description: 神经系统 - 状态、任务、消息持久化

-- ==================== 核心表 ====================

-- 任务表
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project TEXT NOT NULL,
    description TEXT NOT NULL,
    complexity TEXT CHECK(complexity IN ('simple', 'medium', 'complex')),
    status TEXT CHECK(status IN ('pending', 'in_progress', 'completed', 'failed', 'cancelled')) DEFAULT 'pending',
    current_phase TEXT,
    current_agent TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME,
    metadata JSON
);

-- 消息表 (系统事件日志)
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,           -- 'hook', 'agent', 'workflow', 'plugin', 'error', 'system'
    source TEXT NOT NULL,         -- 来源组件
    level TEXT DEFAULT 'info',    -- 'debug', 'info', 'warn', 'error'
    content JSON NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    processed BOOLEAN DEFAULT FALSE
);

-- 状态表 (实时状态快照 - KV存储)
CREATE TABLE IF NOT EXISTS state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT UNIQUE NOT NULL,     -- 'flow.current_phase', 'agent.active', 'daemon.status'
    value JSON NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Agent 执行记录
CREATE TABLE IF NOT EXISTS agent_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER REFERENCES tasks(id) ON DELETE CASCADE,
    agent TEXT NOT NULL,
    phase TEXT NOT NULL,
    started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    ended_at DATETIME,
    status TEXT CHECK(status IN ('running', 'success', 'failed', 'timeout', 'cancelled')) DEFAULT 'running',
    input JSON,
    output JSON,
    tokens_used INTEGER DEFAULT 0,
    model_used TEXT,
    cost_usd REAL DEFAULT 0
);

-- 工作流转换历史
CREATE TABLE IF NOT EXISTS workflow_transitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER REFERENCES tasks(id) ON DELETE CASCADE,
    from_phase TEXT,
    to_phase TEXT,
    from_agent TEXT,
    to_agent TEXT,
    gate_name TEXT,               -- 'G1', 'G2', 'G3', NULL
    gate_passed BOOLEAN,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    metadata JSON
);

-- 插件注册表
CREATE TABLE IF NOT EXISTS plugins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    version TEXT NOT NULL,
    type TEXT CHECK(type IN ('skill', 'hook', 'agent', 'model', 'custom')) NOT NULL,
    description TEXT,
    path TEXT NOT NULL,
    enabled BOOLEAN DEFAULT TRUE,
    config JSON,
    installed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Token 使用统计
CREATE TABLE IF NOT EXISTS token_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL,
    model TEXT NOT NULL,
    provider TEXT NOT NULL,       -- 'anthropic', 'openai', 'deepseek', etc.
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    requests INTEGER DEFAULT 0,
    cost_usd REAL DEFAULT 0,
    UNIQUE(date, model)
);

-- 会话历史
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project TEXT NOT NULL,
    started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    ended_at DATETIME,
    duration_seconds INTEGER,
    total_tokens INTEGER DEFAULT 0,
    total_cost_usd REAL DEFAULT 0,
    summary TEXT,
    checkpoint JSON              -- 可恢复的状态快照
);

-- 项目表
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    path TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_opened_at DATETIME,
    settings JSON
);

-- ==================== 索引 ====================

CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_updated ON tasks(updated_at);

CREATE INDEX IF NOT EXISTS idx_messages_type ON messages(type);
CREATE INDEX IF NOT EXISTS idx_messages_level ON messages(level);
CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp);
CREATE INDEX IF NOT EXISTS idx_messages_processed ON messages(processed);

CREATE INDEX IF NOT EXISTS idx_state_key ON state(key);

CREATE INDEX IF NOT EXISTS idx_agent_runs_task ON agent_runs(task_id);
CREATE INDEX IF NOT EXISTS idx_agent_runs_agent ON agent_runs(agent);
CREATE INDEX IF NOT EXISTS idx_agent_runs_status ON agent_runs(status);

CREATE INDEX IF NOT EXISTS idx_workflow_task ON workflow_transitions(task_id);

CREATE INDEX IF NOT EXISTS idx_token_usage_date ON token_usage(date);
CREATE INDEX IF NOT EXISTS idx_token_usage_model ON token_usage(model);

CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project);

-- ==================== 触发器 ====================

-- 自动更新 tasks.updated_at
CREATE TRIGGER IF NOT EXISTS tasks_updated_at
AFTER UPDATE ON tasks
BEGIN
    UPDATE tasks SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

-- 自动更新 plugins.updated_at
CREATE TRIGGER IF NOT EXISTS plugins_updated_at
AFTER UPDATE ON plugins
BEGIN
    UPDATE plugins SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

-- ==================== 初始数据 ====================

-- 默认状态
INSERT OR IGNORE INTO state (key, value) VALUES
    ('daemon.status', '"stopped"'),
    ('daemon.started_at', 'null'),
    ('flow.active', 'false'),
    ('flow.current_phase', 'null'),
    ('flow.current_agent', 'null'),
    ('session.active', 'false'),
    ('session.id', 'null'),
    ('token_usage.today_cost', '0'),
    ('token_usage.today_tokens', '0');
