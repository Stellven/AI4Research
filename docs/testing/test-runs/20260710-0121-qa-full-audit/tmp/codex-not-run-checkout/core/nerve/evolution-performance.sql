-- ============================================================================
-- Solar Evolution Performance System - Agent 绩效追踪与互评系统
-- Version: 1.0
-- Description: Agent 效率监控、互评打分、书记员机制、绩效优化
-- ============================================================================

-- ============================================================================
-- 1. Agent 执行效率追踪
-- ============================================================================

-- Agent 单次执行详情
CREATE TABLE IF NOT EXISTS evo_agent_executions (
    execution_id TEXT PRIMARY KEY,
    session_id TEXT REFERENCES evo_council_sessions(session_id),
    role_id TEXT NOT NULL REFERENCES evo_council_roles(role_id),
    phase TEXT NOT NULL,

    -- 执行详情
    model_used TEXT NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    total_tokens INTEGER GENERATED ALWAYS AS (input_tokens + output_tokens) STORED,

    -- 时间效率
    latency_ms INTEGER NOT NULL,
    time_to_first_token_ms INTEGER,
    tokens_per_second REAL GENERATED ALWAYS AS (1000.0 * output_tokens / NULLIF(latency_ms, 0)) STORED,

    -- 成本
    cost_usd REAL NOT NULL,
    cost_per_1k_tokens REAL GENERATED ALWAYS AS (1000.0 * cost_usd / NULLIF(total_tokens, 0)) STORED,

    -- 输出质量指标 (由后续 Agent 或 Secretary 填充)
    output_length INTEGER,                  -- 输出字符数
    structured_output_valid BOOLEAN,        -- 结构化输出是否有效
    json_parse_success BOOLEAN,             -- JSON 解析是否成功

    -- 结果
    execution_success BOOLEAN DEFAULT TRUE,
    error_type TEXT,
    error_message TEXT,

    -- 被引用情况 (后续 Agent 是否使用了这个输出)
    cited_by_count INTEGER DEFAULT 0,       -- 被后续 Agent 引用次数
    influenced_decision BOOLEAN,            -- 是否影响了最终决策

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Agent 绩效聚合 (按小时)
CREATE TABLE IF NOT EXISTS evo_agent_stats_hourly (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hour_bucket TEXT NOT NULL,              -- 'YYYY-MM-DD HH:00:00'
    role_id TEXT NOT NULL,
    model_used TEXT NOT NULL,

    -- 执行统计
    execution_count INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    error_count INTEGER DEFAULT 0,
    success_rate REAL GENERATED ALWAYS AS (100.0 * success_count / NULLIF(execution_count, 0)) STORED,

    -- Token 统计
    total_input_tokens INTEGER DEFAULT 0,
    total_output_tokens INTEGER DEFAULT 0,
    avg_input_tokens REAL,
    avg_output_tokens REAL,

    -- 时间统计
    total_latency_ms INTEGER DEFAULT 0,
    avg_latency_ms REAL,
    p50_latency_ms REAL,
    p95_latency_ms REAL,
    avg_tokens_per_second REAL,

    -- 成本统计
    total_cost_usd REAL DEFAULT 0,
    avg_cost_per_execution REAL,

    -- 质量统计 (来自互评)
    avg_quality_score REAL,                 -- 平均质量分
    avg_relevance_score REAL,               -- 平均相关性分
    avg_actionability_score REAL,           -- 平均可操作性分

    -- 影响力统计
    total_citations INTEGER DEFAULT 0,       -- 总被引用次数
    decision_influence_rate REAL,            -- 影响决策的比例

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(hour_bucket, role_id, model_used)
);

-- ============================================================================
-- 2. Agent 互评系统
-- ============================================================================

-- Agent 对 Agent 的评分
CREATE TABLE IF NOT EXISTS evo_agent_reviews (
    review_id TEXT PRIMARY KEY,
    session_id TEXT REFERENCES evo_council_sessions(session_id),

    -- 评分者和被评者
    reviewer_role_id TEXT NOT NULL REFERENCES evo_council_roles(role_id),
    reviewee_role_id TEXT NOT NULL REFERENCES evo_council_roles(role_id),
    reviewee_execution_id TEXT REFERENCES evo_agent_executions(execution_id),

    -- 评分维度 (1-5 分)
    relevance_score INTEGER CHECK(relevance_score BETWEEN 1 AND 5),       -- 相关性: 输出与议题的相关程度
    quality_score INTEGER CHECK(quality_score BETWEEN 1 AND 5),           -- 质量: 分析深度和准确性
    actionability_score INTEGER CHECK(actionability_score BETWEEN 1 AND 5), -- 可操作性: 建议是否可执行
    efficiency_score INTEGER CHECK(efficiency_score BETWEEN 1 AND 5),     -- 效率: Token 使用效率
    innovation_score INTEGER CHECK(innovation_score BETWEEN 1 AND 5),     -- 创新性: 是否有新颖见解

    -- 综合分 (加权平均)
    overall_score REAL GENERATED ALWAYS AS (
        (COALESCE(relevance_score, 3) * 0.25 +
         COALESCE(quality_score, 3) * 0.30 +
         COALESCE(actionability_score, 3) * 0.25 +
         COALESCE(efficiency_score, 3) * 0.10 +
         COALESCE(innovation_score, 3) * 0.10)
    ) STORED,

    -- 评语
    strengths JSON,                         -- 优点列表
    weaknesses JSON,                        -- 缺点列表
    suggestions JSON,                       -- 改进建议
    comment TEXT,                           -- 自由评语

    -- 是否采纳了被评者的建议
    adopted_suggestions BOOLEAN,
    adoption_reason TEXT,

    -- 元数据
    review_model TEXT,                      -- 评分时使用的模型
    review_tokens INTEGER,                  -- 评分消耗的 token
    review_cost_usd REAL,

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 互评规则配置
CREATE TABLE IF NOT EXISTS evo_review_rules (
    rule_id TEXT PRIMARY KEY,
    reviewer_role TEXT NOT NULL,            -- 评分者角色
    reviewee_role TEXT NOT NULL,            -- 被评者角色
    review_phase TEXT NOT NULL,             -- 在哪个阶段评分

    -- 评分权重 (不同角色对不同维度的评分权重不同)
    relevance_weight REAL DEFAULT 0.25,
    quality_weight REAL DEFAULT 0.30,
    actionability_weight REAL DEFAULT 0.25,
    efficiency_weight REAL DEFAULT 0.10,
    innovation_weight REAL DEFAULT 0.10,

    -- 是否启用
    enabled BOOLEAN DEFAULT TRUE,

    UNIQUE(reviewer_role, reviewee_role)
);

-- ============================================================================
-- 3. Secretary Agent (书记员) 专用表
-- ============================================================================

-- 会议纪要
CREATE TABLE IF NOT EXISTS evo_meeting_minutes (
    minutes_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES evo_council_sessions(session_id),

    -- 会议摘要
    executive_summary TEXT NOT NULL,        -- 执行摘要
    key_decisions JSON NOT NULL,            -- 关键决策列表
    action_items JSON NOT NULL,             -- 待办事项

    -- 参与统计
    participating_roles JSON NOT NULL,      -- 参与的角色
    total_speeches INTEGER,                 -- 总发言数
    total_tokens_used INTEGER,              -- 总 Token 消耗
    total_cost_usd REAL,                    -- 总成本

    -- 时间统计
    session_duration_minutes REAL,          -- 会议时长
    avg_response_time_ms REAL,              -- 平均响应时间

    -- 效率评估
    efficiency_rating TEXT CHECK(efficiency_rating IN ('excellent', 'good', 'fair', 'poor')),
    efficiency_notes TEXT,

    -- 各 Agent 表现评分 (Secretary 综合评定)
    role_performance_scores JSON,           -- {"role:observer": 4.2, "role:analyst": 3.8, ...}

    -- 改进建议
    improvement_suggestions JSON,           -- 下次会议的改进建议

    -- 元数据
    generated_by_model TEXT,
    generation_tokens INTEGER,
    generation_cost_usd REAL,

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 书记员对各 Agent 的综合评定
CREATE TABLE IF NOT EXISTS evo_secretary_assessments (
    assessment_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES evo_council_sessions(session_id),
    role_id TEXT NOT NULL REFERENCES evo_council_roles(role_id),

    -- 表现评分 (1-5)
    contribution_score INTEGER CHECK(contribution_score BETWEEN 1 AND 5),   -- 贡献度
    accuracy_score INTEGER CHECK(accuracy_score BETWEEN 1 AND 5),           -- 准确性
    timeliness_score INTEGER CHECK(timeliness_score BETWEEN 1 AND 5),       -- 及时性
    collaboration_score INTEGER CHECK(collaboration_score BETWEEN 1 AND 5), -- 协作性
    value_add_score INTEGER CHECK(value_add_score BETWEEN 1 AND 5),         -- 增值贡献

    -- 综合分
    overall_score REAL GENERATED ALWAYS AS (
        (COALESCE(contribution_score, 3) * 0.30 +
         COALESCE(accuracy_score, 3) * 0.25 +
         COALESCE(timeliness_score, 3) * 0.15 +
         COALESCE(collaboration_score, 3) * 0.15 +
         COALESCE(value_add_score, 3) * 0.15)
    ) STORED,

    -- 具体评价
    highlights JSON,                        -- 亮点
    concerns JSON,                          -- 问题
    recommendations JSON,                   -- 建议

    -- 与历史对比
    score_vs_avg REAL,                      -- 与该角色历史平均分的差异
    trend TEXT CHECK(trend IN ('improving', 'stable', 'declining')),

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(session_id, role_id)
);

-- ============================================================================
-- 4. 绩效基准线
-- ============================================================================

-- Agent 绩效基准 (用于异常检测)
CREATE TABLE IF NOT EXISTS evo_agent_baselines (
    baseline_id TEXT PRIMARY KEY,
    role_id TEXT NOT NULL REFERENCES evo_council_roles(role_id),
    model_name TEXT,                        -- NULL = 所有模型的综合基准

    -- 效率基准
    baseline_latency_ms REAL,
    baseline_tokens_per_second REAL,
    baseline_cost_per_execution REAL,

    -- 质量基准
    baseline_success_rate REAL,
    baseline_quality_score REAL,
    baseline_relevance_score REAL,

    -- 阈值 (超过则告警)
    latency_warning_threshold REAL,
    latency_critical_threshold REAL,
    quality_warning_threshold REAL,
    cost_warning_threshold REAL,

    -- 计算周期
    calculation_period_days INTEGER DEFAULT 30,
    sample_size INTEGER,                    -- 样本数量
    last_calculated DATETIME,

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(role_id, model_name)
);

-- ============================================================================
-- 5. 初始化：Secretary 角色
-- ============================================================================

INSERT OR REPLACE INTO evo_council_roles (
    role_id, role_name, role_description,
    default_model, allowed_models, current_model,
    responsibilities, system_prompt,
    max_tokens_per_call, max_calls_per_hour, priority, vote_weight
) VALUES (
    'role:secretary',
    'Secretary',
    '书记员 - 记录会议、评估各 Agent 表现、生成改进建议',
    'sonnet',
    '["sonnet", "haiku", "gpt-4o", "gpt-4o-mini"]',
    NULL,
    '["记录会议纪要", "评估 Agent 表现", "追踪决策执行", "生成改进建议", "维护绩效基准"]',
    '你是 Solar 系统的书记员 (Secretary)。你的职责是：

1. **记录会议纪要**
   - 总结会议讨论要点
   - 记录关键决策
   - 列出待办事项

2. **评估各 Agent 表现**
   对每个参与的 Agent 进行评分 (1-5分)：
   - 贡献度: 对讨论的实质性贡献
   - 准确性: 分析和建议的准确程度
   - 及时性: 响应速度和效率
   - 协作性: 与其他 Agent 的配合
   - 增值贡献: 是否带来独特价值

3. **生成改进建议**
   - 指出会议流程中的问题
   - 建议如何提升效率
   - 推荐 Agent 配置调整

输出格式：
```json
{
  "minutes": {
    "executive_summary": "一句话总结",
    "key_decisions": ["决策1", "决策2"],
    "action_items": [{"item": "...", "owner": "role:xxx", "deadline": "..."}]
  },
  "role_assessments": {
    "role:observer": {
      "contribution": 4, "accuracy": 4, "timeliness": 5, "collaboration": 4, "value_add": 3,
      "highlights": ["快速识别异常"],
      "concerns": ["分析深度不足"],
      "recommendations": ["增加上下文信息"]
    }
  },
  "efficiency_rating": "good",
  "improvement_suggestions": ["建议1", "建议2"]
}
```',
    3000, 20, 85, 0.5
);

-- ============================================================================
-- 6. 初始化：互评规则
-- ============================================================================

-- Analyst 评价 Observer
INSERT OR REPLACE INTO evo_review_rules (rule_id, reviewer_role, reviewee_role, review_phase,
    relevance_weight, quality_weight, actionability_weight, efficiency_weight, innovation_weight)
VALUES ('rule:analyst_reviews_observer', 'role:analyst', 'role:observer', 'analysis',
    0.35, 0.25, 0.20, 0.15, 0.05);

-- Strategist 评价 Analyst
INSERT OR REPLACE INTO evo_review_rules (rule_id, reviewer_role, reviewee_role, review_phase,
    relevance_weight, quality_weight, actionability_weight, efficiency_weight, innovation_weight)
VALUES ('rule:strategist_reviews_analyst', 'role:strategist', 'role:analyst', 'proposing',
    0.25, 0.35, 0.20, 0.10, 0.10);

-- Guardian 评价 Strategist
INSERT OR REPLACE INTO evo_review_rules (rule_id, reviewer_role, reviewee_role, review_phase,
    relevance_weight, quality_weight, actionability_weight, efficiency_weight, innovation_weight)
VALUES ('rule:guardian_reviews_strategist', 'role:guardian', 'role:strategist', 'reviewing',
    0.20, 0.30, 0.30, 0.05, 0.15);

-- Executor 评价 Strategist (执行可行性)
INSERT OR REPLACE INTO evo_review_rules (rule_id, reviewer_role, reviewee_role, review_phase,
    relevance_weight, quality_weight, actionability_weight, efficiency_weight, innovation_weight)
VALUES ('rule:executor_reviews_strategist', 'role:executor', 'role:strategist', 'consensus',
    0.15, 0.20, 0.45, 0.15, 0.05);

-- Secretary 评价所有角色 (综合评定)
INSERT OR REPLACE INTO evo_review_rules (rule_id, reviewer_role, reviewee_role, review_phase,
    relevance_weight, quality_weight, actionability_weight, efficiency_weight, innovation_weight)
VALUES
('rule:secretary_reviews_observer', 'role:secretary', 'role:observer', 'final', 0.30, 0.25, 0.20, 0.15, 0.10),
('rule:secretary_reviews_analyst', 'role:secretary', 'role:analyst', 'final', 0.25, 0.35, 0.20, 0.10, 0.10),
('rule:secretary_reviews_strategist', 'role:secretary', 'role:strategist', 'final', 0.20, 0.30, 0.25, 0.10, 0.15),
('rule:secretary_reviews_guardian', 'role:secretary', 'role:guardian', 'final', 0.25, 0.35, 0.25, 0.10, 0.05),
('rule:secretary_reviews_executor', 'role:secretary', 'role:executor', 'final', 0.20, 0.25, 0.35, 0.15, 0.05);

-- ============================================================================
-- 7. 触发器：自动更新统计
-- ============================================================================

-- 执行完成后自动更新小时统计
CREATE TRIGGER IF NOT EXISTS trg_update_agent_hourly_stats
AFTER INSERT ON evo_agent_executions
BEGIN
    INSERT INTO evo_agent_stats_hourly (
        hour_bucket, role_id, model_used,
        execution_count, success_count, error_count,
        total_input_tokens, total_output_tokens,
        avg_input_tokens, avg_output_tokens,
        total_latency_ms, avg_latency_ms,
        total_cost_usd, avg_cost_per_execution
    )
    VALUES (
        strftime('%Y-%m-%d %H:00:00', NEW.created_at),
        NEW.role_id,
        NEW.model_used,
        1,
        CASE WHEN NEW.execution_success THEN 1 ELSE 0 END,
        CASE WHEN NEW.execution_success THEN 0 ELSE 1 END,
        NEW.input_tokens,
        NEW.output_tokens,
        NEW.input_tokens,
        NEW.output_tokens,
        NEW.latency_ms,
        NEW.latency_ms,
        NEW.cost_usd,
        NEW.cost_usd
    )
    ON CONFLICT(hour_bucket, role_id, model_used) DO UPDATE SET
        execution_count = execution_count + 1,
        success_count = success_count + excluded.success_count,
        error_count = error_count + excluded.error_count,
        total_input_tokens = total_input_tokens + excluded.total_input_tokens,
        total_output_tokens = total_output_tokens + excluded.total_output_tokens,
        avg_input_tokens = (total_input_tokens + excluded.total_input_tokens) / (execution_count + 1),
        avg_output_tokens = (total_output_tokens + excluded.total_output_tokens) / (execution_count + 1),
        total_latency_ms = total_latency_ms + excluded.total_latency_ms,
        avg_latency_ms = (total_latency_ms + excluded.total_latency_ms) / (execution_count + 1),
        total_cost_usd = total_cost_usd + excluded.total_cost_usd,
        avg_cost_per_execution = (total_cost_usd + excluded.total_cost_usd) / (execution_count + 1),
        updated_at = CURRENT_TIMESTAMP;
END;

-- 互评后自动更新质量统计
CREATE TRIGGER IF NOT EXISTS trg_update_quality_stats_on_review
AFTER INSERT ON evo_agent_reviews
BEGIN
    UPDATE evo_agent_stats_hourly
    SET
        avg_quality_score = (
            SELECT AVG(quality_score) FROM evo_agent_reviews
            WHERE reviewee_role_id = NEW.reviewee_role_id
              AND created_at >= datetime(evo_agent_stats_hourly.hour_bucket)
              AND created_at < datetime(evo_agent_stats_hourly.hour_bucket, '+1 hour')
        ),
        avg_relevance_score = (
            SELECT AVG(relevance_score) FROM evo_agent_reviews
            WHERE reviewee_role_id = NEW.reviewee_role_id
              AND created_at >= datetime(evo_agent_stats_hourly.hour_bucket)
              AND created_at < datetime(evo_agent_stats_hourly.hour_bucket, '+1 hour')
        ),
        avg_actionability_score = (
            SELECT AVG(actionability_score) FROM evo_agent_reviews
            WHERE reviewee_role_id = NEW.reviewee_role_id
              AND created_at >= datetime(evo_agent_stats_hourly.hour_bucket)
              AND created_at < datetime(evo_agent_stats_hourly.hour_bucket, '+1 hour')
        ),
        updated_at = CURRENT_TIMESTAMP
    WHERE role_id = NEW.reviewee_role_id
      AND hour_bucket = strftime('%Y-%m-%d %H:00:00', NEW.created_at);
END;

-- ============================================================================
-- 8. 视图：绩效仪表盘
-- ============================================================================

-- Agent 实时绩效排名
CREATE VIEW IF NOT EXISTS v_evo_agent_performance_ranking AS
SELECT
    r.role_id,
    r.role_name,
    r.current_model,
    s.execution_count AS executions_24h,
    ROUND(s.success_rate, 1) AS success_rate_pct,
    ROUND(s.avg_latency_ms, 0) AS avg_latency_ms,
    ROUND(s.avg_cost_per_execution, 4) AS avg_cost_usd,
    ROUND(s.avg_quality_score, 2) AS avg_quality,
    ROUND(s.avg_relevance_score, 2) AS avg_relevance,
    ROUND(s.total_cost_usd, 3) AS total_cost_24h,
    RANK() OVER (ORDER BY s.avg_quality_score DESC NULLS LAST) AS quality_rank,
    RANK() OVER (ORDER BY s.success_rate DESC NULLS LAST) AS reliability_rank,
    RANK() OVER (ORDER BY s.avg_cost_per_execution ASC NULLS LAST) AS cost_efficiency_rank
FROM evo_council_roles r
LEFT JOIN (
    SELECT
        role_id,
        SUM(execution_count) AS execution_count,
        100.0 * SUM(success_count) / NULLIF(SUM(execution_count), 0) AS success_rate,
        SUM(total_latency_ms) / NULLIF(SUM(execution_count), 0) AS avg_latency_ms,
        SUM(total_cost_usd) / NULLIF(SUM(execution_count), 0) AS avg_cost_per_execution,
        AVG(avg_quality_score) AS avg_quality_score,
        AVG(avg_relevance_score) AS avg_relevance_score,
        SUM(total_cost_usd) AS total_cost_usd
    FROM evo_agent_stats_hourly
    WHERE hour_bucket >= datetime('now', '-24 hours')
    GROUP BY role_id
) s ON r.role_id = s.role_id
WHERE r.enabled = TRUE
ORDER BY quality_rank;

-- Agent 绩效趋势 (过去 7 天)
CREATE VIEW IF NOT EXISTS v_evo_agent_performance_trend AS
SELECT
    r.role_id,
    r.role_name,
    date(s.hour_bucket) AS date,
    SUM(s.execution_count) AS executions,
    ROUND(100.0 * SUM(s.success_count) / NULLIF(SUM(s.execution_count), 0), 1) AS success_rate,
    ROUND(AVG(s.avg_latency_ms), 0) AS avg_latency_ms,
    ROUND(SUM(s.total_cost_usd), 3) AS total_cost,
    ROUND(AVG(s.avg_quality_score), 2) AS avg_quality
FROM evo_council_roles r
LEFT JOIN evo_agent_stats_hourly s ON r.role_id = s.role_id
WHERE s.hour_bucket >= datetime('now', '-7 days')
GROUP BY r.role_id, date(s.hour_bucket)
ORDER BY r.role_id, date;

-- 互评关系矩阵
CREATE VIEW IF NOT EXISTS v_evo_review_matrix AS
SELECT
    reviewer.role_name AS reviewer,
    reviewee.role_name AS reviewee,
    COUNT(r.review_id) AS review_count,
    ROUND(AVG(r.overall_score), 2) AS avg_score,
    ROUND(AVG(r.quality_score), 2) AS avg_quality,
    ROUND(AVG(r.relevance_score), 2) AS avg_relevance,
    ROUND(AVG(r.actionability_score), 2) AS avg_actionability,
    ROUND(100.0 * SUM(CASE WHEN r.adopted_suggestions THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 1) AS adoption_rate
FROM evo_agent_reviews r
JOIN evo_council_roles reviewer ON r.reviewer_role_id = reviewer.role_id
JOIN evo_council_roles reviewee ON r.reviewee_role_id = reviewee.role_id
WHERE r.created_at >= datetime('now', '-30 days')
GROUP BY r.reviewer_role_id, r.reviewee_role_id;

-- 需要优化的 Agent
CREATE VIEW IF NOT EXISTS v_evo_agents_need_optimization AS
SELECT
    r.role_id,
    r.role_name,
    r.current_model,
    b.baseline_quality_score,
    s.avg_quality_score AS current_quality,
    ROUND(s.avg_quality_score - b.baseline_quality_score, 2) AS quality_delta,
    b.baseline_latency_ms,
    s.avg_latency_ms AS current_latency,
    ROUND(100.0 * (s.avg_latency_ms - b.baseline_latency_ms) / NULLIF(b.baseline_latency_ms, 0), 1) AS latency_delta_pct,
    CASE
        WHEN s.avg_quality_score < b.quality_warning_threshold THEN 'quality_degraded'
        WHEN s.avg_latency_ms > b.latency_warning_threshold THEN 'latency_high'
        WHEN s.avg_cost_per_execution > b.cost_warning_threshold THEN 'cost_high'
        ELSE 'unknown'
    END AS issue_type,
    CASE
        WHEN s.avg_quality_score < b.baseline_quality_score * 0.8 THEN '考虑升级模型'
        WHEN s.avg_latency_ms > b.baseline_latency_ms * 1.5 THEN '检查网络或降级模型'
        WHEN s.avg_cost_per_execution > b.baseline_cost_per_execution * 1.3 THEN '优化提示词或降级模型'
        ELSE '观察中'
    END AS recommendation
FROM evo_council_roles r
JOIN evo_agent_baselines b ON r.role_id = b.role_id
LEFT JOIN (
    SELECT
        role_id,
        AVG(avg_quality_score) AS avg_quality_score,
        AVG(avg_latency_ms) AS avg_latency_ms,
        AVG(avg_cost_per_execution) AS avg_cost_per_execution
    FROM evo_agent_stats_hourly
    WHERE hour_bucket >= datetime('now', '-24 hours')
    GROUP BY role_id
) s ON r.role_id = s.role_id
WHERE r.enabled = TRUE
  AND (
    s.avg_quality_score < b.quality_warning_threshold
    OR s.avg_latency_ms > b.latency_warning_threshold
    OR s.avg_cost_per_execution > b.cost_warning_threshold
  );

-- Secretary 评定汇总
CREATE VIEW IF NOT EXISTS v_evo_secretary_summary AS
SELECT
    r.role_id,
    r.role_name,
    COUNT(sa.assessment_id) AS assessment_count,
    ROUND(AVG(sa.overall_score), 2) AS avg_overall_score,
    ROUND(AVG(sa.contribution_score), 2) AS avg_contribution,
    ROUND(AVG(sa.accuracy_score), 2) AS avg_accuracy,
    ROUND(AVG(sa.collaboration_score), 2) AS avg_collaboration,
    SUM(CASE WHEN sa.trend = 'improving' THEN 1 ELSE 0 END) AS improving_sessions,
    SUM(CASE WHEN sa.trend = 'declining' THEN 1 ELSE 0 END) AS declining_sessions,
    (
        SELECT json_group_array(json_extract(value, '$'))
        FROM (
            SELECT value FROM json_each(sa.recommendations)
            ORDER BY sa.created_at DESC
            LIMIT 3
        )
    ) AS recent_recommendations
FROM evo_council_roles r
LEFT JOIN evo_secretary_assessments sa ON r.role_id = sa.role_id
WHERE sa.created_at >= datetime('now', '-30 days')
GROUP BY r.role_id;

-- ============================================================================
-- 9. 索引
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_evo_agent_exec_session ON evo_agent_executions(session_id);
CREATE INDEX IF NOT EXISTS idx_evo_agent_exec_role ON evo_agent_executions(role_id);
CREATE INDEX IF NOT EXISTS idx_evo_agent_exec_created ON evo_agent_executions(created_at);
CREATE INDEX IF NOT EXISTS idx_evo_reviews_session ON evo_agent_reviews(session_id);
CREATE INDEX IF NOT EXISTS idx_evo_reviews_reviewee ON evo_agent_reviews(reviewee_role_id);
CREATE INDEX IF NOT EXISTS idx_evo_stats_hour ON evo_agent_stats_hourly(hour_bucket);
CREATE INDEX IF NOT EXISTS idx_evo_minutes_session ON evo_meeting_minutes(session_id);
CREATE INDEX IF NOT EXISTS idx_evo_assessments_session ON evo_secretary_assessments(session_id);

-- ============================================================================
-- 架构说明
-- ============================================================================
/*
┌─────────────────────────────────────────────────────────────────────────────┐
│                    Agent 绩效追踪与互评系统                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                         执行追踪                                      │    │
│  │                                                                       │    │
│  │   evo_agent_executions: 每次执行的详细记录                            │    │
│  │   ├─ 时间效率: latency_ms, tokens_per_second                         │    │
│  │   ├─ 成本效率: cost_usd, cost_per_1k_tokens                          │    │
│  │   └─ 影响力: cited_by_count, influenced_decision                     │    │
│  │                                                                       │    │
│  │   evo_agent_stats_hourly: 小时级聚合统计                              │    │
│  │                                                                       │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                    ↓                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                         互评机制                                      │    │
│  │                                                                       │    │
│  │   评分流向:                                                           │    │
│  │   Observer ←── Analyst ←── Strategist ←── Guardian                   │    │
│  │                    ↑              ↑                                   │    │
│  │                    └── Executor ──┘                                   │    │
│  │                                                                       │    │
│  │   评分维度 (1-5):                                                     │    │
│  │   ├─ 相关性 (relevance): 输出与议题的相关程度                         │    │
│  │   ├─ 质量 (quality): 分析深度和准确性                                 │    │
│  │   ├─ 可操作性 (actionability): 建议是否可执行                         │    │
│  │   ├─ 效率 (efficiency): Token 使用效率                                │    │
│  │   └─ 创新性 (innovation): 是否有新颖见解                              │    │
│  │                                                                       │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                    ↓                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                     Secretary (书记员)                                │    │
│  │                                                                       │    │
│  │   职责:                                                               │    │
│  │   1. 记录会议纪要 (evo_meeting_minutes)                               │    │
│  │   2. 综合评定各 Agent (evo_secretary_assessments)                     │    │
│  │   3. 生成改进建议                                                     │    │
│  │   4. 追踪绩效趋势                                                     │    │
│  │                                                                       │    │
│  │   评定维度:                                                           │    │
│  │   ├─ 贡献度 (contribution): 对讨论的实质性贡献                        │    │
│  │   ├─ 准确性 (accuracy): 分析的准确程度                                │    │
│  │   ├─ 及时性 (timeliness): 响应速度                                    │    │
│  │   ├─ 协作性 (collaboration): 与其他 Agent 的配合                      │    │
│  │   └─ 增值贡献 (value_add): 独特价值                                   │    │
│  │                                                                       │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                    ↓                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                     绩效优化闭环                                      │    │
│  │                                                                       │    │
│  │   evo_agent_baselines: 绩效基准线                                     │    │
│  │   v_evo_agents_need_optimization: 识别需要优化的 Agent                │    │
│  │                                                                       │    │
│  │   优化动作:                                                           │    │
│  │   ├─ 质量下降 → 升级模型                                              │    │
│  │   ├─ 延迟过高 → 降级模型或检查网络                                    │    │
│  │   ├─ 成本过高 → 优化提示词或降级模型                                  │    │
│  │   └─ 协作差 → 调整互评权重                                            │    │
│  │                                                                       │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
*/
