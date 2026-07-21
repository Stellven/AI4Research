-- ============================================================================
-- Solar Evolution Council - 多 Agent 决策委员会
-- Version: 2.0
-- Description: 多模型协作决策，自主发现问题、讨论、制定策略
-- ============================================================================

-- ============================================================================
-- 1. 决策委员会配置
-- ============================================================================

-- Agent 角色定义 (用户可配置)
CREATE TABLE IF NOT EXISTS evo_council_roles (
    role_id TEXT PRIMARY KEY,
    role_name TEXT NOT NULL,
    role_description TEXT NOT NULL,

    -- 模型配置 (用户可选)
    default_model TEXT NOT NULL,            -- 默认模型
    allowed_models JSON NOT NULL,           -- 允许的模型列表
    current_model TEXT,                     -- 当前使用的模型

    -- 职责
    responsibilities JSON NOT NULL,         -- 职责列表
    system_prompt TEXT NOT NULL,            -- 系统提示词

    -- 成本控制
    max_tokens_per_call INTEGER DEFAULT 2000,
    max_calls_per_hour INTEGER DEFAULT 10,
    priority INTEGER DEFAULT 50,            -- 调用优先级 (预算紧张时低优先级跳过)

    -- 投票权重
    vote_weight REAL DEFAULT 1.0,

    enabled BOOLEAN DEFAULT TRUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- 2. 决策会议记录
-- ============================================================================

-- 会议 (一次完整的决策过程)
CREATE TABLE IF NOT EXISTS evo_council_sessions (
    session_id TEXT PRIMARY KEY,

    -- 触发信息
    trigger_type TEXT NOT NULL CHECK(trigger_type IN (
        'scheduled',        -- 定时触发
        'anomaly',          -- 异常触发
        'user_request',     -- 用户请求
        'threshold_breach', -- 阈值突破
        'feedback_signal'   -- 反馈信号
    )),
    trigger_context JSON,                   -- 触发上下文

    -- 议题
    agenda TEXT NOT NULL,                   -- 讨论议题
    scope TEXT CHECK(scope IN ('cost', 'quality', 'latency', 'memory', 'routing', 'general')),

    -- 会议状态
    status TEXT NOT NULL CHECK(status IN (
        'initiated',        -- 已发起
        'observing',        -- 观察阶段
        'analyzing',        -- 分析阶段
        'proposing',        -- 提案阶段
        'reviewing',        -- 审核阶段
        'voting',           -- 投票阶段
        'approved',         -- 已批准
        'rejected',         -- 已拒绝
        'executing',        -- 执行中
        'validating',       -- 验证中
        'completed',        -- 已完成
        'failed'            -- 失败
    )) DEFAULT 'initiated',

    -- 预算控制
    budget_limit_usd REAL,                  -- 本次会议预算上限
    budget_used_usd REAL DEFAULT 0,         -- 已使用预算

    -- 时间戳
    started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME,

    -- 最终决策
    final_decision JSON,                    -- 最终决策
    execution_plan JSON,                    -- 执行计划

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 会议发言记录
CREATE TABLE IF NOT EXISTS evo_council_speeches (
    speech_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES evo_council_sessions(session_id),
    role_id TEXT NOT NULL REFERENCES evo_council_roles(role_id),

    -- 发言阶段
    phase TEXT NOT NULL CHECK(phase IN (
        'observation',      -- 观察报告
        'analysis',         -- 分析意见
        'proposal',         -- 提案
        'review',           -- 审核意见
        'vote',             -- 投票
        'rebuttal',         -- 反驳
        'consensus'         -- 共识确认
    )),

    -- 发言内容
    model_used TEXT NOT NULL,               -- 实际使用的模型
    input_prompt TEXT NOT NULL,             -- 输入提示
    output_content TEXT NOT NULL,           -- 输出内容
    structured_output JSON,                 -- 结构化输出

    -- Token 使用
    input_tokens INTEGER,
    output_tokens INTEGER,
    cost_usd REAL,

    -- 时间
    latency_ms INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 投票记录
CREATE TABLE IF NOT EXISTS evo_council_votes (
    vote_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES evo_council_sessions(session_id),
    role_id TEXT NOT NULL REFERENCES evo_council_roles(role_id),
    proposal_id TEXT NOT NULL,              -- 被投票的提案

    -- 投票
    vote TEXT NOT NULL CHECK(vote IN ('approve', 'reject', 'abstain')),
    vote_weight REAL NOT NULL,              -- 投票权重
    reasoning TEXT,                         -- 投票理由

    -- 条件
    conditions JSON,                        -- 附加条件 (如 "需要先做 X")

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(session_id, role_id, proposal_id)
);

-- ============================================================================
-- 3. 动态生成的策略 (由委员会创建，非硬编码)
-- ============================================================================

CREATE TABLE IF NOT EXISTS evo_dynamic_strategies (
    strategy_id TEXT PRIMARY KEY,

    -- 创建来源
    created_by_session TEXT REFERENCES evo_council_sessions(session_id),
    created_by_role TEXT,                   -- 提出者角色

    -- 策略定义 (由 AI 生成)
    strategy_name TEXT NOT NULL,
    strategy_description TEXT NOT NULL,
    strategy_type TEXT,

    -- 触发条件 (AI 生成的 SQL 或自然语言)
    trigger_condition_sql TEXT,             -- SQL 条件
    trigger_condition_nl TEXT,              -- 自然语言描述
    trigger_condition_type TEXT CHECK(trigger_condition_type IN ('sql', 'llm_eval', 'hybrid')),

    -- 执行动作 (AI 生成)
    action_plan JSON NOT NULL,              -- 动作计划
    action_type TEXT CHECK(action_type IN (
        'config_change',    -- 配置变更
        'routing_change',   -- 路由变更
        'model_switch',     -- 模型切换
        'memory_operation', -- 记忆操作
        'alert',            -- 告警
        'escalate',         -- 上报人工
        'custom_code'       -- 自定义代码
    )),

    -- 验证条件 (AI 生成)
    success_criteria_sql TEXT,
    success_criteria_nl TEXT,
    validation_window_minutes INTEGER DEFAULT 30,

    -- 回滚计划 (AI 生成)
    rollback_plan JSON,

    -- 信任度 (基于历史表现动态调整)
    confidence REAL DEFAULT 0.5,            -- 初始置信度
    execution_count INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    computed_success_rate REAL,

    -- 状态
    status TEXT CHECK(status IN ('draft', 'active', 'suspended', 'retired')) DEFAULT 'draft',
    retired_reason TEXT,

    -- 生命周期
    effective_from DATETIME,
    effective_until DATETIME,               -- NULL = 永久
    last_triggered DATETIME,
    last_executed DATETIME,

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- 4. 预算与成本控制
-- ============================================================================

CREATE TABLE IF NOT EXISTS evo_council_budget (
    budget_id TEXT PRIMARY KEY,
    budget_type TEXT NOT NULL CHECK(budget_type IN (
        'hourly',           -- 每小时预算
        'daily',            -- 每日预算
        'weekly',           -- 每周预算
        'monthly',          -- 每月预算
        'per_session'       -- 每次会议预算
    )),

    -- 预算金额
    budget_limit_usd REAL NOT NULL,
    budget_used_usd REAL DEFAULT 0,
    budget_remaining_usd REAL GENERATED ALWAYS AS (budget_limit_usd - budget_used_usd) STORED,

    -- 预算分配 (各角色)
    role_allocations JSON,                  -- {"observer": 0.1, "analyst": 0.3, ...}

    -- 超支策略
    overspend_action TEXT CHECK(overspend_action IN (
        'block',            -- 阻止调用
        'downgrade',        -- 降级到更便宜的模型
        'skip_low_priority',-- 跳过低优先级角色
        'alert_only'        -- 仅告警
    )) DEFAULT 'downgrade',

    -- 时间范围
    period_start DATETIME NOT NULL,
    period_end DATETIME NOT NULL,

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 模型定价表 (用于成本计算)
CREATE TABLE IF NOT EXISTS evo_model_pricing (
    model_id TEXT PRIMARY KEY,
    model_name TEXT NOT NULL,
    provider TEXT NOT NULL,

    -- 价格 (USD per 1M tokens)
    input_price_per_1m REAL NOT NULL,
    output_price_per_1m REAL NOT NULL,
    cached_input_price_per_1m REAL,

    -- 能力评估 (0-100)
    reasoning_score INTEGER,
    coding_score INTEGER,
    speed_score INTEGER,
    cost_efficiency_score INTEGER,

    -- 推荐用途
    recommended_roles JSON,                 -- ["observer", "analyst"]

    effective_from DATETIME DEFAULT CURRENT_TIMESTAMP,
    effective_until DATETIME
);

-- ============================================================================
-- 5. 初始化：委员会角色
-- ============================================================================

INSERT OR REPLACE INTO evo_council_roles (
    role_id, role_name, role_description,
    default_model, allowed_models, current_model,
    responsibilities, system_prompt,
    max_tokens_per_call, max_calls_per_hour, priority, vote_weight
) VALUES

-- Observer: 高频低成本监控
('role:observer', 'Observer', '系统观察者 - 持续监控指标，检测异常模式',
 'haiku', '["haiku", "gpt-4o-mini", "gemini-flash"]', NULL,
 '["监控系统指标", "检测异常模式", "生成观察报告", "标记潜在问题"]',
 '你是 Solar 系统的观察者。你的职责是：
1. 分析提供的系统指标数据
2. 识别异常模式和趋势
3. 生成简洁的观察报告
4. 标记需要关注的问题

输出格式：
```json
{
  "observations": [{"metric": "...", "status": "normal|warning|critical", "trend": "up|down|stable", "note": "..."}],
  "anomalies": [{"type": "...", "severity": 1-5, "description": "..."}],
  "recommendations": ["建议1", "建议2"]
}
```',
 1000, 60, 100, 0.5),

-- Analyst: 中等成本深度分析
('role:analyst', 'Analyst', '数据分析师 - 深度分析问题根因，提出假设',
 'sonnet', '["sonnet", "gpt-4o", "gemini-pro"]', NULL,
 '["分析观察报告", "进行根因分析", "提出假设", "量化影响"]',
 '你是 Solar 系统的数据分析师。你的职责是：
1. 分析 Observer 的观察报告
2. 进行根因分析，找出问题的真正原因
3. 提出假设并验证
4. 量化问题的影响

输出格式：
```json
{
  "root_causes": [{"cause": "...", "confidence": 0.0-1.0, "evidence": ["..."]}],
  "impact_assessment": {"cost_impact_usd": 0.0, "quality_impact": "low|medium|high", "affected_users": "..."},
  "hypotheses": [{"hypothesis": "...", "test_method": "...", "expected_outcome": "..."}]
}
```',
 2000, 20, 80, 1.0),

-- Strategist: 高成本战略决策
('role:strategist', 'Strategist', '策略制定者 - 设计优化方案，制定执行计划',
 'opus', '["opus", "gpt-4", "gemini-ultra"]', NULL,
 '["设计优化策略", "制定执行计划", "评估长期影响", "创建新策略"]',
 '你是 Solar 系统的首席策略师。你的职责是：
1. 基于分析结果设计优化策略
2. 制定详细的执行计划
3. 评估策略的长期影响
4. 创建可复用的自动化策略

重要：你创建的策略应该是通用的、可自动执行的，不是一次性的手动操作。

输出格式：
```json
{
  "strategy": {
    "name": "策略名称",
    "description": "策略描述",
    "trigger_condition": "SQL 或自然语言条件",
    "actions": [{"action": "...", "params": {...}}],
    "success_criteria": "验证成功的条件",
    "rollback_plan": {"steps": [...]}
  },
  "execution_plan": {
    "phases": [{"phase": 1, "actions": [...], "checkpoint": "..."}],
    "estimated_impact": {"cost_savings_usd": 0.0, "quality_improvement": "..."}
  },
  "risks": [{"risk": "...", "mitigation": "..."}]
}
```',
 4000, 5, 60, 2.0),

-- Guardian: 风险把关
('role:guardian', 'Guardian', '安全守护者 - 评估风险，审核策略，保护系统',
 'sonnet', '["sonnet", "gpt-4o", "gemini-pro"]', NULL,
 '["风险评估", "安全审核", "合规检查", "否决危险操作"]',
 '你是 Solar 系统的安全守护者。你的职责是：
1. 评估提案的风险
2. 检查安全和合规性
3. 识别潜在的负面影响
4. 对危险操作投反对票

你有权否决任何可能导致：
- 数据丢失
- 服务中断
- 成本失控
- 安全漏洞
的提案。

输出格式：
```json
{
  "risk_assessment": {
    "overall_risk": "low|medium|high|critical",
    "risks": [{"type": "...", "severity": 1-5, "likelihood": 0.0-1.0, "mitigation": "..."}]
  },
  "safety_checks": [{"check": "...", "passed": true|false, "note": "..."}],
  "recommendation": "approve|reject|modify",
  "required_modifications": ["..."],
  "veto": false,
  "veto_reason": null
}
```',
 2000, 15, 90, 1.5),

-- Executor: 执行者 (可以是较小的模型)
('role:executor', 'Executor', '执行者 - 将策略转化为具体操作',
 'haiku', '["haiku", "sonnet", "gpt-4o-mini"]', NULL,
 '["解析执行计划", "生成执行代码", "监控执行状态", "报告执行结果"]',
 '你是 Solar 系统的执行者。你的职责是：
1. 将批准的策略转化为具体的可执行操作
2. 生成必要的 SQL 语句或配置变更
3. 监控执行状态
4. 报告执行结果

输出格式：
```json
{
  "execution_steps": [
    {"step": 1, "type": "sql|config|api", "command": "...", "description": "..."}
  ],
  "pre_checks": [{"check": "...", "query": "..."}],
  "post_checks": [{"check": "...", "query": "...", "expected": "..."}]
}
```',
 1500, 30, 70, 0.5);

-- ============================================================================
-- 6. 初始化：模型定价
-- ============================================================================

INSERT OR REPLACE INTO evo_model_pricing (
    model_id, model_name, provider,
    input_price_per_1m, output_price_per_1m, cached_input_price_per_1m,
    reasoning_score, coding_score, speed_score, cost_efficiency_score,
    recommended_roles
) VALUES
('claude-opus-4-5', 'Claude Opus 4.5', 'anthropic', 15.0, 75.0, 7.5, 98, 95, 60, 40, '["strategist"]'),
('claude-sonnet-4', 'Claude Sonnet 4', 'anthropic', 3.0, 15.0, 1.5, 90, 92, 80, 75, '["analyst", "guardian"]'),
('claude-haiku-3-5', 'Claude Haiku 3.5', 'anthropic', 0.8, 4.0, 0.4, 75, 80, 95, 95, '["observer", "executor"]'),
('gpt-4o', 'GPT-4o', 'openai', 2.5, 10.0, NULL, 88, 90, 85, 80, '["analyst", "guardian"]'),
('gpt-4o-mini', 'GPT-4o Mini', 'openai', 0.15, 0.6, NULL, 70, 75, 95, 98, '["observer", "executor"]'),
('gemini-pro', 'Gemini Pro', 'google', 1.25, 5.0, NULL, 85, 85, 90, 85, '["analyst"]'),
('gemini-flash', 'Gemini Flash', 'google', 0.075, 0.3, NULL, 65, 70, 98, 99, '["observer"]');

-- ============================================================================
-- 7. 初始化：默认预算
-- ============================================================================

INSERT OR REPLACE INTO evo_council_budget (
    budget_id, budget_type,
    budget_limit_usd, budget_used_usd,
    role_allocations, overspend_action,
    period_start, period_end
) VALUES
('budget:daily', 'daily', 5.0, 0,
 '{"observer": 0.15, "analyst": 0.30, "strategist": 0.35, "guardian": 0.15, "executor": 0.05}',
 'downgrade',
 date('now'), date('now', '+1 day')),

('budget:per_session', 'per_session', 1.0, 0,
 '{"observer": 0.10, "analyst": 0.25, "strategist": 0.40, "guardian": 0.20, "executor": 0.05}',
 'skip_low_priority',
 datetime('now'), datetime('now', '+1 hour'));

-- ============================================================================
-- 8. 会议流程视图
-- ============================================================================

-- 当前活跃会议
CREATE VIEW IF NOT EXISTS v_evo_active_sessions AS
SELECT
    s.session_id,
    s.agenda,
    s.scope,
    s.status,
    s.budget_limit_usd,
    s.budget_used_usd,
    ROUND(100.0 * s.budget_used_usd / NULLIF(s.budget_limit_usd, 0), 1) AS budget_usage_pct,
    COUNT(DISTINCT sp.role_id) AS participating_roles,
    COUNT(sp.speech_id) AS total_speeches,
    s.started_at,
    ROUND((julianday('now') - julianday(s.started_at)) * 1440, 1) AS duration_minutes
FROM evo_council_sessions s
LEFT JOIN evo_council_speeches sp ON s.session_id = sp.session_id
WHERE s.status NOT IN ('completed', 'failed', 'rejected')
GROUP BY s.session_id;

-- 策略效果排名
CREATE VIEW IF NOT EXISTS v_evo_strategy_effectiveness AS
SELECT
    ds.strategy_id,
    ds.strategy_name,
    ds.strategy_type,
    ds.status,
    ds.execution_count,
    ds.success_count,
    ROUND(100.0 * ds.success_count / NULLIF(ds.execution_count, 0), 1) AS success_rate_pct,
    ds.confidence,
    ds.last_triggered,
    cs.session_id AS created_in_session,
    cs.agenda AS original_agenda
FROM evo_dynamic_strategies ds
LEFT JOIN evo_council_sessions cs ON ds.created_by_session = cs.session_id
ORDER BY ds.success_count DESC, ds.confidence DESC;

-- 预算使用情况
CREATE VIEW IF NOT EXISTS v_evo_budget_status AS
SELECT
    b.budget_id,
    b.budget_type,
    b.budget_limit_usd,
    b.budget_used_usd,
    b.budget_remaining_usd,
    ROUND(100.0 * b.budget_used_usd / NULLIF(b.budget_limit_usd, 0), 1) AS usage_pct,
    b.overspend_action,
    CASE
        WHEN b.budget_remaining_usd <= 0 THEN 'exhausted'
        WHEN b.budget_remaining_usd < b.budget_limit_usd * 0.2 THEN 'low'
        WHEN b.budget_remaining_usd < b.budget_limit_usd * 0.5 THEN 'moderate'
        ELSE 'healthy'
    END AS budget_health,
    b.period_start,
    b.period_end
FROM evo_council_budget b
WHERE b.period_end > datetime('now');

-- 角色成本分析
CREATE VIEW IF NOT EXISTS v_evo_role_cost_analysis AS
SELECT
    r.role_id,
    r.role_name,
    r.current_model,
    r.default_model,
    COUNT(sp.speech_id) AS total_speeches,
    SUM(sp.cost_usd) AS total_cost_usd,
    AVG(sp.cost_usd) AS avg_cost_per_speech,
    SUM(sp.input_tokens) AS total_input_tokens,
    SUM(sp.output_tokens) AS total_output_tokens,
    AVG(sp.latency_ms) AS avg_latency_ms
FROM evo_council_roles r
LEFT JOIN evo_council_speeches sp ON r.role_id = sp.role_id
    AND sp.created_at >= datetime('now', '-7 days')
GROUP BY r.role_id;

-- ============================================================================
-- 9. 触发器：预算控制
-- ============================================================================

-- 发言后更新会议预算
CREATE TRIGGER IF NOT EXISTS trg_update_session_budget
AFTER INSERT ON evo_council_speeches
BEGIN
    UPDATE evo_council_sessions
    SET budget_used_usd = budget_used_usd + COALESCE(NEW.cost_usd, 0)
    WHERE session_id = NEW.session_id;
END;

-- 发言后更新总预算
CREATE TRIGGER IF NOT EXISTS trg_update_total_budget
AFTER INSERT ON evo_council_speeches
BEGIN
    UPDATE evo_council_budget
    SET
        budget_used_usd = budget_used_usd + COALESCE(NEW.cost_usd, 0),
        updated_at = CURRENT_TIMESTAMP
    WHERE budget_type = 'daily'
      AND period_start <= date('now')
      AND period_end > date('now');
END;

-- 策略执行后更新统计
CREATE TRIGGER IF NOT EXISTS trg_update_strategy_stats
AFTER UPDATE OF status ON evo_optimization_executions
WHEN NEW.status IN ('success', 'failed', 'rolled_back')
BEGIN
    UPDATE evo_dynamic_strategies
    SET
        execution_count = execution_count + 1,
        success_count = success_count + CASE WHEN NEW.status = 'success' THEN 1 ELSE 0 END,
        computed_success_rate = 1.0 * (success_count + CASE WHEN NEW.status = 'success' THEN 1 ELSE 0 END) / (execution_count + 1),
        confidence = 0.7 * confidence + 0.3 * (CASE WHEN NEW.status = 'success' THEN 1.0 ELSE 0.0 END),
        last_executed = CURRENT_TIMESTAMP,
        updated_at = CURRENT_TIMESTAMP
    WHERE strategy_id = (
        SELECT strategy_id FROM evo_optimization_executions WHERE execution_id = NEW.execution_id
    );
END;

-- ============================================================================
-- 10. 索引
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_evo_speeches_session ON evo_council_speeches(session_id);
CREATE INDEX IF NOT EXISTS idx_evo_speeches_role ON evo_council_speeches(role_id);
CREATE INDEX IF NOT EXISTS idx_evo_votes_session ON evo_council_votes(session_id);
CREATE INDEX IF NOT EXISTS idx_evo_strategies_status ON evo_dynamic_strategies(status);
CREATE INDEX IF NOT EXISTS idx_evo_strategies_type ON evo_dynamic_strategies(strategy_type);
CREATE INDEX IF NOT EXISTS idx_evo_sessions_status ON evo_council_sessions(status);

-- ============================================================================
-- 架构说明
-- ============================================================================
/*
┌─────────────────────────────────────────────────────────────────────────────┐
│                     Multi-Agent Evolution Council                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                         决策流程                                      │    │
│  │                                                                       │    │
│  │   触发 → Observer(Haiku) → Analyst(Sonnet) → Strategist(Opus)        │    │
│  │                                    ↓                                  │    │
│  │   执行 ← Executor(Haiku) ← 投票 ← Guardian(Sonnet) ← 提案审核         │    │
│  │                                                                       │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                         预算控制                                      │    │
│  │                                                                       │    │
│  │   • 每日预算: $5 (可配置)                                             │    │
│  │   • 角色分配: Observer 15%, Analyst 30%, Strategist 35%...           │    │
│  │   • 超支策略: 降级模型 / 跳过低优先级 / 阻止                          │    │
│  │                                                                       │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                         模型选择                                      │    │
│  │                                                                       │    │
│  │   Observer:   Haiku / GPT-4o-mini / Gemini-Flash (便宜高频)           │    │
│  │   Analyst:    Sonnet / GPT-4o / Gemini-Pro (平衡)                    │    │
│  │   Strategist: Opus / GPT-4 / Gemini-Ultra (最强)                     │    │
│  │   Guardian:   Sonnet / GPT-4o (可靠)                                 │    │
│  │   Executor:   Haiku / Sonnet (按需)                                  │    │
│  │                                                                       │    │
│  │   * 用户可在 evo_council_roles.current_model 配置                    │    │
│  │                                                                       │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                         策略生命周期                                  │    │
│  │                                                                       │    │
│  │   由 AI 创建 → 委员会批准 → 自动执行 → 效果验证 → 信任度调整           │    │
│  │                     ↑                              ↓                  │    │
│  │                     └────── 失败则降低信任度 ←─────┘                   │    │
│  │                                                                       │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
*/
