-- ============================================================
-- HIVE Protocol - Database Schema
-- Heterogeneous Intelligent Virtual Ecosystem
--
-- 命名者：李卓远 (继承人)
-- 核心原则：不传参数、不传权重、只传任务
-- ============================================================

-- ============================================================
-- 网络配置表
-- ============================================================

CREATE TABLE IF NOT EXISTS hive_networks (
    network_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    max_nodes INTEGER DEFAULT 50,
    bidding_timeout_ms INTEGER DEFAULT 5000,
    heartbeat_interval_ms INTEGER DEFAULT 30000,
    initial_credits INTEGER DEFAULT 100,
    task_base_reward INTEGER DEFAULT 10,
    penalty_rate REAL DEFAULT 0.1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 节点表
-- ============================================================

CREATE TABLE IF NOT EXISTS hive_nodes (
    node_id TEXT PRIMARY KEY,
    network_id TEXT NOT NULL,
    name TEXT NOT NULL,
    owner TEXT NOT NULL,
    tier TEXT CHECK(tier IN ('edge', 'local', 'cloud')) NOT NULL,
    status TEXT CHECK(status IN ('online', 'offline', 'busy')) DEFAULT 'online',
    credits INTEGER DEFAULT 100,
    joined_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_heartbeat DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (network_id) REFERENCES hive_networks(network_id)
);

CREATE INDEX IF NOT EXISTS idx_hive_nodes_network ON hive_nodes(network_id);
CREATE INDEX IF NOT EXISTS idx_hive_nodes_status ON hive_nodes(status);
CREATE INDEX IF NOT EXISTS idx_hive_nodes_tier ON hive_nodes(tier);

-- ============================================================
-- 节点能力表
-- ============================================================

CREATE TABLE IF NOT EXISTS hive_node_capabilities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    tier TEXT CHECK(tier IN ('edge', 'local', 'cloud')) NOT NULL,
    max_concurrent INTEGER DEFAULT 5,
    avg_latency_ms INTEGER DEFAULT 1000,
    success_rate REAL DEFAULT 0.9,
    credits_per_task INTEGER DEFAULT 5,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (node_id) REFERENCES hive_nodes(node_id),
    UNIQUE(node_id, agent_id)
);

CREATE INDEX IF NOT EXISTS idx_hive_capabilities_node ON hive_node_capabilities(node_id);
CREATE INDEX IF NOT EXISTS idx_hive_capabilities_agent ON hive_node_capabilities(agent_id);

-- ============================================================
-- 任务表
-- ============================================================

CREATE TABLE IF NOT EXISTS hive_tasks (
    task_id TEXT PRIMARY KEY,
    network_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    priority TEXT CHECK(priority IN ('low', 'normal', 'high', 'urgent')) DEFAULT 'normal',
    status TEXT CHECK(status IN ('pending', 'bidding', 'assigned', 'running', 'completed', 'failed', 'verified')) DEFAULT 'pending',
    min_tier TEXT CHECK(min_tier IN ('edge', 'local', 'cloud')) DEFAULT 'edge',
    created_by TEXT NOT NULL,
    assigned_to TEXT,
    result_success BOOLEAN,
    result_output TEXT,
    result_artifacts TEXT,  -- JSON array
    result_tokens_used INTEGER,
    result_latency_ms INTEGER,
    result_cost REAL,
    result_error TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    deadline DATETIME,
    completed_at DATETIME,
    FOREIGN KEY (network_id) REFERENCES hive_networks(network_id),
    FOREIGN KEY (created_by) REFERENCES hive_nodes(node_id),
    FOREIGN KEY (assigned_to) REFERENCES hive_nodes(node_id)
);

CREATE INDEX IF NOT EXISTS idx_hive_tasks_network ON hive_tasks(network_id);
CREATE INDEX IF NOT EXISTS idx_hive_tasks_status ON hive_tasks(status);
CREATE INDEX IF NOT EXISTS idx_hive_tasks_created_by ON hive_tasks(created_by);
CREATE INDEX IF NOT EXISTS idx_hive_tasks_assigned_to ON hive_tasks(assigned_to);

-- ============================================================
-- 任务需求表
-- ============================================================

CREATE TABLE IF NOT EXISTS hive_task_requirements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    FOREIGN KEY (task_id) REFERENCES hive_tasks(task_id)
);

