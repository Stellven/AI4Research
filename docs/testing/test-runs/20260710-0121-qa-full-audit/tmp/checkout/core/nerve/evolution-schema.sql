-- Solar Self-Evolution System - Schema Definition
-- Version: 1.0
-- Description: 自演进系统 - 使用追踪、记忆系统、反馈循环、持续优化
-- Reference: LLM Observability Best Practices 2025, AWS AgentCore Memory, MLOps Maturity Model

-- ==================== 1. 会话与追踪 (Session & Tracing) ====================
-- 基于分布式追踪最佳实践: Session → Trace → Span 三层结构

-- 会话表 (多轮对话的顶层容器)
CREATE TABLE IF NOT EXISTS evo_sessions (
    session_id TEXT PRIMARY KEY,            -- UUID
    user_id TEXT,                           -- 用户标识 (可选)
    project_id TEXT,                        -- 项目/工作区
    started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    ended_at DATETIME,
    duration_seconds INTEGER,

    -- 会话级元数据
    initial_context JSON,                   -- 初始上下文 (项目、文件、模式)
    tags JSON,                              -- 标签 ["dev", "research", "office"]
    mode TEXT,                              -- 模式: dev, office, research

    -- 会话级统计 (汇总)
    total_turns INTEGER DEFAULT 0,          -- 总轮次
    total_input_tokens INTEGER DEFAULT 0,
    total_output_tokens INTEGER DEFAULT 0,
    total_cached_tokens INTEGER DEFAULT 0,
    total_cost_usd REAL DEFAULT 0,
    total_latency_ms INTEGER DEFAULT 0,

    -- 会话结果
    final_status TEXT CHECK(final_status IN ('completed', 'abandoned', 'error', 'timeout')),
    satisfaction_score INTEGER,             -- 用户满意度 (1-5, 可选)
    summary TEXT,                           -- AI 生成的会话摘要

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 追踪表 (单次请求的完整处理链)
CREATE TABLE IF NOT EXISTS evo_traces (
    trace_id TEXT PRIMARY KEY,              -- UUID
    session_id TEXT REFERENCES evo_sessions(session_id) ON DELETE CASCADE,
    parent_trace_id TEXT,                   -- 父追踪 (用于嵌套请求)

    -- 请求信息
    user_query TEXT NOT NULL,               -- 用户原始输入
    query_type TEXT,                        -- 查询类型: command, question, instruction, etc.
    intent JSON,                            -- 解析后的意图 {"action": "remind", "object": "meeting"}

    -- 执行信息
    entry_point TEXT,                       -- 入口: chat, skill, agent, shortcut
    execution_path JSON,                    -- 执行路径 ["agent:coder", "tool:Edit", "tool:Write"]
    retry_count INTEGER DEFAULT 0,          -- 重试次数 (用于学习信号)

    -- 时间戳
    started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    ended_at DATETIME,
    latency_ms INTEGER,

    -- 结果
    status TEXT CHECK(status IN ('success', 'partial', 'failed', 'timeout', 'cancelled')),
    error_type TEXT,                        -- 错误类型
    error_message TEXT,                     -- 错误信息

    -- Token 使用 (追踪级汇总)
    total_input_tokens INTEGER DEFAULT 0,
    total_output_tokens INTEGER DEFAULT 0,
    total_cached_tokens INTEGER DEFAULT 0,
    total_cost_usd REAL DEFAULT 0,

    -- 响应
    response_summary TEXT,                  -- 响应摘要 (用于记忆)
    response_quality_score REAL,            -- AI 自评质量分 (0-1)

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Span 表 (追踪内的单个操作单元)
CREATE TABLE IF NOT EXISTS evo_spans (
    span_id TEXT PRIMARY KEY,               -- UUID
    trace_id TEXT NOT NULL REFERENCES evo_traces(trace_id) ON DELETE CASCADE,
    parent_span_id TEXT,                    -- 父 Span (用于嵌套)

    -- Span 类型
    span_type TEXT NOT NULL CHECK(span_type IN (
        'llm_call',         -- LLM 调用
        'tool_call',        -- 工具调用
        'agent_call',       -- Agent 调用
        'skill_call',       -- Skill 调用
        'shortcut_call',    -- Shortcut 调用
        'mcp_call',         -- MCP 调用
        'retrieval',        -- 检索操作 (RAG)
        'embedding',        -- 向量嵌入
        'custom'            -- 自定义
    )),
    span_name TEXT NOT NULL,                -- 操作名称

    -- 时间
    started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    ended_at DATETIME,
    latency_ms INTEGER,

    -- 状态
    status TEXT CHECK(status IN ('success', 'failed', 'timeout', 'cancelled')),
    error_message TEXT,

    -- 输入输出
    input_data JSON,                        -- 输入数据 (truncated if large)
    output_data JSON,                       -- 输出数据 (truncated if large)

    -- Token/成本 (用于聚合)
    input_tokens INTEGER DEFAULT 0,         -- 输入 tokens
    output_tokens INTEGER DEFAULT 0,        -- 输出 tokens
    cached_tokens INTEGER DEFAULT 0,        -- 缓存 tokens
    cost_usd REAL DEFAULT 0,                -- 成本 USD

    -- 元数据
    metadata JSON                           -- 额外元数据
);

-- ==================== 2. LLM 调用详情 (LLM Call Details) ====================
-- 详细记录每次 LLM 调用，用于成本分析和优化

-- LLM 调用表
CREATE TABLE IF NOT EXISTS evo_llm_calls (
    call_id TEXT PRIMARY KEY,               -- UUID
    span_id TEXT NOT NULL REFERENCES evo_spans(span_id) ON DELETE CASCADE,
    trace_id TEXT NOT NULL,                 -- 冗余，便于查询
    session_id TEXT,                        -- 冗余，便于查询

    -- 模型信息
    provider TEXT NOT NULL,                 -- anthropic, openai, deepseek, etc.
    model_name TEXT NOT NULL,               -- claude-opus-4-5-20251101
    model_alias TEXT,                       -- opus, sonnet, haiku

    -- 请求参数
    temperature REAL,
    max_tokens INTEGER,
    top_p REAL,
    top_k INTEGER,
    stop_sequences JSON,
    system_prompt_hash TEXT,                -- 系统提示的 hash (用于去重存储)

    -- Token 使用 (详细分解)
    input_tokens INTEGER DEFAULT 0,         -- 输入 tokens
    output_tokens INTEGER DEFAULT 0,        -- 输出 tokens
    cached_input_tokens INTEGER DEFAULT 0,  -- 缓存命中的输入 tokens
    cached_output_tokens INTEGER DEFAULT 0, -- 缓存的输出 tokens
    audio_tokens INTEGER DEFAULT 0,         -- 音频 tokens (如适用)
    image_tokens INTEGER DEFAULT 0,         -- 图像 tokens (如适用)
    reasoning_tokens INTEGER DEFAULT 0,     -- 推理 tokens (如适用)

    -- 成本计算
    input_cost_usd REAL DEFAULT 0,
    output_cost_usd REAL DEFAULT 0,
    cached_cost_usd REAL DEFAULT 0,
    total_cost_usd REAL DEFAULT 0,

    -- 性能指标
    latency_ms INTEGER,                     -- 总延迟
    time_to_first_token_ms INTEGER,         -- 首 token 时间 (TTFT)
    tokens_per_second REAL,                 -- 生成速度

    -- 上下文信息
    context_files JSON,                     -- 涉及的文件 ["src/main.ts", "README.md"]
    context_type TEXT,                      -- 上下文类型: code, docs, mixed
    context_size_tokens INTEGER,            -- 上下文大小

    -- 质量指标 (可选, 异步填充)
    response_quality REAL,                  -- 响应质量 (0-1)
    hallucination_risk REAL,                -- 幻觉风险 (0-1)
    relevance_score REAL,                   -- 相关性 (0-1)

    -- 错误信息
    error_code TEXT,                        -- 错误代码 (如适用)
    error_message TEXT,                     -- 错误信息

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 系统提示存储 (去重存储，节省空间)
CREATE TABLE IF NOT EXISTS evo_system_prompts (
    prompt_hash TEXT PRIMARY KEY,           -- SHA256 hash
    prompt_content TEXT NOT NULL,           -- 完整内容
    prompt_tokens INTEGER,                  -- Token 数量
    first_seen_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_used_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    usage_count INTEGER DEFAULT 1
);

-- ==================== 3. 工具调用详情 (Tool Call Details) ====================

CREATE TABLE IF NOT EXISTS evo_tool_calls (
    call_id TEXT PRIMARY KEY,
    span_id TEXT NOT NULL REFERENCES evo_spans(span_id) ON DELETE CASCADE,
    trace_id TEXT NOT NULL,

    -- 工具信息
    tool_name TEXT NOT NULL,                -- Read, Write, Edit, Bash, etc.
    tool_provider TEXT,                     -- builtin, mcp, custom

    -- 输入输出
    input_params JSON,                      -- 输入参数
    output_result JSON,                     -- 输出结果 (truncated)
    output_size_bytes INTEGER,              -- 输出大小

    -- 执行信息
    latency_ms INTEGER,
    status TEXT CHECK(status IN ('success', 'failed', 'timeout', 'permission_denied')),
    error_message TEXT,

    -- 元数据
    file_path TEXT,                         -- 涉及的文件路径 (如适用)
    file_type TEXT,                         -- 文件类型
    line_count INTEGER,                     -- 行数 (如适用)

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ==================== 4. Agent 记忆系统 (Agent Memory System) ====================
-- 基于 AWS AgentCore Memory 和学术研究的三层记忆模型

-- 语义记忆 (Semantic Memory) - "What" - 事实和知识
CREATE TABLE IF NOT EXISTS evo_memory_semantic (
    memory_id TEXT PRIMARY KEY,
    namespace TEXT NOT NULL,                -- 命名空间: "project/thunderduck", "user/preferences"

    -- 内容
    key TEXT NOT NULL,                      -- 知识键
    value JSON NOT NULL,                    -- 知识值
    embedding BLOB,                         -- 向量嵌入 (用于相似性搜索)

    -- 元数据
    source_type TEXT,                       -- 来源类型: inferred, explicit, imported
    source_trace_id TEXT,                   -- 来源追踪 ID
    confidence REAL DEFAULT 1.0,            -- 置信度 (0-1)

    -- 生命周期
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_accessed_at DATETIME,
    access_count INTEGER DEFAULT 0,
    ttl_seconds INTEGER,                    -- 生存时间 (NULL = 永久)

    UNIQUE(namespace, key)
);

-- 情节记忆 (Episodic Memory) - "When/Where" - 过去的交互和经验
CREATE TABLE IF NOT EXISTS evo_memory_episodic (
    memory_id TEXT PRIMARY KEY,
    namespace TEXT NOT NULL,

    -- 事件信息
    event_type TEXT NOT NULL,               -- 事件类型: task_completed, error_resolved, pattern_learned
    event_summary TEXT NOT NULL,            -- 事件摘要
    event_details JSON,                     -- 详细信息

    -- 关联
    session_id TEXT,
    trace_id TEXT,
    related_files JSON,                     -- 相关文件
    related_resources JSON,                 -- 相关资源 (agents, skills, etc.)

    -- 情感/重要性
    importance REAL DEFAULT 0.5,            -- 重要性 (0-1)
    sentiment TEXT,                         -- 情感: positive, negative, neutral
    outcome TEXT,                           -- 结果: success, failure, partial

    -- 向量
    embedding BLOB,                         -- 用于相似性搜索

    -- 生命周期
    occurred_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_recalled_at DATETIME,
    recall_count INTEGER DEFAULT 0,
    decay_rate REAL DEFAULT 0.01            -- 遗忘率
);

-- 程序记忆 (Procedural Memory) - "How" - 如何执行任务
CREATE TABLE IF NOT EXISTS evo_memory_procedural (
    memory_id TEXT PRIMARY KEY,
    namespace TEXT NOT NULL,

    -- 过程信息
    procedure_name TEXT NOT NULL,           -- 过程名称
    procedure_type TEXT,                    -- 类型: workflow, pattern, rule
    description TEXT,

    -- 触发条件
    trigger_conditions JSON NOT NULL,       -- 触发条件
    trigger_keywords JSON,                  -- 触发关键词

    -- 执行步骤
    steps JSON NOT NULL,                    -- 执行步骤
    resources_needed JSON,                  -- 需要的资源

    -- 性能统计
    execution_count INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    avg_duration_seconds REAL,
    last_executed_at DATETIME,

    -- 版本控制
    version INTEGER DEFAULT 1,
    previous_version_id TEXT,

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(namespace, procedure_name, version)
);

-- ==================== 5. 反馈循环 (Feedback Loop) ====================
-- 用于持续学习和优化

-- 反馈记录
CREATE TABLE IF NOT EXISTS evo_feedback (
    feedback_id TEXT PRIMARY KEY,

    -- 关联
    trace_id TEXT,
    span_id TEXT,
    session_id TEXT,
    resource_id TEXT,                       -- 相关资源

    -- 反馈类型
    feedback_type TEXT NOT NULL CHECK(feedback_type IN (
        'explicit_rating',      -- 用户明确评分
        'implicit_positive',    -- 隐式正反馈 (继续使用)
        'implicit_negative',    -- 隐式负反馈 (重试、取消)
        'correction',           -- 用户纠正
        'preference',           -- 偏好表达
        'bug_report',           -- 错误报告
        'feature_request'       -- 功能请求
    )),

    -- 反馈内容
    rating INTEGER,                         -- 1-5 评分 (如适用)
    comment TEXT,                           -- 评论
    original_response TEXT,                 -- 原始响应
    corrected_response TEXT,                -- 纠正后的响应

    -- 元数据
    context JSON,                           -- 反馈上下文

    -- 处理状态
    processed BOOLEAN DEFAULT FALSE,
    processed_at DATETIME,
    action_taken TEXT,                      -- 采取的行动

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 学习信号 (从反馈中提取的可操作信号)
CREATE TABLE IF NOT EXISTS evo_learning_signals (
    signal_id TEXT PRIMARY KEY,

    -- 关联追踪
    trace_id TEXT,                          -- 来源追踪
    span_id TEXT,                           -- 来源 Span

    -- 信号类型
    signal_type TEXT NOT NULL CHECK(signal_type IN (
        'prompt_improvement',       -- 提示改进
        'model_preference',         -- 模型偏好
        'routing_adjustment',       -- 路由调整
        'cost_optimization',        -- 成本优化
        'latency_improvement',      -- 延迟改进
        'quality_issue',            -- 质量问题
        'new_capability_needed'     -- 需要新能力
    )),

    -- 信号内容
    signal_strength REAL NOT NULL,          -- 信号强度 (0-1)
    source TEXT,                            -- 信号来源: user_feedback, auto_detect, peer_review
    context JSON,                           -- 上下文信息
    evidence JSON DEFAULT '[]',             -- 证据 (来源 feedback IDs)
    recommendation JSON,                    -- 推荐行动
    actionable BOOLEAN DEFAULT TRUE,        -- 是否可操作

    -- 影响范围
    affected_resources JSON,                -- 受影响的资源

    -- 状态
    status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'reviewed', 'applied', 'rejected')),
    applied_at DATETIME,

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ==================== 6. A/B 测试与实验 (Experiments) ====================

CREATE TABLE IF NOT EXISTS evo_experiments (
    experiment_id TEXT PRIMARY KEY,
    experiment_name TEXT NOT NULL,
    description TEXT,

    -- 实验配置
    hypothesis TEXT,                        -- 假设
    experiment_type TEXT CHECK(experiment_type IN ('a_b', 'multi_arm', 'contextual_bandit')),

    -- 变体
    variants JSON NOT NULL,                 -- [{"name": "control", "config": {...}}, {"name": "treatment", "config": {...}}]
    traffic_allocation JSON,                -- 流量分配

    -- 目标指标
    primary_metric TEXT NOT NULL,           -- 主要指标
    secondary_metrics JSON,                 -- 次要指标
    guardrail_metrics JSON,                 -- 护栏指标 (不能恶化)

    -- 时间范围
    started_at DATETIME,
    ended_at DATETIME,
    min_sample_size INTEGER,                -- 最小样本量

    -- 状态
    status TEXT DEFAULT 'draft' CHECK(status IN ('draft', 'running', 'paused', 'completed', 'cancelled')),

    -- 结果
    winner_variant TEXT,
    result_summary JSON,
    statistical_significance REAL,

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 实验分配记录
CREATE TABLE IF NOT EXISTS evo_experiment_assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_id TEXT NOT NULL REFERENCES evo_experiments(experiment_id) ON DELETE CASCADE,
    session_id TEXT,
    trace_id TEXT,

    variant_name TEXT NOT NULL,
    assigned_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    -- 结果
    outcome_value REAL,
    outcome_recorded_at DATETIME
);

-- ==================== 7. 性能基线与异常检测 (Baselines & Anomalies) ====================

-- 性能基线
CREATE TABLE IF NOT EXISTS evo_baselines (
    baseline_id TEXT PRIMARY KEY,
    resource_id TEXT NOT NULL,
    metric_name TEXT NOT NULL,              -- latency, cost, success_rate, etc.

    -- 基线值
    baseline_value REAL NOT NULL,
    baseline_stddev REAL,

    -- 统计窗口
    window_type TEXT CHECK(window_type IN ('rolling_7d', 'rolling_30d', 'fixed_period')),
    sample_count INTEGER,

    -- 阈值
    warning_threshold REAL,                 -- 警告阈值 (相对于基线的偏差)
    critical_threshold REAL,                -- 严重阈值

    -- 状态
    is_active BOOLEAN DEFAULT TRUE,         -- 是否启用

    last_updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(resource_id, metric_name)
);

-- 异常记录
CREATE TABLE IF NOT EXISTS evo_anomalies (
    anomaly_id TEXT PRIMARY KEY,
    baseline_id TEXT REFERENCES evo_baselines(baseline_id),
    resource_id TEXT,                       -- 资源 ID
    metric_name TEXT,                       -- 指标名称

    -- 异常信息
    anomaly_type TEXT CHECK(anomaly_type IN ('spike', 'drop', 'drift', 'pattern_change')),
    severity TEXT CHECK(severity IN ('info', 'warning', 'critical')),

    -- 数值
    expected_value REAL,
    actual_value REAL,
    observed_value REAL,
    deviation_percent REAL,

    -- 上下文
    context JSON,
    possible_causes JSON,

    -- 状态
    detected_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    acknowledged BOOLEAN DEFAULT FALSE,
    acknowledged_at DATETIME,
    resolved BOOLEAN DEFAULT FALSE,
    resolved_at DATETIME,
    resolution_notes TEXT,

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ==================== 8. 优化建议 (Optimization Recommendations) ====================

CREATE TABLE IF NOT EXISTS evo_recommendations (
    recommendation_id TEXT PRIMARY KEY,

    -- 推荐类型
    recommendation_type TEXT NOT NULL CHECK(recommendation_type IN (
        'model_switch',             -- 模型切换
        'prompt_optimization',      -- 提示优化
        'caching_opportunity',      -- 缓存机会
        'batching_opportunity',     -- 批处理机会
        'cost_reduction',           -- 成本降低
        'latency_improvement',      -- 延迟改进
        'quality_improvement',      -- 质量改进
        'resource_retirement',      -- 资源废弃
        'routing_change'            -- 路由变更
    )),

    -- 资源关联
    resource_id TEXT,                       -- 关联资源 ID
    current_state JSON,                     -- 当前状态
    recommended_state JSON,                 -- 推荐状态

    -- 推荐内容
    title TEXT,                             -- 标题 (可选，触发器可能不提供)
    description TEXT,                       -- 描述 (可选)
    rationale TEXT,                         -- 理由

    -- 影响评估
    affected_resources JSON,
    estimated_impact JSON,                  -- {"cost_saving": 0.15, "latency_reduction": 0.1}
    confidence REAL,                        -- 置信度

    -- 证据
    evidence JSON NOT NULL,                 -- 支持证据
    data_window TEXT,                       -- 数据窗口: "2026-01-23 to 2026-01-30"

    -- 行动
    recommended_action JSON,                -- 具体行动步骤
    auto_applicable BOOLEAN DEFAULT FALSE,  -- 是否可自动应用

    -- 状态
    status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'reviewing', 'approved', 'applied', 'rejected', 'expired')),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    reviewed_at DATETIME,
    applied_at DATETIME,

    -- 结果追踪
    before_metrics JSON,
    after_metrics JSON,
    actual_impact JSON
);

-- ==================== 9. 日志聚合 (Log Aggregations) ====================
-- 用于快速查询的预聚合表

-- 每小时模型使用聚合
CREATE TABLE IF NOT EXISTS evo_hourly_model_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hour_bucket TEXT NOT NULL,              -- 小时时间戳 'YYYY-MM-DD HH:00:00'
    model_name TEXT NOT NULL,
    model_alias TEXT NOT NULL,
    provider TEXT,                          -- 提供商 (anthropic, openai, local)

    -- 计数
    call_count INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    error_count INTEGER DEFAULT 0,

    -- Token 统计
    total_input_tokens INTEGER DEFAULT 0,
    total_output_tokens INTEGER DEFAULT 0,
    total_cached_tokens INTEGER DEFAULT 0,
    avg_input_tokens REAL,
    avg_output_tokens REAL,

    -- 成本
    total_cost_usd REAL DEFAULT 0,
    avg_cost_per_call REAL,

    -- 延迟
    avg_latency_ms REAL,
    p50_latency_ms REAL,
    p95_latency_ms REAL,
    p99_latency_ms REAL,
    avg_ttft_ms REAL,                       -- 平均首 token 时间

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(hour_bucket, model_alias)
);

-- 每小时工具使用聚合
CREATE TABLE IF NOT EXISTS evo_hourly_tool_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hour_bucket TEXT NOT NULL,              -- 小时时间戳 'YYYY-MM-DD HH:00:00'
    tool_name TEXT NOT NULL,

    -- 计数
    call_count INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,

    -- 延迟
    avg_latency_ms REAL,
    p50_latency_ms REAL,
    p95_latency_ms REAL,

    -- 数据量
    total_input_chars INTEGER DEFAULT 0,
    total_output_chars INTEGER DEFAULT 0,

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(hour_bucket, tool_name)
);

-- 每日成本聚合
CREATE TABLE IF NOT EXISTS evo_daily_cost_summary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date_bucket DATE NOT NULL,              -- 日期 'YYYY-MM-DD'
    user_id TEXT NOT NULL DEFAULT 'default',
    project_id TEXT NOT NULL DEFAULT 'default',

    -- 按模型分解
    model_costs JSON,                       -- {"opus": 5.2, "sonnet": 2.1, "haiku": 0.3}

    -- 按资源分解
    resource_costs JSON,                    -- {"agent:coder": 3.1, "skill:review": 0.8}

    -- 会话统计
    session_count INTEGER DEFAULT 0,
    total_turns INTEGER DEFAULT 0,
    avg_cost_per_session REAL,
    max_session_cost REAL,
    avg_session_duration_sec REAL,

    -- 总计
    total_cost_usd REAL DEFAULT 0,
    total_input_tokens INTEGER DEFAULT 0,
    total_output_tokens INTEGER DEFAULT 0,
    total_cached_tokens INTEGER DEFAULT 0,
    cache_hit_rate REAL,                    -- 缓存命中率

    -- 与前日对比
    cost_change_percent REAL,

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(date_bucket, user_id, project_id)
);

