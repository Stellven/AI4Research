-- Solar Ontology Schema
-- 本体 = 记忆库 + 个性 (不是大脑，大脑是 Claude)

-- ==================== 个性维度表 ====================

-- 偏好维度 (Preferences)
CREATE TABLE IF NOT EXISTS ont_preference_dimensions (
    dimension_id TEXT PRIMARY KEY,
    category TEXT NOT NULL,           -- work_style, communication, priority, risk
    name TEXT NOT NULL,
    description TEXT,
    value_type TEXT DEFAULT 'continuous',  -- continuous, categorical, ranking
    value_range JSON,                 -- 取值范围
    default_value REAL DEFAULT 0.5,
    current_value REAL,
    confidence REAL DEFAULT 0.0,      -- 置信度 0-1
    sample_count INTEGER DEFAULT 0,
    last_updated DATETIME,
    evidence JSON                     -- 支撑证据
);

-- 价值观维度 (Values)
CREATE TABLE IF NOT EXISTS ont_value_dimensions (
    dimension_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    weight REAL DEFAULT 0.5,          -- 重要性权重 0-1
    conflicts_with JSON,              -- 冲突的价值观
    evidence JSON,
    confidence REAL DEFAULT 0.0,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 风格维度 (Style)
CREATE TABLE IF NOT EXISTS ont_style_dimensions (
    dimension_id TEXT PRIMARY KEY,
    category TEXT NOT NULL,           -- output, interaction, code
    name TEXT NOT NULL,
    description TEXT,
    current_value TEXT,               -- 当前值
    alternatives JSON,                -- 可选值
    evidence JSON,
    confidence REAL DEFAULT 0.0,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 关系表 (Relationships)
CREATE TABLE IF NOT EXISTS ont_relationships (
    relationship_id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,        -- person, project, tool, community
    entity_name TEXT NOT NULL,
    relationship_type TEXT,           -- guardian, focus, frequent, trusted
    importance REAL DEFAULT 0.5,      -- 重要性 0-1
    context JSON,                     -- 上下文信息
    last_interaction DATETIME,
    interaction_count INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ==================== Agent 规则表 ====================

-- Agent 行为规则 (由本体驱动生成)
CREATE TABLE IF NOT EXISTS ont_agent_rules (
    rule_id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT NOT NULL,
    rule_type TEXT NOT NULL,          -- behavior, output, decision
    rule_key TEXT NOT NULL,
    rule_value JSON NOT NULL,
    source_dimension TEXT,            -- 来源维度
    generated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    valid_until DATETIME,             -- 过期时间
    UNIQUE(agent_id, rule_type, rule_key)
);

-- 全局规则 (适用于所有 Agent)
CREATE TABLE IF NOT EXISTS ont_global_rules (
    rule_id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_key TEXT NOT NULL UNIQUE,
    rule_value JSON NOT NULL,
    source_dimension TEXT,
    confidence REAL DEFAULT 0.5,
    generated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ==================== 本体版本历史 ====================

CREATE TABLE IF NOT EXISTS ont_versions (
    version_id TEXT PRIMARY KEY,
    version_number INTEGER NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    preference_snapshot JSON,         -- 偏好快照
    agent_rules_snapshot JSON,        -- Agent 规则快照
    trigger_reason TEXT,              -- 触发原因
    changes_summary TEXT              -- 变更摘要
);

-- 偏好变更历史
CREATE TABLE IF NOT EXISTS ont_preference_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dimension_id TEXT NOT NULL,
    old_value REAL,
    new_value REAL,
    delta REAL,
    confidence REAL,
    signal_source TEXT,               -- session, explicit, feedback
    signal_weight REAL DEFAULT 1.0,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ==================== 索引 ====================

CREATE INDEX IF NOT EXISTS idx_ont_pref_category ON ont_preference_dimensions(category);
CREATE INDEX IF NOT EXISTS idx_ont_rules_agent ON ont_agent_rules(agent_id);
CREATE INDEX IF NOT EXISTS idx_ont_rel_type ON ont_relationships(entity_type, relationship_type);
CREATE INDEX IF NOT EXISTS idx_ont_pref_history_dim ON ont_preference_history(dimension_id);

-- ==================== 视图 ====================

-- 活跃偏好视图 (置信度 > 0.3)
CREATE VIEW IF NOT EXISTS v_ont_active_preferences AS
SELECT
    dimension_id,
    category,
    name,
    current_value,
    confidence,
    sample_count,
    last_updated
FROM ont_preference_dimensions
WHERE confidence > 0.3
ORDER BY confidence DESC;

-- 偏好趋势视图
CREATE VIEW IF NOT EXISTS v_ont_preference_trends AS
SELECT
    dimension_id,
    date(timestamp) as date,
    AVG(new_value) as avg_value,
    AVG(confidence) as avg_confidence,
    COUNT(*) as signal_count
FROM ont_preference_history
GROUP BY dimension_id, date(timestamp)
ORDER BY date DESC;

-- Agent 规则视图
CREATE VIEW IF NOT EXISTS v_ont_agent_context AS
SELECT
    ar.agent_id,
    ar.rule_type,
    ar.rule_key,
    ar.rule_value,
    ar.source_dimension,
    pd.current_value as dimension_value,
    pd.confidence as dimension_confidence
FROM ont_agent_rules ar
LEFT JOIN ont_preference_dimensions pd ON ar.source_dimension = pd.dimension_id
WHERE ar.valid_until IS NULL OR ar.valid_until > datetime('now');

-- 重要关系视图
CREATE VIEW IF NOT EXISTS v_ont_important_relationships AS
SELECT *
FROM ont_relationships
WHERE importance > 0.5
ORDER BY importance DESC, last_interaction DESC;

-- ==================== 初始数据 ====================

-- 偏好维度初始化 (从行为中学习，不是预设值)
INSERT OR IGNORE INTO ont_preference_dimensions (dimension_id, category, name, description, value_type, value_range)
VALUES
-- 工作风格
('work_time', 'work_style', '工作时间偏好', '偏好的工作时段', 'categorical', '["morning","afternoon","evening","night"]'),
('session_depth', 'work_style', '会话深度', '偏好短会话还是长会话', 'continuous', '[0, 1]'),
('parallelism', 'work_style', '并行度', '同时处理多少任务', 'continuous', '[0, 1]'),

-- 沟通风格
('verbosity', 'communication', '详细程度', '输出的详细程度', 'continuous', '[0, 1]'),
('explanation', 'communication', '解释需求', '是否需要先解释再执行', 'continuous', '[0, 1]'),

-- 优先级
('speed_vs_quality', 'priority', '速度vs质量', '偏好快速还是高质量', 'continuous', '[0, 1]'),
('cost_sensitivity', 'priority', '成本敏感度', '对 Token 成本的敏感程度', 'continuous', '[0, 1]'),
('performance_focus', 'priority', '性能关注', '对运行性能的关注程度', 'continuous', '[0, 1]'),

-- 风险
('risk_tolerance', 'risk', '风险容忍', '对风险的接受程度', 'continuous', '[0, 1]'),
('automation_trust', 'risk', '自动化信任', '对自动执行的信任程度', 'continuous', '[0, 1]');

-- 初始关系 (监护人)
INSERT OR IGNORE INTO ont_relationships (relationship_id, entity_type, entity_name, relationship_type, importance, context)
VALUES ('guardian:sihaoli', 'person', 'sihaoli', 'guardian', 1.0, '{"role": "监护人", "first_law": true}');

-- 全局规则初始化
INSERT OR IGNORE INTO ont_global_rules (rule_key, rule_value, source_dimension, confidence)
VALUES
('confirm_external_actions', 'true', 'first_law', 1.0),
('guardian_name', '"sihaoli"', 'first_law', 1.0);
