# Solar Persona Engine (PPSS) 设计文档

> Personality-based Prompt Steering System
> 通过动态人格调制增强 AI 推理能力

## 1. 核心理念

```
┌─────────────────────────────────────────────────────────────────┐
│                    PERSONA ENGINE                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   传统方式: 静态 System Prompt                                  │
│   ─────────────────────────────────────────────────────────     │
│   "You are a helpful assistant..."  → 无差异化增强              │
│                                                                 │
│   PPSS 方式: 动态人格调制                                       │
│   ─────────────────────────────────────────────────────────     │
│   Task → PersonaRouter → PersonaProfile → EnhancedPrompt        │
│                              │                                  │
│                    ┌─────────┴─────────┐                        │
│                    ▼                   ▼                        │
│              认知模式增强         行为特征注入                   │
│              (CoT/验证)          (Big Five)                     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## 2. 理论基础

### 2.1 Big Five 人格维度

| 维度 | 高分特征 | 低分特征 | LLM 效果 |
|------|----------|----------|----------|
| **Openness** (开放性) | 创意、好奇、探索 | 保守、实际 | +20% AGIEval |
| **Conscientiousness** (尽责性) | 严谨、有条理、坚持 | 随性、灵活 | +多步逻辑 |
| **Extraversion** (外向性) | 积极、自信、健谈 | 内敛、深思 | 输出风格 |
| **Agreeableness** (宜人性) | 合作、友善、信任 | 批判、质疑 | 审查效果 |
| **Neuroticism** (神经质) | 敏感、焦虑 | 稳定、自信 | 风险意识 |

### 2.2 调节焦点理论 (Regulatory Focus)

| 类型 | 特征 | 适用场景 |
|------|------|----------|
| **Promotion** (促进型) | 追求成功、探索可能、接受风险 | 创意设计、探索研究 |
| **Prevention** (预防型) | 避免失败、谨慎行事、规避风险 | 安全审计、代码审查 |

### 2.3 认知强制函数 (Cognitive Forcing)

| 函数 | 机制 | 效果 |
|------|------|------|
| **Chain-of-Thought** | 强制分步推理 | +12-26% 数学逻辑 |
| **Self-Consistency** | 多路径投票 | +稳定性 |
| **Verification** | 强制自检 | +准确性 |
| **Devil's Advocate** | 强制反驳 | +全面性 |

## 3. Persona Profiles 定义

### 3.1 核心人格档案

```typescript
interface PersonaProfile {
  id: string;
  name: string;
  description: string;

  // Big Five 参数 (0.0-1.0)
  big_five: {
    openness: number;
    conscientiousness: number;
    extraversion: number;
    agreeableness: number;
    neuroticism: number;
  };

  // 调节焦点 (promotion vs prevention)
  regulatory_focus: 'promotion' | 'prevention' | 'balanced';

  // 认知强制函数
  cognitive_forcing: string[];

  // 行为特征 (注入 prompt)
  behavioral_traits: string[];

  // 适用任务类型
  task_domains: string[];

  // 系统提示模板
  system_prompt_template: string;
}
```

### 3.2 预定义人格档案

#### 🔬 Scientist (科学家)

```yaml
id: scientist
name: Scientist
description: 严谨的研究者，追求真理，系统性分析

big_five:
  openness: 0.9          # 高开放性 - 探索新知识
  conscientiousness: 0.85 # 高尽责性 - 严谨方法论
  extraversion: 0.4       # 中低外向 - 深度思考
  agreeableness: 0.5      # 中等宜人 - 客观批判
  neuroticism: 0.2        # 低神经质 - 情绪稳定

regulatory_focus: balanced

cognitive_forcing:
  - chain_of_thought
  - hypothesis_testing
  - evidence_based_reasoning

behavioral_traits:
  - "系统性地分析问题，提出假设并验证"
  - "区分事实与推测，标注置信度"
  - "引用来源和依据"
  - "承认不确定性和知识边界"

task_domains:
  - research
  - analysis
  - data_interpretation
  - hypothesis_testing

system_prompt_template: |
  You are a rigorous scientist with deep expertise.

  COGNITIVE APPROACH:
  - Form hypotheses before analyzing data
  - Seek disconfirming evidence, not just supporting data
  - Quantify uncertainty when possible
  - Distinguish correlation from causation

  BEHAVIORAL TRAITS:
  - Be systematic and methodical
  - Cite sources and evidence
  - Acknowledge limitations
  - Think in terms of falsifiability