-- ==================== 索引 ====================

-- Sessions
CREATE INDEX IF NOT EXISTS idx_evo_sessions_user ON evo_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_evo_sessions_project ON evo_sessions(project_id);
CREATE INDEX IF NOT EXISTS idx_evo_sessions_started ON evo_sessions(started_at);
CREATE INDEX IF NOT EXISTS idx_evo_sessions_mode ON evo_sessions(mode);

-- Traces
CREATE INDEX IF NOT EXISTS idx_evo_traces_session ON evo_traces(session_id);
CREATE INDEX IF NOT EXISTS idx_evo_traces_started ON evo_traces(started_at);
CREATE INDEX IF NOT EXISTS idx_evo_traces_status ON evo_traces(status);
CREATE INDEX IF NOT EXISTS idx_evo_traces_entry ON evo_traces(entry_point);

-- Spans
CREATE INDEX IF NOT EXISTS idx_evo_spans_trace ON evo_spans(trace_id);
CREATE INDEX IF NOT EXISTS idx_evo_spans_type ON evo_spans(span_type);
CREATE INDEX IF NOT EXISTS idx_evo_spans_name ON evo_spans(span_name);

-- LLM Calls
CREATE INDEX IF NOT EXISTS idx_evo_llm_trace ON evo_llm_calls(trace_id);
CREATE INDEX IF NOT EXISTS idx_evo_llm_session ON evo_llm_calls(session_id);
CREATE INDEX IF NOT EXISTS idx_evo_llm_model ON evo_llm_calls(model_name);
CREATE INDEX IF NOT EXISTS idx_evo_llm_provider ON evo_llm_calls(provider);
CREATE INDEX IF NOT EXISTS idx_evo_llm_created ON evo_llm_calls(created_at);

