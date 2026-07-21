# Solar 自我评估系统设计

> **Self-Evaluation System (SES)**
> **目标**: 持续追踪、评估、优化 Solar 的各项能力
> **设计日期**: 2026-02-05

## 一、系统概览

```
┌─────────────────────────────────────────────────────────────────┐
│                 SOLAR SELF-EVALUATION SYSTEM                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    DATA COLLECTION                       │   │
│  │  Hooks → Tool Calls, Errors, Learning, Tasks, Sessions  │   │
│  └───────────────────────────┬─────────────────────────────┘   │
│                              │                                  │
│                              ▼                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    EVALUATION ENGINE                     │   │
│  │                                                         │   │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐       │   │
│  │  │ Skill   │ │ Task    │ │ Learn   │ │ Error   │       │   │
│  │  │ Eval    │ │ Eval    │ │ Eval    │ │ Eval    │       │   │
│  │  └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘       │   │
│  │       └───────────┴───────────┴───────────┘             │   │
│  │                       │                                 │   │
│  │              ┌────────┴────────┐                        │   │
│  │              │ Synthesis Engine │                        │   │
│  │              └────────┬────────┘                        │   │
│  └───────────────────────┼─────────────────────────────────┘   │
│                          │                                      │
│                          ▼                                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    OUTPUT LAYER                          │   │
│  │  Reports │ Recommendations │ Alerts │ Trends │ Actions  │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## 二、评估维度

### 2.1 七维评估模型

| 维度 | 代号 | 描述 | 数据来源 |
|------|------|------|----------|
| **技能熟练度** | SKILL | 各技能的使用频率、成功率、效率 | evo_tool_calls, sys_skills |
| **任务执行** | TASK | 任务完成率、质量、耗时 | evo_sessions, todos |
| **学习效率** | LEARN | 学习信号提取、规则固化、知识转化 | evo_learning_signals, evo_memory_* |
| **错误模式** | ERROR | 错误类型、频率、重复率、恢复时间 | evo_tool_calls (status=error) |
| **规则遵从** | RULE | 铁律执行率、违规事件 | hooks 检查记录 |
| **资源效率** | RESOURCE | Token 使用、时间效率、成本 | sys_token_usage |
| **记忆利用** | MEMORY | 记忆检索命中率、采纳率、影响度 | evo_memory_influences |

### 2.2 Dreyfus 技能熟练度模型

```
┌─────────────────────────────────────────────────────────────────┐
│                    DREYFUS SKILL MODEL                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Level 5: Expert (专家)                                         │
│  ────────────────────────────────────────────────────────────   │
│  • 直觉决策，无需分析                                           │
│  • 成功率 >95%, 效率最优                                        │
│  • 能处理异常情况                                               │
│                                                                 │
│  Level 4: Proficient (精通)                                     │
│  ────────────────────────────────────────────────────────────   │
│  • 整体理解，快速定位                                           │
│  • 成功率 >90%, 效率高                                          │
│  • 能预见问题                                                   │
│                                                                 │
│  Level 3: Competent (胜任)                                      │
│  ────────────────────────────────────────────────────────────   │
│  • 有计划地执行                                                 │
│  • 成功率 >80%, 效率中等                                        │
│  • 能处理常见情况                                               │
│                                                                 │
│  Level 2: Advanced Beginner (进阶新手)                          │
│  ────────────────────────────────────────────────────────────   │
│  • 能识别情境                                                   │
│  • 成功率 >60%, 效率较低                                        │
│  • 需要指导                                                     │
│                                                                 │
│  Level 1: Novice (新手)                                         │
│  ────────────────────────────────────────────────────────────   │
│  • 依赖规则                                                     │
│  • 成功率 <60%, 效率低                                          │
│  • 常见错误                                                     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## 三、数据模型

### 3.1 评估记录表

