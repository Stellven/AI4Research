# Solar Persona Evaluation Model Design

> 基于 [PersonaGym](https://personagym.com/) + [Multi-LLM Evaluator Framework](https://www.emergentmind.com/topics/multi-llm-evaluator-framework) 研究

## 1. 核心架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    PERSONA EVALUATION SYSTEM (PES)                       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   Input: Task                                                           │
│       │                                                                 │
│       ▼                                                                 │
│   ┌───────────────────────────────────────────────────────────┐        │
│   │              Task Analyzer (任务分析器)                    │        │
│   │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌───────────┐    │        │
│   │  │ Domain  │  │Complexity│  │Cognitive│  │ Risk      │    │        │
│   │  │ Detect  │  │ Score   │  │ Require │  │ Tolerance │    │        │
│   │  └────┬────┘  └────┬────┘  └────┬────┘  └─────┬─────┘    │        │
│   │       └────────────┴────────────┴─────────────┘          │        │
│   │                          │                                │        │
│   │                          ▼                                │        │
│   │                   Task Profile                            │        │
│   └───────────────────────────────────────────────────────────┘        │
│                          │                                              │
│                          ▼                                              │
│   ┌───────────────────────────────────────────────────────────┐        │
│   │              Persona Matcher (人格匹配器)                  │        │
│   │                                                           │        │
│   │   Task Profile × Persona Profiles → Affinity Scores      │        │
│   │                                                           │        │
│   │   ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐       │        │
│   │   │scientist│ │engineer │ │ redteam │ │creative │ ...    │        │
│   │   │ 0.85    │ │ 0.72    │ │ 0.68    │ │ 0.45    │        │        │
│   │   └─────────┘ └─────────┘ └─────────┘ └─────────┘        │        │
│   │                          │                                │        │
│   │                          ▼                                │        │
│   │              Top-N Selection + Weight Normalization       │        │
│   └───────────────────────────────────────────────────────────┘        │
│                          │                                              │
│                          ▼                                              │
│   ┌───────────────────────────────────────────────────────────┐        │
│   │              Ensemble Composer (集成组合器)                │        │
│   │                                                           │        │
│   │   Selected: [scientist(0.52), engineer(0.32), redteam(0.16)]       │
│   │   Mode: weighted_ensemble | jekyll_hyde | primary_only    │        │
│   │                          │                                │        │
│   │                          ▼                                │        │
│   │              Composed System Prompt                       │        │
│   └───────────────────────────────────────────────────────────┘        │
│                          │                                              │
│                          ▼                                              │
│                       Execution                                         │
│                          │                                              │
│                          ▼                                              │
│   ┌───────────────────────────────────────────────────────────┐        │
│   │              Performance Tracker (性能追踪器)              │        │
│   │                                                           │        │
│   │   Metrics:                                                │        │
│   │   • Task Success Rate                                     │        │
│   │   • Response Quality Score                                │        │
│   │   • Persona Consistency Score                             │        │
│   │   • User Feedback (if available)                          │        │
│   │                          │                                │        │
│   │                          ▼                                │        │
│   │              Bayesian Weight Update                       │        │
│   └───────────────────────────────────────────────────────────┘        │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## 2. Task Profile 定义

基于任务特征的多维向量：

```typescript
interface TaskProfile {
  // 领域分类 (来自 routing rules)
  domain: 'code' | 'security' | 'research' | 'creative' | 'product' | 'debug' | 'testing' | 'complex';
  domain_confidence: number;  // 0-1

  // 复杂度评分 (1-10)
  complexity: number;
  complexity_factors: {
    multi_step: boolean;
    requires_context: boolean;
    ambiguity_level: number;  // 0-1
    domain_expertise_required: number;  // 0-1
  };

  // 认知需求
  cognitive_requirements: CognitiveFunction[];

  // 监管焦点倾向
  regulatory_lean: 'promotion' | 'prevention' | 'balanced';

  // 风险容忍度
  risk_tolerance: 'high' | 'medium' | 'low';

  // 创新 vs 准确 权衡
  innovation_accuracy_tradeoff: number;  // -1 (accuracy) to +1 (innovation)
}
```

## 3. Persona Affinity Score 计算

### 3.1 Big Five 匹配度

```typescript
function computeBigFiveAffinity(task: TaskProfile, persona: PersonaProfile): number {
  const weights = {
    openness: task.innovation_accuracy_tradeoff > 0 ? 0.3 : 0.1,
    conscientiousness: task.risk_tolerance === 'low' ? 0.35 : 0.2,
    extraversion: 0.1,  // 较少影响
    agreeableness: 0.1,
    neuroticism: task.complexity > 7 ? 0.15 : 0.1,  // 高复杂度需要低神经质
  };

  // 计算加权距离
  let score = 0;
  if (task.innovation_accuracy_tradeoff > 0) {
    // 需要创新 → 高 Openness 加分
    score += weights.openness * persona.big_five.openness;
  } else {
    // 需要准确 → 高 Conscientiousness 加分
    score += weights.conscientiousness * persona.big_five.conscientiousness;
  }

  // 低风险容忍 → 低 Neuroticism 加分 (反向)
  if (task.risk_tolerance === 'low') {
    score += weights.neuroticism * (1 - persona.big_five.neuroticism);
  }

  return score;
}
```

### 3.2 领域匹配度

```typescript
function computeDomainAffinity(task: TaskProfile, persona: PersonaProfile): number {
  const domainPersonaMap: Record<string, string[]> = {
    'code': ['engineer', 'scientist'],
    'security': ['redteam', 'reviewer'],
    'research': ['scientist', 'creative'],
    'creative': ['creative', 'pm'],
    'product': ['pm', 'engineer'],
    'debug': ['engineer', 'scientist'],
    'testing': ['reviewer', 'engineer'],
    'complex': ['scientist', 'reviewer'],
  };

  const preferredPersonas = domainPersonaMap[task.domain] || [];
  const rank = preferredPersonas.indexOf(persona.id);

  if (rank === 0) return 1.0;
  if (rank === 1) return 0.7;
  if (rank >= 0) return 0.4;
  return 0.2;  // 不在列表中
}
```

### 3.3 认知函数匹配度

```typescript
function computeCognitiveAffinity(task: TaskProfile, persona: PersonaProfile): number {
  const required = new Set(task.cognitive_requirements);
  const provided = new Set(persona.cognitive_forcing);

  const intersection = [...required].filter(x => provided.has(x));
  const coverage = intersection.length / required.size;

  return coverage;  // 0-1
}
```

### 3.4 综合 Affinity Score

```typescript
function computeAffinityScore(task: TaskProfile, persona: PersonaProfile): number {
  const bigFiveScore = computeBigFiveAffinity(task, persona);      // 0-1
  const domainScore = computeDomainAffinity(task, persona);        // 0-1
  const cognitiveScore = computeCognitiveAffinity(task, persona);  // 0-1

  // 动态权重 based on task characteristics
  const weights = {
    bigFive: 0.3,
    domain: 0.4,
    cognitive: 0.3,
  };

  return (
    weights.bigFive * bigFiveScore +
    weights.domain * domainScore +
    weights.cognitive * cognitiveScore
  );
}
```

## 4. Top-N Selection with Weights

```typescript
interface PersonaSelection {
  persona_id: string;
  affinity_score: number;
  normalized_weight: number;  // Sum to 1.0
  role: 'primary' | 'secondary' | 'validator';
}

function selectTopN(
  task: TaskProfile,
  personas: PersonaProfile[],
  n: number = 3
): PersonaSelection[] {
  // 计算所有人格的 affinity scores
  const scored = personas.map(p => ({
    persona_id: p.id,
    affinity_score: computeAffinityScore(task, p),
  }));

  // 排序选取 Top-N
  scored.sort((a, b) => b.affinity_score - a.affinity_score);
  const topN = scored.slice(0, n);

  // Softmax 归一化权重
  const temperature = 1.0;  // 可调节，越低越集中
  const expScores = topN.map(s => Math.exp(s.affinity_score / temperature));
  const sumExp = expScores.reduce((a, b) => a + b, 0);

  return topN.map((s, i) => ({
    persona_id: s.persona_id,
    affinity_score: s.affinity_score,
    normalized_weight: expScores[i] / sumExp,
    role: i === 0 ? 'primary' : (i === topN.length - 1 && n >= 2) ? 'validator' : 'secondary',
  }));
}
```

## 5. 性能追踪 Schema

```sql
-- 人格执行记录
CREATE TABLE persona_executions (
  execution_id TEXT PRIMARY KEY,
  task_id TEXT,
  task_profile TEXT,        -- JSON: TaskProfile

  -- 选择的人格组合
  selected_personas TEXT,   -- JSON: PersonaSelection[]
  ensemble_mode TEXT,       -- 'weighted', 'jekyll_hyde', 'primary_only'

  -- 执行结果
  status TEXT,              -- 'success', 'partial', 'failed'
  duration_ms INTEGER,

  -- 质量指标
  task_success_score REAL,      -- 0-1: 任务完成度
  response_quality_score REAL,  -- 0-1: LLM评估的质量
  persona_consistency_score REAL, -- 0-1: 是否保持人格一致性

  -- 用户反馈 (如果有)
  user_feedback TEXT,       -- 'positive', 'negative', 'neutral', NULL
  user_feedback_detail TEXT,

  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 人格性能统计 (聚合视图)
CREATE VIEW v_persona_performance AS
SELECT
  json_each.value ->> '$.persona_id' as persona_id,
  COUNT(*) as total_executions,
  AVG(task_success_score) as avg_success_score,
  AVG(response_quality_score) as avg_quality_score,
  AVG(persona_consistency_score) as avg_consistency_score,
  SUM(CASE WHEN user_feedback = 'positive' THEN 1 ELSE 0 END) * 1.0 /
    NULLIF(SUM(CASE WHEN user_feedback IS NOT NULL THEN 1 ELSE 0 END), 0) as positive_feedback_ratio
FROM persona_executions, json_each(selected_personas)
GROUP BY json_each.value ->> '$.persona_id';

-- 领域-人格效果矩阵
CREATE VIEW v_persona_domain_effectiveness AS
SELECT
  json_extract(task_profile, '$.domain') as domain,
  json_each.value ->> '$.persona_id' as persona_id,
  AVG(task_success_score) as effectiveness,
  COUNT(*) as sample_count
FROM persona_executions, json_each(selected_personas)
GROUP BY domain, persona_id
HAVING sample_count >= 5;  -- 至少5次执行才有统计意义
```

## 6. 权重动态调整 (Bayesian Update)

```typescript
interface PersonaPrior {
  persona_id: string;
  domain: string;
  alpha: number;  // Beta 分布参数
  beta: number;
}

function updatePersonaWeight(
  prior: PersonaPrior,
  success: boolean
): PersonaPrior {
  // Beta-Bernoulli 共轭先验更新
  return {
    ...prior,
    alpha: success ? prior.alpha + 1 : prior.alpha,
    beta: success ? prior.beta : prior.beta + 1,
  };
}

function getExpectedWeight(prior: PersonaPrior): number {
  // Beta 分布的期望值
  return prior.alpha / (prior.alpha + prior.beta);
}

function getConfidenceInterval(prior: PersonaPrior): [number, number] {
  // Wilson score interval for 95% confidence
  const n = prior.alpha + prior.beta - 2;  // 样本数
  const p = getExpectedWeight(prior);
  const z = 1.96;  // 95% CI

  if (n < 5) return [0, 1];  // 样本太少，返回最大区间

  const denominator = 1 + z * z / n;
  const center = (p + z * z / (2 * n)) / denominator;
  const margin = z * Math.sqrt((p * (1 - p) + z * z / (4 * n)) / n) / denominator;

  return [Math.max(0, center - margin), Math.min(1, center + margin)];
}
```

## 7. 评估指标体系 (参考 PersonaGym)

| 指标 | 定义 | 计算方式 | 权重 |
|------|------|----------|------|
| **Task Success** | 任务完成度 | 二元/连续评分 | 0.35 |
| **Response Quality** | 输出质量 | LLM 评估 (1-5) | 0.25 |
| **Persona Consistency** | 人格一致性 | 风格/语气匹配度 | 0.20 |
| **Cognitive Alignment** | 认知函数执行 | 是否使用了期望的认知策略 | 0.15 |
| **User Satisfaction** | 用户满意度 | 显式反馈 | 0.05 |

### 综合 PersonaScore

```
PersonaScore = Σ(weight_i × metric_i)
            = 0.35×TaskSuccess + 0.25×Quality + 0.20×Consistency
              + 0.15×CognitiveAlign + 0.05×UserSat
```

## 8. 实现路线图

### Phase 1: 基础追踪 (1 周)
- [ ] 创建 `persona_executions` 表
- [ ] 在 PersonaEngine 中集成执行记录
- [ ] 实现基础 Task Analyzer

### Phase 2: Affinity 计算 (1 周)
- [ ] 实现 Big Five 匹配算法
- [ ] 实现领域匹配算法
- [ ] 实现 Top-N 选择 + Softmax 权重

### Phase 3: 性能评估 (2 周)
- [ ] 集成 LLM 评估器 (Response Quality)
- [ ] 实现 Persona Consistency 检测
- [ ] 实现 Bayesian 权重更新

### Phase 4: 闭环优化 (持续)
- [ ] 收集足够执行数据 (>100 次/人格)
- [ ] 分析 Domain-Persona 效果矩阵
- [ ] 调整 Affinity 计算权重

---

## 参考文献

1. [PersonaGym: Evaluating Persona Agents and LLMs](https://personagym.com/) - EMNLP 2025
2. [Multi-LLM Evaluator Framework](https://www.emergentmind.com/topics/multi-llm-evaluator-framework)
3. [Evaluation and Benchmarking of LLM Agents: A Survey](https://arxiv.org/html/2507.21504v1) - KDD 2025