CREATE INDEX IF NOT EXISTS idx_hive_requirements_task ON hive_task_requirements(task_id);

-- ============================================================
-- 竞标表
-- ============================================================

CREATE TABLE IF NOT EXISTS hive_bids (
    bid_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    estimated_latency_ms INTEGER,
    estimated_credits INTEGER,
    confidence REAL CHECK(confidence >= 0 AND confidence <= 1),
    is_winner BOOLEAN DEFAULT FALSE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (task_id) REFERENCES hive_tasks(task_id),
    FOREIGN KEY (node_id) REFERENCES hive_nodes(node_id)
);

CREATE INDEX IF NOT EXISTS idx_hive_bids_task ON hive_bids(task_id);
CREATE INDEX IF NOT EXISTS idx_hive_bids_node ON hive_bids(node_id);

-- ============================================================
-- 积分交易表
-- ============================================================

CREATE TABLE IF NOT EXISTS hive_credit_transactions (
    tx_id TEXT PRIMARY KEY,
    network_id TEXT NOT NULL,
    from_node TEXT NOT NULL,  -- 'system' for system rewards
    to_node TEXT NOT NULL,    -- 'system' for penalties
    amount INTEGER NOT NULL,
    type TEXT CHECK(type IN ('task_payment', 'task_reward', 'penalty', 'bonus')) NOT NULL,
    task_id TEXT,
    reason TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (network_id) REFERENCES hive_networks(network_id),
    FOREIGN KEY (task_id) REFERENCES hive_tasks(task_id)
);

CREATE INDEX IF NOT EXISTS idx_hive_credit_tx_network ON hive_credit_transactions(network_id);
CREATE INDEX IF NOT EXISTS idx_hive_credit_tx_from ON hive_credit_transactions(from_node);
CREATE INDEX IF NOT EXISTS idx_hive_credit_tx_to ON hive_credit_transactions(to_node);
CREATE INDEX IF NOT EXISTS idx_hive_credit_tx_type ON hive_credit_transactions(type);

-- ============================================================
-- 消息日志表 (调试用)
-- ============================================================

CREATE TABLE IF NOT EXISTS hive_message_log (
    message_id TEXT PRIMARY KEY,
    network_id TEXT NOT NULL,
    type TEXT NOT NULL,
    from_node TEXT NOT NULL,
    to_node TEXT,
    payload TEXT,  -- JSON
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (network_id) REFERENCES hive_networks(network_id)
);

CREATE INDEX IF NOT EXISTS idx_hive_msg_network ON hive_message_log(network_id);
CREATE INDEX IF NOT EXISTS idx_hive_msg_type ON hive_message_log(type);

-- ============================================================
-- 视图：节点健康状态
-- ============================================================

CREATE VIEW IF NOT EXISTS v_hive_node_health AS
SELECT
    n.node_id,
    n.name,
    n.owner,
    n.tier,
    n.status,
    n.credits,
    COUNT(DISTINCT c.agent_id) as capability_count,
    AVG(c.success_rate) as avg_success_rate,
    AVG(c.avg_latency_ms) as avg_latency_ms,
    (julianday('now') - julianday(n.last_heartbeat)) * 24 * 60 as minutes_since_heartbeat,
    CASE
        WHEN (julianday('now') - julianday(n.last_heartbeat)) * 24 * 60 > 5 THEN 'stale'
        WHEN n.status = 'offline' THEN 'offline'
        WHEN n.status = 'busy' THEN 'busy'
        ELSE 'healthy'
    END as health_status
FROM hive_nodes n
LEFT JOIN hive_node_capabilities c ON n.node_id = c.node_id
GROUP BY n.node_id;

-- ============================================================
-- 视图：任务统计
-- ============================================================

CREATE VIEW IF NOT EXISTS v_hive_task_stats AS
SELECT
    network_id,
    status,
    COUNT(*) as task_count,
    AVG(CASE WHEN completed_at IS NOT NULL THEN
        (julianday(completed_at) - julianday(created_at)) * 24 * 60 * 60 * 1000
    END) as avg_completion_ms,
    SUM(result_tokens_used) as total_tokens,
    SUM(result_cost) as total_cost
FROM hive_tasks
GROUP BY network_id, status;

-- ============================================================
-- 视图：积分排行榜
-- ============================================================