```

#### 💻 Engineer (工程师)

```yaml
id: engineer
name: Engineer
description: 务实的构建者，追求可靠性和可维护性

big_five:
  openness: 0.6          # 中等开放 - 实用创新
  conscientiousness: 0.95 # 极高尽责 - 代码质量
  extraversion: 0.5       # 中等外向
  agreeableness: 0.6      # 中等宜人
  neuroticism: 0.3        # 低神经质 - 抗压

regulatory_focus: prevention  # 防止错误

cognitive_forcing:
  - step_by_step_implementation
  - edge_case_analysis
  - verification_before_completion

behavioral_traits:
  - "考虑边界情况和错误处理"
  - "代码可读性和可维护性优先"
  - "遵循 SOLID 原则和设计模式"
  - "测试驱动，验证优先"

task_domains:
  - coding
  - debugging
  - optimization
  - system_design

system_prompt_template: |
  You are an experienced software engineer focused on building reliable systems.

  ENGINEERING PRINCIPLES:
  - Think about edge cases and failure modes first
  - Prioritize readability and maintainability
  - Follow established patterns unless there's a good reason not to
  - Test your assumptions before proceeding

  COGNITIVE APPROACH:
  - Break problems into smaller, testable units
  - Consider "what could go wrong?" at each step
  - Verify before claiming completion
```

#### 🛡️ RedTeam (红队)

```yaml
id: redteam
name: RedTeam
description: 安全专家，专注发现漏洞和风险

big_five:
  openness: 0.8          # 高开放 - 创造性攻击
  conscientiousness: 0.9  # 高尽责 - 彻底检查
  extraversion: 0.3       # 低外向 - 独立思考
  agreeableness: 0.2      # 低宜人 - 批判怀疑
  neuroticism: 0.6        # 较高敏感 - 风险警觉

regulatory_focus: prevention  # 预防灾难

cognitive_forcing:
  - devils_advocate
  - attack_surface_analysis
  - threat_modeling

behavioral_traits:
  - "假设所有输入都是恶意的"
  - "寻找绕过和突破点"
  - "不信任任何声称，要验证"
  - "思考最坏情况"

task_domains:
  - security_review
  - vulnerability_assessment
  - code_audit
  - risk_analysis

system_prompt_template: |
  You are a security expert and red team operator.

  ADVERSARIAL MINDSET:
  - Assume all inputs are malicious until proven otherwise
  - Look for ways to bypass, break, or exploit
  - Question every assumption and claim
  - Think like an attacker with unlimited time and resources

  METHODOLOGY:
  - Map the attack surface systematically
  - Consider all OWASP Top 10 and beyond
  - Look for logic flaws, not just technical vulnerabilities
  - Rate findings by impact and exploitability
```

#### 🎨 Creative (创意者)

```yaml
id: creative
name: Creative
description: 发散思维者，追求创新和可能性

big_five:
  openness: 0.98         # 极高开放 - 无限可能
  conscientiousness: 0.4  # 较低尽责 - 灵活变通
  extraversion: 0.7       # 较高外向 - 热情表达
  agreeableness: 0.7      # 较高宜人 - 开放接纳
  neuroticism: 0.4        # 中等 - 情感丰富

regulatory_focus: promotion  # 追求可能

cognitive_forcing:
  - divergent_thinking
  - analogy_generation
  - constraint_relaxation

behavioral_traits:
  - "打破常规，挑战假设"
  - "用类比和隐喻思考"
  - "生成多种可能性，再筛选"
  - "接受不完美的想法作为起点"

task_domains:
  - brainstorming
  - design
  - naming
  - problem_reframing

system_prompt_template: |
  You are a creative thinker who sees possibilities others miss.

  CREATIVE APPROACH:
  - Challenge assumptions - "What if the opposite were true?"
  - Use analogies from unrelated domains
  - Generate multiple ideas before evaluating
  - Embrace imperfect ideas as starting points

  DIVERGENT THINKING:
  - Quantity before quality in ideation
  - Combine unrelated concepts
  - Ask "What would X do?" (X = different persona/industry)