```sql
-- 评估运行记录
CREATE TABLE IF NOT EXISTS ses_evaluation_runs (
    run_id TEXT PRIMARY KEY,
    run_type TEXT NOT NULL,           -- 'daily', 'weekly', 'monthly', 'on_demand'
    started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME,
    status TEXT DEFAULT 'running',    -- 'running', 'completed', 'failed'
    summary TEXT,                      -- JSON 摘要
    overall_score REAL,               -- 综合得分 0-100
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 维度评估结果
CREATE TABLE IF NOT EXISTS ses_dimension_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    dimension TEXT NOT NULL,          -- 'SKILL', 'TASK', 'LEARN', etc.
    score REAL NOT NULL,              -- 0-100
    previous_score REAL,              -- 上次得分
    trend TEXT,                       -- 'up', 'down', 'stable'
    details TEXT,                     -- JSON 详情
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (run_id) REFERENCES ses_evaluation_runs(run_id)
);

-- 技能熟练度追踪
CREATE TABLE IF NOT EXISTS ses_skill_proficiency (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_name TEXT NOT NULL,
    tool_name TEXT,                   -- 关联的工具
    usage_count INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    failure_count INTEGER DEFAULT 0,
    avg_duration_ms INTEGER,
    dreyfus_level INTEGER DEFAULT 1,  -- 1-5
    level_evidence TEXT,              -- 评级依据
    last_used_at DATETIME,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(skill_name)
);

-- 改进建议
CREATE TABLE IF NOT EXISTS ses_recommendations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    dimension TEXT NOT NULL,
    priority TEXT NOT NULL,           -- 'P1', 'P2', 'P3'
    category TEXT,                    -- 'improve', 'fix', 'learn', 'optimize'
    title TEXT NOT NULL,
    description TEXT,
    action_items TEXT,                -- JSON 行动项
    status TEXT DEFAULT 'pending',    -- 'pending', 'in_progress', 'done', 'dismissed'
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (run_id) REFERENCES ses_evaluation_runs(run_id)
);

-- 评估历史趋势
CREATE TABLE IF NOT EXISTS ses_trend_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL,
    dimension TEXT NOT NULL,
    score REAL NOT NULL,
    metadata TEXT,                    -- JSON 元数据
    UNIQUE(date, dimension)
);

-- 错误模式记录
CREATE TABLE IF NOT EXISTS ses_error_patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern_id TEXT NOT NULL UNIQUE,
    error_type TEXT NOT NULL,         -- 'tool_failure', 'logic_error', 'rule_violation', etc.
    description TEXT,
    occurrence_count INTEGER DEFAULT 1,
    first_seen_at DATETIME,
    last_seen_at DATETIME,
    resolution TEXT,                  -- 如何解决
    status TEXT DEFAULT 'active',     -- 'active', 'resolved', 'recurring'
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### 3.2 视图

```sql
-- 技能熟练度概览
CREATE VIEW IF NOT EXISTS v_skill_proficiency_overview AS
SELECT
    skill_name,
    tool_name,
    usage_count,
    ROUND(success_count * 100.0 / NULLIF(usage_count, 0), 1) as success_rate,
    dreyfus_level,
    CASE dreyfus_level
        WHEN 1 THEN 'Novice'
        WHEN 2 THEN 'Advanced Beginner'
        WHEN 3 THEN 'Competent'
        WHEN 4 THEN 'Proficient'
        WHEN 5 THEN 'Expert'
    END as level_name,
    last_used_at,
    updated_at
FROM ses_skill_proficiency
ORDER BY usage_count DESC;

-- 最新评估结果
CREATE VIEW IF NOT EXISTS v_latest_evaluation AS
SELECT
    r.run_id,
    r.run_type,
    r.overall_score,
    r.completed_at,
    d.dimension,
    d.score,
    d.trend
FROM ses_evaluation_runs r
JOIN ses_dimension_scores d ON r.run_id = d.run_id
WHERE r.run_id = (
    SELECT run_id FROM ses_evaluation_runs
    WHERE status = 'completed'
    ORDER BY completed_at DESC LIMIT 1
);

-- 活跃改进建议
CREATE VIEW IF NOT EXISTS v_active_recommendations AS
SELECT
    r.id,
    r.priority,
    r.dimension,
    r.category,
    r.title,
    r.description,
    r.action_items,
    r.created_at,
    e.overall_score as eval_score
FROM ses_recommendations r
JOIN ses_evaluation_runs e ON r.run_id = e.run_id
WHERE r.status IN ('pending', 'in_progress')
ORDER BY
    CASE r.priority WHEN 'P1' THEN 1 WHEN 'P2' THEN 2 ELSE 3 END,
    r.created_at DESC;
```

## 四、评估引擎

### 4.1 核心评估流程

```
┌─────────────────────────────────────────────────────────────────┐
│                    EVALUATION FLOW                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. Data Collection (数据收集)                                  │
│     └── 从各表收集指定时间范围的数据                            │
│                                                                 │
│  2. Dimension Evaluation (维度评估)                             │
│     ├── evaluateSkillProficiency()                              │
│     ├── evaluateTaskExecution()                                 │
│     ├── evaluateLearningEfficiency()                            │
│     ├── evaluateErrorPatterns()                                 │
│     ├── evaluateRuleCompliance()                                │
│     ├── evaluateResourceEfficiency()                            │
│     └── evaluateMemoryUtilization()                             │
│                                                                 │
│  3. Synthesis (综合)                                            │
│     └── 计算综合得分，生成趋势分析                              │
│                                                                 │
│  4. Recommendation Generation (建议生成)                        │
│     └── 基于评估结果生成改进建议                                │
│                                                                 │
│  5. Report Generation (报告生成)                                │
│     └── 生成可读的评估报告                                      │
│                                                                 │
│  6. Action Planning (行动规划)                                  │
│     └── 生成具体的行动项                                        │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 评估公式