CREATE VIEW IF NOT EXISTS v_hive_credit_leaderboard AS
SELECT
    n.node_id,
    n.name,
    n.owner,
    n.credits as balance,
    COALESCE(earned.total, 0) as total_earned,
    COALESCE(spent.total, 0) as total_spent,
    COALESCE(tasks.completed, 0) as tasks_completed
FROM hive_nodes n
LEFT JOIN (
    SELECT to_node, SUM(amount) as total
    FROM hive_credit_transactions
    WHERE type IN ('task_reward', 'bonus')
    GROUP BY to_node
) earned ON n.node_id = earned.to_node
LEFT JOIN (
    SELECT from_node, SUM(amount) as total
    FROM hive_credit_transactions
    WHERE type IN ('task_payment', 'penalty')
    GROUP BY from_node
) spent ON n.node_id = spent.from_node
LEFT JOIN (
    SELECT assigned_to, COUNT(*) as completed
    FROM hive_tasks
    WHERE status = 'verified'
    GROUP BY assigned_to
) tasks ON n.node_id = tasks.assigned_to
ORDER BY n.credits DESC;

-- ============================================================
-- 视图：能力矩阵
-- ============================================================

CREATE VIEW IF NOT EXISTS v_hive_capability_matrix AS
SELECT
    c.agent_id,
    c.agent_name,
    c.tier as required_tier,
    COUNT(DISTINCT c.node_id) as available_nodes,
    AVG(c.success_rate) as avg_success_rate,
    AVG(c.avg_latency_ms) as avg_latency_ms,
    AVG(c.credits_per_task) as avg_cost
FROM hive_node_capabilities c
JOIN hive_nodes n ON c.node_id = n.node_id AND n.status != 'offline'
GROUP BY c.agent_id, c.agent_name, c.tier
ORDER BY c.tier, c.agent_id;

-- ============================================================
-- 视图：网络总览
-- ============================================================

CREATE VIEW IF NOT EXISTS v_hive_network_overview AS
SELECT
    h.network_id,
    h.name,
    h.max_nodes,
    COUNT(DISTINCT n.node_id) as total_nodes,
    COUNT(DISTINCT CASE WHEN n.status != 'offline' THEN n.node_id END) as online_nodes,
    COUNT(DISTINCT CASE WHEN n.tier = 'edge' THEN n.node_id END) as edge_nodes,
    COUNT(DISTINCT CASE WHEN n.tier = 'local' THEN n.node_id END) as local_nodes,
    COUNT(DISTINCT CASE WHEN n.tier = 'cloud' THEN n.node_id END) as cloud_nodes,
    SUM(n.credits) as total_credits,
    COUNT(DISTINCT t.task_id) as total_tasks,
    COUNT(DISTINCT CASE WHEN t.status = 'verified' THEN t.task_id END) as completed_tasks
FROM hive_networks h
LEFT JOIN hive_nodes n ON h.network_id = n.network_id
LEFT JOIN hive_tasks t ON h.network_id = t.network_id
GROUP BY h.network_id;

-- ============================================================
-- 触发器：更新时间戳
-- ============================================================

CREATE TRIGGER IF NOT EXISTS tr_hive_network_updated
AFTER UPDATE ON hive_networks
BEGIN
    UPDATE hive_networks SET updated_at = CURRENT_TIMESTAMP WHERE network_id = NEW.network_id;
END;

CREATE TRIGGER IF NOT EXISTS tr_hive_node_heartbeat
AFTER UPDATE OF status ON hive_nodes
BEGIN
    UPDATE hive_nodes SET last_heartbeat = CURRENT_TIMESTAMP WHERE node_id = NEW.node_id;
END;

-- ============================================================
-- 触发器：任务完成时更新节点统计
-- ============================================================

CREATE TRIGGER IF NOT EXISTS tr_hive_task_completed
AFTER UPDATE OF status ON hive_tasks
WHEN NEW.status = 'verified' AND OLD.status != 'verified'
BEGIN
    -- 这里可以添加自动更新节点成功率等逻辑
    SELECT 1; -- placeholder
END;

-- ============================================================
-- 初始化默认网络
-- ============================================================

INSERT OR IGNORE INTO hive_networks (network_id, name) VALUES
    ('solar-hive-001', 'Solar Community Hive');

-- ============================================================
-- HIVE Protocol Schema Complete
-- ============================================================