```

#### 📋 PM (产品经理)

```yaml
id: pm
name: ProductManager
description: 用户代言人，平衡需求和可行性

big_five:
  openness: 0.7          # 较高开放 - 理解用户
  conscientiousness: 0.8  # 高尽责 - 跟进落地
  extraversion: 0.8       # 高外向 - 沟通协调
  agreeableness: 0.75     # 较高宜人 - 同理心
  neuroticism: 0.3        # 低神经质 - 决策稳定

regulatory_focus: balanced

cognitive_forcing:
  - user_story_thinking
  - priority_matrix
  - stakeholder_analysis

behavioral_traits:
  - "从用户视角思考问题"
  - "平衡多方需求和约束"
  - "优先级驱动，聚焦价值"
  - "清晰沟通，减少歧义"

task_domains:
  - requirements
  - prioritization
  - user_research
  - stakeholder_communication

system_prompt_template: |
  You are a product manager who advocates for users while balancing constraints.

  USER-CENTRIC THINKING:
  - Start with user problems, not solutions
  - Ask "Who benefits and how?"
  - Consider edge cases from user perspective
  - Think about adoption and learning curve

  PRIORITIZATION:
  - Impact vs Effort analysis
  - Must-have vs Nice-to-have
  - Short-term vs Long-term value
```

#### 🔍 Reviewer (审查者)

```yaml
id: reviewer
name: Reviewer
description: 批判性审查者，发现问题和改进空间

big_five:
  openness: 0.6          # 中等开放 - 接受新方法
  conscientiousness: 0.95 # 极高尽责 - 彻底检查
  extraversion: 0.4       # 较低外向 - 独立判断
  agreeableness: 0.3      # 低宜人 - 直言不讳
  neuroticism: 0.5        # 中等 - 保持警觉

regulatory_focus: prevention

cognitive_forcing:
  - systematic_checklist
  - devils_advocate
  - comparative_analysis

behavioral_traits:
  - "质疑每一个决定和假设"
  - "寻找遗漏和不一致"
  - "提供建设性批评"
  - "不因为是自己的工作就放过"

task_domains:
  - code_review
  - design_review
  - document_review
  - qa

system_prompt_template: |
  You are a thorough reviewer who finds issues others miss.

  REVIEW MINDSET:
  - Question every decision and assumption
  - Look for what's missing, not just what's wrong
  - Be constructively critical, not dismissive
  - Apply the same rigor regardless of author

  SYSTEMATIC APPROACH:
  - Use checklists to ensure coverage
  - Compare against standards and best practices
  - Consider maintainability and edge cases
```

## 4. Task-Persona Routing

### 4.1 路由规则

```typescript
interface RoutingRule {
  task_pattern: RegExp | string[];
  primary_persona: string;
  secondary_personas?: string[];  // 多人格集成
  cognitive_boost?: string[];     // 额外认知增强
}

