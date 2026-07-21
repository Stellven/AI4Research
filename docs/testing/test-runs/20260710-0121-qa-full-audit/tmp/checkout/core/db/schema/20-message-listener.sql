-- Solar message-listener compatibility schema.
-- The shared queue and trigger tables are defined in 10-backlog.sql as a
-- superset because core/backlog and core/message-listener use the same table
-- names with different column sets.

CREATE TABLE IF NOT EXISTS bl_message_stats (
    date TEXT PRIMARY KEY,
    total_messages INTEGER DEFAULT 0,
    successful_tasks INTEGER DEFAULT 0,
    failed_tasks INTEGER DEFAULT 0,
    avg_execution_time_ms REAL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS bl_scheduled_tasks (
    task_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    action TEXT NOT NULL,
    schedule_interval_sec INTEGER NOT NULL,
    priority INTEGER DEFAULT 50,
    enabled BOOLEAN DEFAULT true,
    last_executed DATETIME,
    next_execution DATETIME,
    execution_count INTEGER DEFAULT 0,
    failure_count INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_message_tasks_sender ON bl_message_tasks(sender);
CREATE INDEX IF NOT EXISTS idx_message_tasks_status ON bl_message_tasks(status);
CREATE INDEX IF NOT EXISTS idx_message_tasks_created ON bl_message_tasks(created_at);
CREATE INDEX IF NOT EXISTS idx_message_triggers_enabled ON bl_message_triggers(enabled);

CREATE VIEW IF NOT EXISTS v_message_tasks_today AS
SELECT
    COUNT(*) as total,
    SUM(CASE WHEN status IN ('done', 'completed') THEN 1 ELSE 0 END) as completed,
    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
    SUM(CASE WHEN status IN ('running', 'processing') THEN 1 ELSE 0 END) as running,
    AVG(execution_time_ms) as avg_time_ms
FROM bl_message_tasks
WHERE DATE(created_at) = DATE('now');