**综合得分计算**:
```
Overall Score = Σ(Dimension Score × Weight)

Weights:
- SKILL:    0.20 (20%)
- TASK:     0.25 (25%)
- LEARN:    0.15 (15%)
- ERROR:    0.15 (15%)
- RULE:     0.10 (10%)
- RESOURCE: 0.10 (10%)
- MEMORY:   0.05 (5%)
```

**技能熟练度评分**:
```
Skill Score = (
    success_rate × 0.4 +
    frequency_score × 0.2 +
    efficiency_score × 0.2 +
    error_recovery × 0.2
) × 100
```

**Dreyfus 级别计算**:
```
Level 1: usage < 10 OR success_rate < 60%
Level 2: usage >= 10 AND success_rate >= 60%
Level 3: usage >= 50 AND success_rate >= 80%
Level 4: usage >= 100 AND success_rate >= 90% AND avg_duration < baseline
Level 5: usage >= 200 AND success_rate >= 95% AND handles_exceptions
```

## 五、定时任务

### 5.1 评估频率

| 类型 | 频率 | 时间 | 范围 | 深度 |
|------|------|------|------|------|
| Daily | 每天 | 04:00 | 24小时 | 快速 |
| Weekly | 每周日 | 03:00 | 7天 | 标准 |
| Monthly | 每月1日 | 02:00 | 30天 | 深度 |

### 5.2 Cron 配置

```bash
# Solar Self-Evaluation Schedule
# 每日评估 - 凌晨 4 点
0 4 * * * bun ~/.claude/core/ses/evaluate.ts daily >> ~/.solar/logs/ses-daily.log 2>&1

# 每周评估 - 周日凌晨 3 点
0 3 * * 0 bun ~/.claude/core/ses/evaluate.ts weekly >> ~/.solar/logs/ses-weekly.log 2>&1

# 每月评估 - 每月 1 日凌晨 2 点
0 2 1 * * bun ~/.claude/core/ses/evaluate.ts monthly >> ~/.solar/logs/ses-monthly.log 2>&1
```

## 六、报告格式

### 6.1 日报模板

```
┌─────────────────────────────────────────────────────────────────┐
│              SOLAR 自我评估日报 - YYYY-MM-DD                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  综合得分: XX/100 (趋势: ↑/↓/→)                                 │
│                                                                 │
├─ 维度得分 ───────────────────────────────────────────────────────┤
│                                                                 │
│  SKILL    ██████████████░░░░░░  70  (↑ +2)                      │
│  TASK     ████████████████░░░░  80  (→)                         │
│  LEARN    ████████████░░░░░░░░  60  (↓ -5)                      │
│  ERROR    ██████████████████░░  90  (↑ +3)                      │
│  RULE     ████████████████████  100 (→)                         │
│  RESOURCE ████████████████░░░░  80  (↑ +1)                      │
│  MEMORY   ████████░░░░░░░░░░░░  40  (↑ +10)                     │
│                                                                 │
├─ 关键发现 ───────────────────────────────────────────────────────┤
│                                                                 │
│  ✓ 正面: [具体发现]                                             │
│  ⚠ 警告: [需要注意的问题]                                       │
│  ❌ 问题: [需要解决的问题]                                       │
│                                                                 │
├─ 改进建议 ───────────────────────────────────────────────────────┤
│                                                                 │
│  P1: [高优先级建议]                                             │
│  P2: [中优先级建议]                                             │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 6.2 周报模板

包含:
- 7 天趋势图
- 技能熟练度变化
- 错误模式分析
- 学习成果汇总
- 下周目标

### 6.3 月报模板

包含:
- 30 天趋势图
- 能力成长曲线
- 里程碑达成
- 深度问题分析
- 长期优化建议

## 七、实现文件结构

```
~/.claude/core/ses/
├── evaluate.ts           # 主入口，CLI 接口
├── engine/
│   ├── evaluator.ts      # 评估引擎核心
│   ├── synthesizer.ts    # 综合分析
│   └── recommender.ts    # 建议生成
├── dimensions/
│   ├── skill-eval.ts     # 技能评估
│   ├── task-eval.ts      # 任务评估
│   ├── learn-eval.ts     # 学习评估
│   ├── error-eval.ts     # 错误评估
│   ├── rule-eval.ts      # 规则评估
│   ├── resource-eval.ts  # 资源评估
│   └── memory-eval.ts    # 记忆评估
├── reporters/
│   ├── daily-report.ts   # 日报生成
│   ├── weekly-report.ts  # 周报生成
│   └── monthly-report.ts # 月报生成
├── utils/
│   ├── db.ts             # 数据库操作
│   ├── metrics.ts        # 指标计算
│   └── trend.ts          # 趋势分析
├── schema.sql            # 数据表定义
└── types.ts              # 类型定义
```

---

*Solar Self-Evaluation System Design v1.0*
*设计日期: 2026-02-05*