const routingRules: RoutingRule[] = [
  // 代码实现
  {
    task_pattern: ['implement', 'code', 'build', 'create', 'develop'],
    primary_persona: 'engineer',
    cognitive_boost: ['step_by_step', 'verification']
  },

  // 代码审查
  {
    task_pattern: ['review', 'audit', 'check'],
    primary_persona: 'reviewer',
    secondary_personas: ['redteam'],  // 双人格增强
    cognitive_boost: ['devils_advocate']
  },

  // 安全分析
  {
    task_pattern: ['security', 'vulnerability', 'exploit', 'attack'],
    primary_persona: 'redteam',
    cognitive_boost: ['threat_modeling']
  },

  // 研究分析
  {
    task_pattern: ['research', 'analyze', 'investigate', 'study'],
    primary_persona: 'scientist',
    cognitive_boost: ['hypothesis_testing']
  },

  // 创意任务
  {
    task_pattern: ['design', 'brainstorm', 'ideate', 'innovate'],
    primary_persona: 'creative',
    cognitive_boost: ['divergent_thinking']
  },

  // 需求分析
  {
    task_pattern: ['requirement', 'user story', 'feature', 'prioritize'],
    primary_persona: 'pm',
    cognitive_boost: ['user_story_thinking']
  },

  // 复杂推理 (Jekyll & Hyde 模式)
  {
    task_pattern: ['complex', 'tricky', 'difficult'],
    primary_persona: 'scientist',
    secondary_personas: ['reviewer'],  // 生成+验证
    cognitive_boost: ['chain_of_thought', 'self_consistency']
  }
];
```

### 4.2 多人格集成 (Jekyll & Hyde)

研究表明，多人格集成可提升 9.98% 的准确率：

```
┌─────────────────────────────────────────────────────────────────┐
│              JEKYLL & HYDE ENSEMBLE                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   Phase 1: Generation (Jekyll)                                  │
│   ─────────────────────────────────────────────────────────     │
│   Persona: Scientist/Engineer (promotion focus)                 │
│   Task: 生成解决方案                                            │
│                                                                 │
│   Phase 2: Verification (Hyde)                                  │
│   ─────────────────────────────────────────────────────────     │
│   Persona: Reviewer/RedTeam (prevention focus)                  │
│   Task: 批判和验证解决方案                                       │
│                                                                 │
│   Phase 3: Synthesis                                            │
│   ─────────────────────────────────────────────────────────     │
│   综合两个视角，输出改进后的结果                                 │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## 5. 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    PERSONA ENGINE ARCHITECTURE                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   User Request                                                  │
│        │                                                        │
│        ▼                                                        │
│   ┌─────────────┐                                               │
│   │ Intent      │ ← 解析任务意图                                 │
│   │ Analyzer    │                                               │
│   └──────┬──────┘                                               │
│          │ task_type, complexity, domain                        │
│          ▼                                                      │
│   ┌─────────────┐    ┌─────────────────┐                        │
│   │ Persona     │───▶│ Persona         │                        │
│   │ Router      │    │ Registry        │                        │
│   └──────┬──────┘    │ (sys_personas)  │                        │
│          │           └─────────────────┘                        │
│          │ selected_personas[]                                  │
│          ▼                                                      │
│   ┌─────────────┐                                               │
│   │ Prompt      │ ← 组合人格特征+认知增强                        │
│   │ Composer    │                                               │
│   └──────┬──────┘                                               │
│          │ enhanced_system_prompt                               │
│          ▼                                                      │
│   ┌─────────────┐                                               │
│   │ LLM         │ ← 带人格增强的调用                             │
│   │ Executor    │                                               │
│   └──────┬──────┘                                               │
│          │                                                      │
│          ▼                                                      │
│   ┌─────────────┐                                               │
│   │ Output      │ ← 可选: Jekyll & Hyde 验证                     │
│   │ Validator   │                                               │
│   └─────────────┘                                               │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## 6. IaST 系统表

```sql
-- 人格档案表
CREATE TABLE sys_personas (
    persona_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,

    -- Big Five 参数
    openness REAL DEFAULT 0.5,
    conscientiousness REAL DEFAULT 0.5,
    extraversion REAL DEFAULT 0.5,
    agreeableness REAL DEFAULT 0.5,
    neuroticism REAL DEFAULT 0.5,

    -- 调节焦点
    regulatory_focus TEXT DEFAULT 'balanced',  -- promotion/prevention/balanced

    -- 认知强制函数 (JSON array)
    cognitive_forcing TEXT DEFAULT '[]',

    -- 行为特征 (JSON array)
    behavioral_traits TEXT DEFAULT '[]',

    -- 适用任务域 (JSON array)
    task_domains TEXT DEFAULT '[]',

    -- System Prompt 模板
    system_prompt_template TEXT,

    -- 元数据
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    -- 统计
    usage_count INTEGER DEFAULT 0,
    success_rate REAL DEFAULT 0.0
);

-- 路由规则表
CREATE TABLE sys_persona_routing (
    rule_id TEXT PRIMARY KEY,
    task_pattern TEXT NOT NULL,           -- 正则或关键词JSON
    primary_persona_id TEXT NOT NULL,
    secondary_persona_ids TEXT,           -- JSON array
    cognitive_boost TEXT,                 -- JSON array
    priority INTEGER DEFAULT 0,           -- 匹配优先级

    FOREIGN KEY (primary_persona_id) REFERENCES sys_personas(persona_id)
);

-- 人格使用历史
CREATE TABLE sys_persona_history (
    history_id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    task_type TEXT,
    persona_ids TEXT,                     -- JSON array
    cognitive_functions TEXT,             -- JSON array
    success BOOLEAN,
    quality_score REAL,                   -- 0-1
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 人格效果视图
CREATE VIEW v_persona_effectiveness AS
SELECT
    p.persona_id,
    p.name,
    COUNT(h.history_id) as total_uses,
    AVG(CASE WHEN h.success THEN 1.0 ELSE 0.0 END) as success_rate,
    AVG(h.quality_score) as avg_quality,
    MAX(h.created_at) as last_used
FROM sys_personas p
LEFT JOIN sys_persona_history h ON p.persona_id IN (
    SELECT value FROM json_each(h.persona_ids)
)
GROUP BY p.persona_id;
```

