-- Solar Ontology Schema V2
-- 核心增强: 时间线记忆 + 完整版本历史

-- ==================== 完整版本快照 ====================

-- 每次重大变更保存完整快照 (可回溯)
CREATE TABLE IF NOT EXISTS ont_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    version_number INTEGER NOT NULL,
    snapshot_type TEXT NOT NULL,              -- 'auto', 'manual', 'milestone'

    -- 完整状态快照
    preferences_state JSON NOT NULL,          -- 所有偏好的完整状态
    relationships_state JSON,                 -- 所有关系
    agent_rules_state JSON,                   -- 所有 Agent 规则
    global_rules_state JSON,                  -- 全局规则

    -- 元信息
    trigger_reason TEXT,                      -- 触发原因
    changes_summary TEXT,                     -- 变更摘要
    session_id TEXT,                          -- 触发的会话

    -- 时间戳
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    -- 指标 (用于比较)
    total_confidence REAL,                    -- 总置信度
    active_dimensions INTEGER,                -- 活跃维度数
    learned_signals INTEGER                   -- 累计学习信号数
);

CREATE INDEX IF NOT EXISTS idx_ont_snapshots_time ON ont_snapshots(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ont_snapshots_version ON ont_snapshots(version_number DESC);

-- ==================== 偏好时间线 (完整历史) ====================

-- 每个偏好的完整时间线 (不只是增量)
CREATE TABLE IF NOT EXISTS ont_preference_timeline (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dimension_id TEXT NOT NULL,

    -- 状态快照
    value_at_time REAL NOT NULL,              -- 该时刻的值
    confidence_at_time REAL NOT NULL,         -- 该时刻的置信度
    sample_count_at_time INTEGER NOT NULL,    -- 该时刻的样本数

    -- 变更信息
    delta REAL,                               -- 变化量 (可能为 NULL 如果是首次)
    signal_source TEXT,                       -- 信号来源
    signal_evidence TEXT,                     -- 证据描述

    -- 时间
    recorded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    session_id TEXT,                          -- 哪个会话产生的

    -- 关联快照
    snapshot_id TEXT,                         -- 关联的快照 ID
    FOREIGN KEY (snapshot_id) REFERENCES ont_snapshots(snapshot_id)
);

CREATE INDEX IF NOT EXISTS idx_ont_pref_timeline_dim ON ont_preference_timeline(dimension_id, recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_ont_pref_timeline_time ON ont_preference_timeline(recorded_at DESC);

-- ==================== 记忆时间线 ====================

-- 情景记忆索引 (用于时间查询)
CREATE TABLE IF NOT EXISTS ont_memory_timeline (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    memory_type TEXT NOT NULL,                -- 'episodic', 'semantic', 'procedural'
    memory_id TEXT NOT NULL,

    -- 操作类型
    operation TEXT NOT NULL,                  -- 'created', 'updated', 'recalled', 'decayed', 'archived'

    -- 状态快照
    importance_at_time REAL,
    confidence_at_time REAL,

    -- 时间
    occurred_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    session_id TEXT,

    -- 上下文
    context TEXT                              -- 额外上下文信息
);

CREATE INDEX IF NOT EXISTS idx_ont_mem_timeline_type ON ont_memory_timeline(memory_type, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_ont_mem_timeline_time ON ont_memory_timeline(occurred_at DESC);

-- ==================== 学习事件日志 ====================

-- 每次学习事件的完整记录
CREATE TABLE IF NOT EXISTS ont_learning_events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,                 -- 'signal_received', 'preference_updated', 'ontology_recomputed', 'rollback'

    -- 事件详情
    details JSON NOT NULL,

    -- 影响
    affected_dimensions JSON,                 -- 受影响的维度
    affected_rules JSON,                      -- 受影响的规则

    -- 来源
    source_type TEXT,                         -- 'session', 'explicit', 'feedback', 'system'
    session_id TEXT,

    -- 时间
    occurred_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ont_learning_time ON ont_learning_events(occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_ont_learning_type ON ont_learning_events(event_type);

-- ==================== 视图: 偏好演进 ====================

-- 每日偏好状态视图
CREATE VIEW IF NOT EXISTS v_ont_daily_preferences AS
SELECT
    dimension_id,
    date(recorded_at) as date,
    AVG(value_at_time) as avg_value,
    MAX(value_at_time) as max_value,
    MIN(value_at_time) as min_value,
    AVG(confidence_at_time) as avg_confidence,
    MAX(sample_count_at_time) as samples,
    COUNT(*) as updates
FROM ont_preference_timeline
GROUP BY dimension_id, date(recorded_at)
ORDER BY date DESC, dimension_id;

-- 偏好趋势视图 (最近7天)
CREATE VIEW IF NOT EXISTS v_ont_preference_trend AS
SELECT
    dimension_id,
    (SELECT value_at_time FROM ont_preference_timeline t2
     WHERE t2.dimension_id = t1.dimension_id
     ORDER BY recorded_at DESC LIMIT 1) as current_value,
    (SELECT value_at_time FROM ont_preference_timeline t2
     WHERE t2.dimension_id = t1.dimension_id
       AND recorded_at < datetime('now', '-7 days')
     ORDER BY recorded_at DESC LIMIT 1) as value_7d_ago,
    (SELECT AVG(delta) FROM ont_preference_timeline t2
     WHERE t2.dimension_id = t1.dimension_id
       AND recorded_at > datetime('now', '-7 days')) as avg_delta_7d,
    (SELECT COUNT(*) FROM ont_preference_timeline t2
     WHERE t2.dimension_id = t1.dimension_id
       AND recorded_at > datetime('now', '-7 days')) as updates_7d
FROM ont_preference_timeline t1
GROUP BY dimension_id;

-- 版本历史视图
CREATE VIEW IF NOT EXISTS v_ont_version_history AS
SELECT
    snapshot_id,
    version_number,
    snapshot_type,
    trigger_reason,
    changes_summary,
    total_confidence,
    active_dimensions,
    learned_signals,
    created_at,
    LAG(created_at) OVER (ORDER BY version_number) as previous_version_at,
    julianday(created_at) - julianday(LAG(created_at) OVER (ORDER BY version_number)) as days_since_previous
FROM ont_snapshots
ORDER BY version_number DESC;

-- 最近学习事件视图
CREATE VIEW IF NOT EXISTS v_ont_recent_learning AS
SELECT
    event_id,
    event_type,
    details,
    affected_dimensions,
    source_type,
    session_id,
    occurred_at
FROM ont_learning_events
WHERE occurred_at > datetime('now', '-7 days')
ORDER BY occurred_at DESC;

-- ==================== 时间查询函数支持 ====================

-- 注: SQLite 不支持自定义函数，但我们可以用视图来模拟

-- 获取特定时间点的偏好状态
CREATE VIEW IF NOT EXISTS v_ont_preference_at_time AS
SELECT
    dimension_id,
    value_at_time,
    confidence_at_time,
    recorded_at
FROM ont_preference_timeline
WHERE id IN (
    SELECT MAX(id)
    FROM ont_preference_timeline
    GROUP BY dimension_id
);

-- ==================== 迁移: 从旧表导入数据 ====================

-- 将现有 ont_preference_history 数据迁移到新的 timeline 表
INSERT OR IGNORE INTO ont_preference_timeline
    (dimension_id, value_at_time, confidence_at_time, sample_count_at_time, delta, signal_source, recorded_at)
SELECT
    dimension_id,
    new_value,
    confidence,
    1,
    delta,
    signal_source,
    timestamp
FROM ont_preference_history
WHERE NOT EXISTS (SELECT 1 FROM ont_preference_timeline LIMIT 1);

-- 创建初始快照 (如果不存在)
INSERT OR IGNORE INTO ont_snapshots (
    snapshot_id,
    version_number,
    snapshot_type,
    preferences_state,
    trigger_reason,
    total_confidence,
    active_dimensions,
    learned_signals
)
SELECT
    'initial_' || strftime('%s', 'now'),
    1,
    'auto',
    (SELECT json_group_array(json_object(
        'dimension_id', dimension_id,
        'value', COALESCE(current_value, default_value),
        'confidence', confidence,
        'sample_count', sample_count
    )) FROM ont_preference_dimensions),
    '初始化',
    (SELECT SUM(confidence) FROM ont_preference_dimensions),
    (SELECT COUNT(*) FROM ont_preference_dimensions WHERE confidence > 0),
    (SELECT COALESCE(SUM(sample_count), 0) FROM ont_preference_dimensions)
WHERE NOT EXISTS (SELECT 1 FROM ont_snapshots LIMIT 1);