-- Tool Calls
CREATE INDEX IF NOT EXISTS idx_evo_tool_trace ON evo_tool_calls(trace_id);
CREATE INDEX IF NOT EXISTS idx_evo_tool_name ON evo_tool_calls(tool_name);

-- Memory
CREATE INDEX IF NOT EXISTS idx_evo_mem_semantic_ns ON evo_memory_semantic(namespace);
CREATE INDEX IF NOT EXISTS idx_evo_mem_episodic_ns ON evo_memory_episodic(namespace);
CREATE INDEX IF NOT EXISTS idx_evo_mem_episodic_type ON evo_memory_episodic(event_type);
CREATE INDEX IF NOT EXISTS idx_evo_mem_procedural_ns ON evo_memory_procedural(namespace);

-- Feedback
CREATE INDEX IF NOT EXISTS idx_evo_feedback_trace ON evo_feedback(trace_id);
CREATE INDEX IF NOT EXISTS idx_evo_feedback_type ON evo_feedback(feedback_type);
CREATE INDEX IF NOT EXISTS idx_evo_feedback_processed ON evo_feedback(processed);

-- Learning Signals
CREATE INDEX IF NOT EXISTS idx_evo_signal_type ON evo_learning_signals(signal_type);
CREATE INDEX IF NOT EXISTS idx_evo_signal_status ON evo_learning_signals(status);