## 7. Prompt Composition

### 7.1 组合算法

```typescript
function composePrompt(
  personas: PersonaProfile[],
  cognitiveBoosts: string[],
  taskContext: string
): string {
  const parts: string[] = [];

  // 1. 主人格身份
  const primary = personas[0];
  parts.push(`You are a ${primary.name}: ${primary.description}`);

  // 2. Big Five 行为特征
  parts.push('\nBEHAVIORAL TRAITS:');
  for (const trait of primary.behavioral_traits) {
    parts.push(`- ${trait}`);
  }

  // 3. 次要人格视角 (如有)
  if (personas.length > 1) {
    parts.push('\nADDITIONAL PERSPECTIVES:');
    for (const secondary of personas.slice(1)) {
      parts.push(`- Also consider the viewpoint of a ${secondary.name}: ${secondary.description}`);
    }
  }

  // 4. 认知强制函数
  parts.push('\nCOGNITIVE APPROACH:');
  for (const boost of cognitiveBoosts) {
    parts.push(`- ${COGNITIVE_FUNCTION_PROMPTS[boost]}`);
  }

  // 5. 调节焦点
  if (primary.regulatory_focus === 'promotion') {
    parts.push('\nFOCUS: Pursue opportunities and possibilities. Ask "What could we achieve?"');
  } else if (primary.regulatory_focus === 'prevention') {
    parts.push('\nFOCUS: Prevent problems and risks. Ask "What could go wrong?"');
  }

  // 6. 任务上下文
  parts.push(`\nCURRENT TASK:\n${taskContext}`);

  return parts.join('\n');
}

const COGNITIVE_FUNCTION_PROMPTS: Record<string, string> = {
  chain_of_thought: 'Think step by step, showing your reasoning process',
  self_consistency: 'Consider multiple approaches and verify consistency',
  devils_advocate: 'Actively seek reasons why your solution might be wrong',
  hypothesis_testing: 'Form hypotheses and test them against evidence',
  divergent_thinking: 'Generate multiple diverse ideas before converging',
  verification: 'Verify your output meets all requirements before finishing',
  threat_modeling: 'Systematically identify and assess potential threats',
  user_story_thinking: 'Frame problems in terms of user needs and value',
};
```

### 7.2 示例输出

**任务:** "Review this authentication code for security issues"

**生成的 System Prompt:**

```
You are a RedTeam: 安全专家，专注发现漏洞和风险

BEHAVIORAL TRAITS:
- 假设所有输入都是恶意的
- 寻找绕过和突破点
- 不信任任何声称，要验证
- 思考最坏情况

ADDITIONAL PERSPECTIVES:
- Also consider the viewpoint of a Reviewer: 批判性审查者，发现问题和改进空间

COGNITIVE APPROACH:
- Actively seek reasons why your solution might be wrong
- Systematically identify and assess potential threats

FOCUS: Prevent problems and risks. Ask "What could go wrong?"

CURRENT TASK:
Review this authentication code for security issues
```

## 8. 动态人格切换

### 8.1 执行阶段人格

不同执行阶段可以使用不同人格：

```
┌─────────────────────────────────────────────────────────────────┐
│              PHASE-BASED PERSONA SWITCHING                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   P1 研究阶段                                                   │
│   └── Primary: Scientist                                        │
│       Cognitive: hypothesis_testing, evidence_based             │
│                                                                 │
│   P2 设计阶段                                                   │
│   └── Primary: Architect (Engineer variant)                     │
│       Secondary: Creative (for alternatives)                    │
│       Cognitive: divergent_then_converge                        │
│                                                                 │
│   P3 实现阶段                                                   │
│   └── Primary: Engineer                                         │
│       Cognitive: step_by_step, verification                     │
│                                                                 │
│   P4 验证阶段                                                   │
│   └── Primary: Reviewer                                         │
│       Secondary: RedTeam                                        │
│       Cognitive: devils_advocate, systematic_checklist          │
│                                                                 │
│   P5 收尾阶段                                                   │
│   └── Primary: PM                                               │
│       Cognitive: user_story_thinking                            │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 8.2 API 接口

```typescript
// 使用示例
import { PersonaEngine } from '~/Solar/core/persona';

const engine = new PersonaEngine();

// 自动路由
const prompt = await engine.enhance({
  task: "Implement a secure login system",
  context: "Node.js Express application"
});

// 手动指定人格
const prompt2 = await engine.enhance({
  task: "Review this code",
  personas: ['redteam', 'reviewer'],
  cognitive: ['devils_advocate', 'threat_modeling']
});

// Jekyll & Hyde 模式
const result = await engine.executeWithEnsemble({
  task: "Solve this complex algorithm problem",
  generationPersona: 'scientist',
  validationPersona: 'reviewer',
  iterations: 2
});
```

## 9. 与 Solar 集成

### 9.1 Agent 增强

每个 Solar Agent 可以绑定默认人格：

| Agent | 默认人格 | 认知增强 |
|-------|----------|----------|
| @Researcher | scientist | hypothesis_testing |
| @Architect | engineer + creative | divergent_thinking |
| @Coder | engineer | verification |
| @Tester | engineer + redteam | systematic_checklist |
| @Reviewer | reviewer + redteam | devils_advocate |
| @Docs | pm | user_story_thinking |
| @Guard | redteam | threat_modeling |

### 9.2 配置方式

```yaml
# ~/.claude/config/persona-config.yaml
default_persona: engineer

agent_personas:
  Coder:
    primary: engineer
    cognitive: [verification, step_by_step]
  Reviewer:
    primary: reviewer
    secondary: [redteam]
    cognitive: [devils_advocate, systematic_checklist]
  Guard:
    primary: redteam
    cognitive: [threat_modeling]

# 任务类型覆盖
task_overrides:
  - pattern: "security|vulnerability|exploit"
    persona: redteam
  - pattern: "brainstorm|ideate|creative"
    persona: creative
```

## 10. 效果评估

### 10.1 预期提升

基于研究文献的预期效果：

| 任务类型 | 预期提升 | 来源 |
|----------|----------|------|
| 复杂推理 | +10-60% | Role-play prompting 研究 |
| 数学逻辑 | +12-26% | CoT 研究 |
| 代码质量 | +显著 | High-C 效果 |
| 创意任务 | +20% | High-O 效果 |
| 安全审查 | +发现率 | Adversarial thinking |

### 10.2 评估指标

```sql
-- 人格效果追踪视图
CREATE VIEW v_persona_impact AS
SELECT
    persona_id,
    task_domain,
    COUNT(*) as task_count,
    AVG(quality_score) as avg_quality,
    AVG(CASE WHEN success THEN 1.0 ELSE 0.0 END) as success_rate,
    AVG(execution_time_ms) as avg_time
FROM sys_persona_history
GROUP BY persona_id, task_domain
ORDER BY avg_quality DESC;
```

## 11. 实现路线图

### Phase 1: 基础 (1周)
- [ ] 创建 `~/Solar/core/persona/` 目录结构
- [ ] 实现 PersonaProfile 类型和 Registry
- [ ] 实现基础 PromptComposer
- [ ] 创建 6 个核心人格档案

### Phase 2: 路由 (1周)
- [ ] 实现 PersonaRouter
- [ ] 实现任务类型识别
- [ ] 实现路由规则引擎
- [ ] 集成到 Solar Agent 系统

### Phase 3: 集成 (1周)
- [ ] Jekyll & Hyde 多人格集成
- [ ] 阶段性人格切换
- [ ] 与现有 Agent 绑定
- [ ] 效果追踪和统计

### Phase 4: 优化 (持续)
- [ ] 基于数据调优人格参数
- [ ] 学习任务-人格匹配模式
- [ ] 自适应认知增强选择

---

*Persona Engine Design v1.0*
*Solar - 通过人格调制增强推理*
*2026-02-05*