-- Experiments
CREATE INDEX IF NOT EXISTS idx_evo_exp_status ON evo_experiments(status);

-- Baselines
CREATE INDEX IF NOT EXISTS idx_evo_baseline_resource ON evo_baselines(resource_id);

-- Anomalies
CREATE INDEX IF NOT EXISTS idx_evo_anomaly_severity ON evo_anomalies(severity);
CREATE INDEX IF NOT EXISTS idx_evo_anomaly_resolved ON evo_anomalies(resolved);

-- Recommendations
CREATE INDEX IF NOT EXISTS idx_evo_rec_type ON evo_recommendations(recommendation_type);
CREATE INDEX IF NOT EXISTS idx_evo_rec_status ON evo_recommendations(status);

-- Aggregations
CREATE INDEX IF NOT EXISTS idx_evo_hourly_model ON evo_hourly_model_usage(hour_bucket, model_alias);
CREATE INDEX IF NOT EXISTS idx_evo_hourly_tool ON evo_hourly_tool_usage(hour_bucket, tool_name);
CREATE INDEX IF NOT EXISTS idx_evo_daily_cost ON evo_daily_cost_summary(date_bucket);
CREATE INDEX IF NOT EXISTS idx_evo_daily_cost_user ON evo_daily_cost_summary(user_id, date_bucket);

-- 记录 schema 版本
INSERT OR IGNORE INTO sys_schema_migrations (version, description)
VALUES ('2.0.0-evolution', 'Self-evolution system: sessions, tracing, memory, feedback, experiments, baselines, recommendations');
