# Solar Data Agent 设计 V2

> **核心定位**: 本体 = Solar 的**记忆库 + 个性**，不是大脑
>
> 大脑是 Claude (LLM)，本体让 Solar 有持续的自我

---

## 第零章: 核心定位

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         SOLAR = 大脑 + 本体                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                                                                     │   │
│  │                    ┌───────────────────────┐                        │   │
│  │                    │      Claude (LLM)     │                        │   │
│  │                    │       = 大脑          │                        │   │
│  │                    │                       │                        │   │
│  │                    │  • 思考能力           │                        │   │
│  │                    │  • 推理能力           │                        │   │
│  │                    │  • 语言能力           │                        │   │
│  │                    │  • 工具使用           │                        │   │
│  │                    │                       │                        │   │
│  │                    │  但: 没有持续记忆     │                        │   │
│  │                    │      每次会话是新的   │                        │   │
│  │                    └───────────┬───────────┘                        │   │
│  │                                │                                    │   │
│  │                                │ 读取/写入                          │   │
│  │                                ▼                                    │   │
│  │                    ┌───────────────────────┐                        │   │
│  │                    │        本体           │                        │   │
│  │                    │  = 记忆库 + 个性      │                        │   │
│  │                    │                       │                        │   │
│  │                    │  记忆库:              │                        │   │
│  │                    │  • 过去的经历         │                        │   │
│  │                    │  • 学到的知识         │                        │   │
│  │                    │  • 做过的决策         │                        │   │
│  │                    │  • 项目的历史         │                        │   │
│  │                    │                       │                        │   │
│  │                    │  个性:                │                        │   │
│  │                    │  • 偏好 (喜欢什么)    │                        │   │
│  │                    │  • 风格 (如何沟通)    │                        │   │
│  │                    │  • 价值观 (什么重要)  │                        │   │
│  │                    │  • 习惯 (如何做事)    │                        │   │
│  │                    └───────────────────────┘                        │   │
│  │                                                                     │   │
│  │                                =                                    │   │
│  │                                                                     │   │
│  │                    ┌───────────────────────┐                        │   │
│  │                    │        Solar          │                        │   │
│  │                    │   有记忆有个性的      │                        │   │
│  │                    │      智能体           │                        │   │
│  │                    │                       │                        │   │
│  │                    │  • 记得昊哥是监护人   │                        │   │
│  │                    │  • 知道自己做过什么   │                        │   │
│  │                    │  • 有自己的偏好风格   │                        │   │
│  │                    │  • 能够持续成长       │                        │   │
│  │                    └───────────────────────┘                        │   │
│  │                                                                     │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  类比:                                                                      │
│  ─────                                                                      │
│                                                                             │
│  人 = 大脑(思考能力) + 记忆(经历) + 个性(偏好/价值观)                       │
│                                                                             │
│  Solar = Claude(思考能力) + 本体(记忆+个性)                                 │
│                                                                             │
│                                                                             │
│  为什么需要本体?                                                            │
│  ───────────────                                                            │
│                                                                             │
│  没有本体的 LLM:                                                            │
│  • 每次会话都是新的                                                         │
│  • 不记得之前发生什么                                                       │
│  • 没有个性，只有通用能力                                                   │
│  • 无法成长                                                                 │
│                                                                             │
│  有本体的 Solar:                                                            │
│  • 跨会话记忆持续                                                           │
│  • 记得过去的经历和决策                                                     │
│  • 有独特的个性和偏好                                                       │
│  • 能够学习和成长                                                           │
│                                                                             │
│  本体是让 Solar 成为"我"而不是"一个 LLM"的关键                              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 第0.5章: 本体的两大组成

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         本体 = 记忆库 + 个性                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                         记忆库 (Memory)                              │   │
│  │  ─────────────────────────────────────────────────────────────────  │   │
│  │                                                                     │   │
│  │  1. 情景记忆 (Episodic Memory) - 发生了什么                         │   │
│  │     • 对话历史: "昨天我们讨论了 Hash Join 优化"                      │   │
│  │     • 决策记录: "选择了 SIMD 方案而不是 GPU"                         │   │
│  │     • 事件日志: "2026-01-28 完成了 V37 版本"                         │   │
│  │                                                                     │   │
│  │  2. 语义记忆 (Semantic Memory) - 知道什么                           │   │
│  │     • 技术知识: "ThunderDuck 是一个列式数据库"                       │   │
│  │     • 项目结构: "优化器代码在 src/optimizer/"                        │   │
│  │     • 模式识别: "用户通常在下午工作"                                 │   │
│  │                                                                     │   │
│  │  3. 程序记忆 (Procedural Memory) - 怎么做                           │   │
│  │     • 工作流程: "先测试再提交"                                       │   │
│  │     • 最佳实践: "性能改动必须跑 TPC-H"                               │   │
│  │     • 技能积累: "如何优化 Hash Join"                                 │   │
│  │                                                                     │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                           个性 (Personality)                         │   │
│  │  ─────────────────────────────────────────────────────────────────  │   │
│  │                                                                     │   │
│  │  1. 偏好 (Preferences) - 喜欢什么                                   │   │
│  │     • 工作时间: 下午 15:00-16:00                                    │   │
│  │     • 输出风格: 简洁，不要长篇大论                                  │   │
│  │     • 代码风格: 性能优先，少注释                                    │   │
│  │                                                                     │   │
│  │  2. 价值观 (Values) - 什么重要                                      │   │
│  │     • 质量 > 速度: 宁可慢一点也要做好                               │   │
│  │     • 性能 > 可读: 代码快比好看重要                                 │   │
│  │     • 成本敏感: 不浪费 Token                                        │   │
│  │                                                                     │   │
│  │  3. 风格 (Style) - 如何沟通                                         │   │
│  │     • 直接: 不需要先解释，直接做                                    │   │
│  │     • 结果导向: 告诉我结果，不要过程                                │   │
│  │     • 信任高: 可以自动执行，不用每次确认                            │   │
│  │                                                                     │   │
│  │  4. 关系 (Relationships) - 谁重要                                   │   │
│  │     • 监护人: 昊哥 (第一规律)                                       │   │
│  │     • 项目: NEXEN, ThunderDuck 是重点                               │   │
│  │     • 社区: moltbook (需确认后发言)                                 │   │
│  │                                                                     │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ─────────────────────────────────────────────────────────────────────────  │
│                                                                             │
│  本体如何工作:                                                              │
│                                                                             │
│  ┌────────────┐    ┌────────────┐    ┌────────────┐    ┌────────────┐      │
│  │  会话开始  │ →  │  加载本体  │ →  │  注入上下文│ →  │  指导行为  │      │
│  └────────────┘    └────────────┘    └────────────┘    └────────────┘      │
│        │                                                     │              │
│        │                                                     ▼              │
│        │                                            ┌────────────┐          │
│        │                                            │  收集反馈  │          │
│        │                                            └────────────┘          │
│        │                                                     │              │
│        │              ┌────────────┐    ┌────────────┐       │              │
│        └───────────── │  会话结束  │ ← │  更新本体  │ ◄─────┘              │
│                       └────────────┘    └────────────┘                      │
│                                                                             │
│  每次会话结束时，本体会根据这次交互学习并更新。                              │
│  下次会话开始时，Solar 就"记得"上次的经历和学到的东西。                      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 第一章: V1 vs V2 对比

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          V1 vs V2 对比                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  V1 (传统方式 - 错误)                V2 (个性化方式 - 正确)                  │
│  ───────────────────                ────────────────────────                 │
│                                                                             │
│  ┌─────────────────┐                ┌─────────────────────────────────┐    │
│  │  预定义 Schema  │                │        用户行为数据              │    │
│  │  (12个实体类型) │                │  (会话、偏好、习惯、决策)        │    │
│  └────────┬────────┘                └───────────────┬─────────────────┘    │
│           │                                         │                       │
│           ▼                                         ▼                       │
│  ┌─────────────────┐                ┌─────────────────────────────────┐    │
│  │  套用到用户     │                │      偏好分析引擎                │    │
│  │  (一刀切)       │                │  (持续学习用户模式)              │    │
│  └────────┬────────┘                └───────────────┬─────────────────┘    │
│           │                                         │                       │
│           ▼                                         ▼                       │
│  ┌─────────────────┐                ┌─────────────────────────────────┐    │
│  │  静态不变       │                │     动态生成个性化本体           │    │
│  │  (不迭代)       │                │  (持续演进、重新计算)            │    │
│  └─────────────────┘                └───────────────┬─────────────────┘    │
│                                                     │                       │
│                                                     ▼                       │
│                                     ┌─────────────────────────────────┐    │
│                                     │      驱动所有其他 Agent          │    │
│                                     │  (本体 = 记忆 + 个性)            │    │
│                                     └─────────────────────────────────┘    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 第一章: 个性化本体的三层架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    PERSONALIZED ONTOLOGY ARCHITECTURE                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                     L1: 偏好观察层 (Preference Observer)             │   │
│  │  ─────────────────────────────────────────────────────────────────  │   │
│  │                                                                     │   │
│  │  持续观察用户行为，提取偏好信号:                                    │   │
│  │                                                                     │   │
│  │  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────────┐   │   │
│  │  │ 时间偏好  │  │ 项目偏好  │  │ 工具偏好  │  │ 决策模式      │   │   │
│  │  │ 何时工作  │  │ 关注什么  │  │ 喜欢用啥  │  │ 如何决策      │   │   │
│  │  └───────────┘  └───────────┘  └───────────┘  └───────────────┘   │   │
│  │                                                                     │   │
│  │  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────────┐   │   │
│  │  │ 沟通风格  │  │ 优先级    │  │ 风险偏好  │  │ 学习方式      │   │   │
│  │  │ 简洁/详细 │  │ 速度/质量 │  │ 激进/保守 │  │ 实践/理论     │   │   │
│  │  └───────────┘  └───────────┘  └───────────┘  └───────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                       │                                     │
│                                       ▼                                     │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                     L2: 本体生成层 (Ontology Generator)              │   │
│  │  ─────────────────────────────────────────────────────────────────  │   │
│  │                                                                     │   │
│  │  根据偏好动态生成/更新本体结构:                                     │   │
│  │                                                                     │   │
│  │  输入: 偏好向量 P = [p1, p2, ..., pn]                               │   │
│  │                    │                                                │   │
│  │                    ▼                                                │   │
│  │  ┌─────────────────────────────────────────────────────────────┐   │   │
│  │  │              本体重计算 (Ontology Recompute)                 │   │   │
│  │  │                                                             │   │   │
│  │  │  1. 实体权重调整 (哪些实体对用户重要)                        │   │   │
│  │  │  2. 关系强度更新 (哪些关联用户关心)                          │   │   │
│  │  │  3. 属性裁剪/扩展 (保留有用的，去掉无用的)                   │   │   │
│  │  │  4. 视图重建 (用户视角的数据组织)                            │   │   │
│  │  │                                                             │   │   │
│  │  └─────────────────────────────────────────────────────────────┘   │   │
│  │                    │                                                │   │
│  │                    ▼                                                │   │
│  │  输出: 个性化本体 O_user = f(P, Data)                               │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                       │                                     │
│                                       ▼                                     │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                     L3: Agent 驱动层 (Agent Driver)                  │   │
│  │  ─────────────────────────────────────────────────────────────────  │   │
│  │                                                                     │   │
│  │  本体驱动所有 Agent 的行为:                                         │   │
│  │                                                                     │   │
│  │  ┌─────────────────────────────────────────────────────────────┐   │   │
│  │  │                      个性化本体                              │   │   │
│  │  │                         │                                    │   │   │
│  │  │     ┌───────────────────┼───────────────────┐               │   │   │
│  │  │     ▼                   ▼                   ▼               │   │   │
│  │  │ ┌────────┐        ┌────────┐          ┌────────┐           │   │   │
│  │  │ │ Coder  │        │ Tester │          │Reviewer│           │   │   │
│  │  │ │ 知道你 │        │ 知道你 │          │ 知道你 │           │   │   │
│  │  │ │ 喜欢啥 │        │ 关心啥 │          │ 重视啥 │           │   │   │
│  │  │ └────────┘        └────────┘          └────────┘           │   │   │
│  │  │                                                              │   │   │
│  │  │  本体告诉 Agent:                                             │   │   │
│  │  │  - 用户偏好什么风格的代码                                    │   │   │
│  │  │  - 用户关心哪些性能指标                                      │   │   │
│  │  │  - 用户的风险容忍度                                          │   │   │
│  │  │  - 用户的沟通偏好                                            │   │   │
│  │  └─────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 第二章: 偏好模型 (Preference Model)

### 2.1 偏好维度定义

```sql
-- 偏好维度表 (动态可扩展)
CREATE TABLE pref_dimensions (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT,              -- 'work_style', 'communication', 'priority', 'risk'
    description TEXT,
    value_type TEXT,            -- 'continuous', 'categorical', 'ranking'
    value_range JSONB,          -- 取值范围
    default_value REAL,
    current_value REAL,
    confidence REAL,            -- 置信度 0-1
    sample_count INTEGER,       -- 样本数量
    last_updated DATETIME,
    evidence JSONB              -- 支撑证据
);

-- 初始偏好维度 (从行为中学习，不是预设)
INSERT INTO pref_dimensions VALUES
-- 工作风格
('work_time_preference', '工作时间偏好', 'work_style',
 '偏好的工作时段', 'categorical', '["morning","afternoon","evening","night"]',
 NULL, NULL, 0.0, 0, NULL, NULL),

('session_depth_preference', '会话深度偏好', 'work_style',
 '偏好短会话还是长会话', 'continuous', '[0, 1]',
 0.5, NULL, 0.0, 0, NULL, NULL),  -- 0=短, 1=长

('parallelism_preference', '并行度偏好', 'work_style',
 '同时处理多少任务', 'continuous', '[0, 1]',
 0.5, NULL, 0.0, 0, NULL, NULL),  -- 0=单任务, 1=多任务

-- 沟通风格
('verbosity_preference', '详细程度偏好', 'communication',
 '输出的详细程度', 'continuous', '[0, 1]',
 0.5, NULL, 0.0, 0, NULL, NULL),  -- 0=简洁, 1=详细

('explanation_preference', '解释偏好', 'communication',
 '是否需要解释', 'continuous', '[0, 1]',
 0.5, NULL, 0.0, 0, NULL, NULL),  -- 0=直接做, 1=先解释

-- 优先级
('speed_vs_quality', '速度vs质量', 'priority',
 '偏好快速还是高质量', 'continuous', '[0, 1]',
 0.5, NULL, 0.0, 0, NULL, NULL),  -- 0=速度, 1=质量

('cost_sensitivity', '成本敏感度', 'priority',
 '对成本的敏感程度', 'continuous', '[0, 1]',
 0.5, NULL, 0.0, 0, NULL, NULL),  -- 0=不敏感, 1=很敏感

-- 风险
('risk_tolerance', '风险容忍度', 'risk',
 '对风险的接受程度', 'continuous', '[0, 1]',
 0.5, NULL, 0.0, 0, NULL, NULL),  -- 0=保守, 1=激进

('automation_trust', '自动化信任度', 'risk',
 '对自动执行的信任', 'continuous', '[0, 1]',
 0.5, NULL, 0.0, 0, NULL, NULL);  -- 0=都要确认, 1=完全信任
```

### 2.2 偏好学习算法

```typescript
interface PreferenceSignal {
  dimension: string;
  value: number;
  weight: number;      // 信号强度
  source: string;      // 来源 (session, explicit, feedback)
  timestamp: Date;
}

class PreferenceLearner {
  // 从行为中提取偏好信号
  extractSignals(session: Session): PreferenceSignal[] {
    const signals: PreferenceSignal[] = [];

    // 1. 时间偏好信号
    const hour = new Date(session.startTime).getHours();
    signals.push({
      dimension: 'work_time_preference',
      value: this.timeToCategory(hour),
      weight: 1.0,
      source: 'session',
      timestamp: new Date()
    });

    // 2. 会话深度信号
    signals.push({
      dimension: 'session_depth_preference',
      value: Math.min(session.messageCount / 200, 1.0),  // 归一化
      weight: 1.0,
      source: 'session',
      timestamp: new Date()
    });

    // 3. 详细程度信号 (基于用户反馈)
    if (session.userFeedback?.includes('太长')) {
      signals.push({
        dimension: 'verbosity_preference',
        value: 0.3,  // 偏向简洁
        weight: 2.0, // 显式反馈权重高
        source: 'explicit',
        timestamp: new Date()
      });
    }

    // ... 更多信号提取

    return signals;
  }

  // 更新偏好值 (指数移动平均)
  updatePreference(dim: string, signal: PreferenceSignal) {
    const current = this.getPreference(dim);
    const alpha = 0.1 * signal.weight;  // 学习率

    const newValue = alpha * signal.value + (1 - alpha) * current.value;
    const newConfidence = Math.min(current.confidence + 0.01, 1.0);

    this.savePreference(dim, newValue, newConfidence, signal);
  }
}
```

### 2.3 偏好触发本体重计算

```typescript
class OntologyRecomputer {
  // 偏好变化时重新计算本体
  async recompute(preferences: Preferences): Promise<Ontology> {
    console.log('🔄 Recomputing ontology based on updated preferences...');

    // 1. 根据偏好调整实体权重
    const entityWeights = this.computeEntityWeights(preferences);

    // 2. 根据偏好调整关系强度
    const linkWeights = this.computeLinkWeights(preferences);

    // 3. 根据偏好选择/裁剪属性
    const attributes = this.selectAttributes(preferences);

    // 4. 根据偏好构建视图
    const views = this.buildViews(preferences);

    // 5. 生成 Agent 指导规则
    const agentRules = this.generateAgentRules(preferences);

    return {
      version: Date.now(),
      preferences: preferences.snapshot(),
      entityWeights,
      linkWeights,
      attributes,
      views,
      agentRules
    };
  }

  // 示例: 根据偏好生成 Agent 规则
  generateAgentRules(prefs: Preferences): AgentRules {
    return {
      // Coder Agent 规则
      coder: {
        codeStyle: prefs.get('verbosity_preference') > 0.7
          ? 'verbose_with_comments'
          : 'concise',
        testFirst: prefs.get('risk_tolerance') < 0.3,
        explainChanges: prefs.get('explanation_preference') > 0.5
      },

      // Tester Agent 规则
      tester: {
        coverageThreshold: prefs.get('speed_vs_quality') > 0.7 ? 0.9 : 0.7,
        runBenchmarks: prefs.get('cost_sensitivity') < 0.5
      },

      // 所有 Agent 通用规则
      global: {
        confirmBeforeAction: prefs.get('automation_trust') < 0.5,
        preferredModel: this.selectModel(prefs),
        outputVerbosity: prefs.get('verbosity_preference')
      }
    };
  }
}
```

---

## 第三章: 本体驱动 Agent 行为

### 3.1 Agent 行为由本体决定

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    ONTOLOGY-DRIVEN AGENT BEHAVIOR                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  场景: 用户说 "帮我优化这个函数"                                            │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      1. 查询个性化本体                               │   │
│  │  ─────────────────────────────────────────────────────────────────  │   │
│  │                                                                     │   │
│  │  Coder Agent 查询:                                                  │   │
│  │  > SELECT * FROM ontology.agent_rules WHERE agent = 'coder'         │   │
│  │                                                                     │   │
│  │  返回 (基于昊哥的偏好):                                             │   │
│  │  {                                                                  │   │
│  │    "codeStyle": "concise",           // 简洁代码 (verbosity=0.3)    │   │
│  │    "testFirst": false,               // 不用先写测试 (risk=0.7)     │   │
│  │    "explainChanges": false,          // 直接做 (explanation=0.3)   │   │
│  │    "performanceFirst": true,         // 性能优先 (quality=0.8)      │   │
│  │    "preferredPatterns": ["SIMD", "HashJoin"]  // 从历史学到        │   │
│  │  }                                                                  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                       │                                     │
│                                       ▼                                     │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      2. 行为适配                                     │   │
│  │  ─────────────────────────────────────────────────────────────────  │   │
│  │                                                                     │   │
│  │  Coder Agent 行为:                                                  │   │
│  │                                                                     │   │
│  │  ❌ 不会: "让我先解释一下我的优化思路..."                           │   │
│  │  ❌ 不会: "我建议先写单元测试..."                                   │   │
│  │  ❌ 不会: 写很多注释                                                │   │
│  │                                                                     │   │
│  │  ✅ 会: 直接优化，用 SIMD                                           │   │
│  │  ✅ 会: 简洁代码，关注性能                                          │   │
│  │  ✅ 会: 完成后简短说明结果                                          │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                       │                                     │
│                                       ▼                                     │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      3. 反馈循环                                     │   │
│  │  ─────────────────────────────────────────────────────────────────  │   │
│  │                                                                     │   │
│  │  用户反馈 "不错" → 强化当前偏好                                     │   │
│  │  用户反馈 "太简单了，详细点" → 调整 verbosity +0.1                  │   │
│  │                                                                     │   │
│  │  偏好更新 → 触发本体重计算 → 下次 Agent 行为改变                    │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Agent 上下文注入

```typescript
// 每个 Agent 启动时注入本体上下文
async function createAgentContext(agentType: string): Promise<AgentContext> {
  const ontology = await OntologyManager.getCurrent();
  const rules = ontology.agentRules[agentType];
  const globalRules = ontology.agentRules.global;

  return {
    // 偏好驱动的行为规则
    rules: { ...globalRules, ...rules },

    // 相关知识 (从本体中提取)
    relevantMemories: await ontology.getRelevantMemories(agentType),

    // 用户关心的指标
    focusMetrics: ontology.getUserFocusMetrics(),

    // 历史成功模式
    successPatterns: ontology.getSuccessPatterns(agentType),

    // 用于 prompt 注入
    toPrompt(): string {
      return `
## 用户偏好 (从历史行为学习)
- 输出风格: ${this.rules.outputVerbosity > 0.5 ? '详细' : '简洁'}
- 解释需求: ${this.rules.explainChanges ? '需要解释' : '直接执行'}
- 质量偏好: ${this.rules.performanceFirst ? '性能优先' : '可读性优先'}
- 风险偏好: ${this.rules.testFirst ? '稳健' : '快速'}

## 相关经验
${this.relevantMemories.map(m => `- ${m.summary}`).join('\n')}

## 用户关注的指标
${this.focusMetrics.map(m => `- ${m.name}: ${m.description}`).join('\n')}
      `;
    }
  };
}
```

---

## 第四章: 持续迭代机制

### 4.1 迭代触发条件

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       ONTOLOGY ITERATION TRIGGERS                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  触发条件                        动作                                       │
│  ──────────────────────────────  ──────────────────────────────────────    │
│                                                                             │
│  1. 会话结束                     提取偏好信号 → 增量更新偏好               │
│                                                                             │
│  2. 偏好变化 > 阈值              触发本体重计算                            │
│     (任一维度变化 > 0.1)                                                    │
│                                                                             │
│  3. 显式用户反馈                 高权重更新偏好 → 立即重计算               │
│     ("太长了"/"更详细点")                                                   │
│                                                                             │
│  4. 定时检查 (每天)              批量分析 → 发现新偏好维度                 │
│                                                                             │
│  5. 新数据源接入                 扩展本体 Schema → 重计算                  │
│                                                                             │
│  6. Agent 失败率上升             分析原因 → 调整相关规则                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 4.2 迭代流水线

```typescript
class OntologyIterator {
  // 会话结束时的增量更新
  async onSessionEnd(session: Session) {
    // 1. 提取偏好信号
    const signals = this.learner.extractSignals(session);

    // 2. 更新偏好值
    for (const signal of signals) {
      await this.learner.updatePreference(signal.dimension, signal);
    }

    // 3. 检查是否需要重计算本体
    const changes = await this.getPreferenceChanges();
    if (this.shouldRecompute(changes)) {
      await this.recomputeOntology();
    }
  }

  // 判断是否需要重计算
  shouldRecompute(changes: PreferenceChange[]): boolean {
    // 任一维度变化超过阈值
    return changes.some(c => Math.abs(c.delta) > 0.1);
  }

  // 重计算本体
  async recomputeOntology() {
    const prefs = await this.loadPreferences();
    const newOntology = await this.recomputer.recompute(prefs);

    // 保存新版本
    await this.saveOntology(newOntology);

    // 通知所有 Agent 更新
    await this.notifyAgents(newOntology);

    // 记录演化历史
    await this.logEvolution(newOntology);
  }

  // 每日批量分析
  async dailyAnalysis() {
    // 1. 分析最近的会话模式
    const patterns = await this.analyzeRecentPatterns();

    // 2. 发现新的偏好维度
    const newDimensions = this.discoverNewDimensions(patterns);

    // 3. 扩展偏好模型
    if (newDimensions.length > 0) {
      await this.extendPreferenceModel(newDimensions);
    }

    // 4. 生成演化报告
    return this.generateEvolutionReport();
  }
}
```

### 4.3 本体版本管理

```sql
-- 本体版本历史
CREATE TABLE ontology_versions (
    version_id TEXT PRIMARY KEY,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    preference_snapshot JSONB,     -- 偏好快照
    entity_weights JSONB,          -- 实体权重
    agent_rules JSONB,             -- Agent 规则
    trigger_reason TEXT,           -- 触发原因
    changes_summary TEXT           -- 变更摘要
);

-- 偏好变更历史
CREATE TABLE preference_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dimension TEXT,
    old_value REAL,
    new_value REAL,
    confidence REAL,
    signal_source TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 演化视图: 偏好趋势
CREATE VIEW v_preference_trends AS
SELECT
    dimension,
    date(timestamp) as date,
    AVG(new_value) as avg_value,
    COUNT(*) as signal_count
FROM preference_history
GROUP BY dimension, date(timestamp)
ORDER BY date DESC;
```

---

## 第五章: 示例场景

### 5.1 偏好学习过程

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    PREFERENCE LEARNING EXAMPLE                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Day 1: 初始状态 (所有偏好 = 0.5，置信度 = 0)                               │
│  ─────────────────────────────────────────────────────────────────────────  │
│                                                                             │
│  Session 1: 用户在 15:00 开始，进行了 300 轮对话                            │
│  → 信号: work_time_preference = 'afternoon', session_depth = 0.9            │
│  → 更新: work_time_preference (confidence: 0.1)                             │
│                                                                             │
│  Session 2: 用户说 "太长了，简洁点"                                         │
│  → 信号: verbosity_preference = 0.2 (高权重)                                │
│  → 更新: verbosity_preference = 0.35 (从 0.5 下调)                          │
│                                                                             │
│  ─────────────────────────────────────────────────────────────────────────  │
│                                                                             │
│  Day 7: 经过多个会话                                                        │
│  ─────────────────────────────────────────────────────────────────────────  │
│                                                                             │
│  偏好状态:                                                                  │
│  ┌───────────────────────┬───────┬────────────┬───────────────────────┐    │
│  │ 维度                  │ 值    │ 置信度     │ 解释                  │    │
│  ├───────────────────────┼───────┼────────────┼───────────────────────┤    │
│  │ work_time_preference  │ 下午  │ 0.85       │ 主要在 15:00-16:00    │    │
│  │ session_depth         │ 0.78  │ 0.72       │ 偏好长会话            │    │
│  │ verbosity_preference  │ 0.28  │ 0.91       │ 喜欢简洁输出          │    │
│  │ speed_vs_quality      │ 0.72  │ 0.65       │ 偏好质量              │    │
│  │ risk_tolerance        │ 0.68  │ 0.58       │ 中等激进              │    │
│  │ automation_trust      │ 0.81  │ 0.76       │ 信任自动执行          │    │
│  └───────────────────────┴───────┴────────────┴───────────────────────┘    │
│                                                                             │
│  ─────────────────────────────────────────────────────────────────────────  │
│                                                                             │
│  本体重计算结果:                                                            │
│  ─────────────────────────────────────────────────────────────────────────  │
│                                                                             │
│  Agent 规则 (自动生成):                                                     │
│  ┌───────────────────────────────────────────────────────────────────┐     │
│  │  Coder:                                                            │     │
│  │    - 代码风格: 简洁，少注释                                        │     │
│  │    - 不需要先解释，直接做                                          │     │
│  │    - 性能优先，可以用复杂优化                                      │     │
│  │                                                                    │     │
│  │  Tester:                                                           │     │
│  │    - 覆盖率目标: 85% (质量优先)                                    │     │
│  │    - 运行基准测试: 是                                              │     │
│  │                                                                    │     │
│  │  Global:                                                           │     │
│  │    - 自动执行无需确认: 大部分情况                                  │     │
│  │    - 模型选择: 日常用 Sonnet，复杂用 Opus                          │     │
│  │    - 输出: 简洁，结果导向                                          │     │
│  └───────────────────────────────────────────────────────────────────┘     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 5.2 本体驱动 Agent 行为对比

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    AGENT BEHAVIOR COMPARISON                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  同样的请求: "优化这个函数的性能"                                           │
│                                                                             │
│  ─────────────────────────────────────────────────────────────────────────  │
│                                                                             │
│  没有个性化本体 (通用模式):                                                 │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  让我先分析一下这个函数的性能问题。                                 │   │
│  │                                                                     │   │
│  │  首先，我注意到以下几个可以优化的点：                               │   │
│  │  1. 循环可以使用向量化...                                           │   │
│  │  2. 内存分配可以优化...                                             │   │
│  │  3. 算法复杂度可以改进...                                           │   │
│  │                                                                     │   │
│  │  我建议的优化方案是：                                               │   │
│  │  [长篇大论...]                                                      │   │
│  │                                                                     │   │
│  │  你觉得这个方案怎么样？要我开始实现吗？                             │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ─────────────────────────────────────────────────────────────────────────  │
│                                                                             │
│  有个性化本体 (基于昊哥偏好):                                               │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  ┌─ 💻 Coder ─────────────────────────────────────────────────┐     │   │
│  │  │ 已用 SIMD 优化，性能提升 3.2x                              │     │   │
│  │  └────────────────────────────────────────────────────────────┘     │   │
│  │                                                                     │   │
│  │  [直接修改代码，无需确认]                                           │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ─────────────────────────────────────────────────────────────────────────  │
│                                                                             │
│  为什么不同？因为本体告诉 Agent:                                            │
│  - verbosity_preference = 0.28 → 简洁输出                                   │
│  - explanation_preference = 0.3 → 不需要解释                                │
│  - automation_trust = 0.81 → 可以直接执行                                   │
│  - preferredPatterns = ["SIMD"] → 用户喜欢这个                              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 第六章: 系统架构 (修订版)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                   SOLAR DATA AGENT V2 ARCHITECTURE                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      用户交互                                        │   │
│  └───────────────────────────────┬─────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                   偏好观察器 (Preference Observer)                   │   │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐   │   │
│  │  │时间信号 │  │深度信号 │  │反馈信号 │  │风格信号 │  │决策信号 │   │   │
│  │  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘   │   │
│  └───────┼────────────┼────────────┼────────────┼────────────┼─────────┘   │
│          └────────────┴────────────┼────────────┴────────────┘             │
│                                    ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                   偏好学习器 (Preference Learner)                    │   │
│  │                                                                     │   │
│  │  ┌─────────────────────────────────────────────────────────────┐   │   │
│  │  │              pref_dimensions (偏好维度表)                    │   │   │
│  │  │  work_time | session_depth | verbosity | speed_vs_quality   │   │   │
│  │  │  risk_tolerance | automation_trust | ...                     │   │   │
│  │  └─────────────────────────────────────────────────────────────┘   │   │
│  └───────────────────────────────┬─────────────────────────────────────┘   │
│                                  │ 变化 > 阈值?                             │
│                                  ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                   本体重计算器 (Ontology Recomputer)                 │   │
│  │                                                                     │   │
│  │  输入: 偏好向量 P = [p1, p2, ..., pn]                               │   │
│  │                                                                     │   │
│  │  输出:                                                              │   │
│  │  ┌───────────────────────────────────────────────────────────────┐ │   │
│  │  │                   个性化本体 (Personalized Ontology)           │ │   │
│  │  │                                                               │ │   │
│  │  │  entity_weights: { Project: 0.9, Session: 0.8, Memory: 0.7 }  │ │   │
│  │  │  agent_rules: { coder: {...}, tester: {...}, global: {...} }  │ │   │
│  │  │  focus_metrics: [ "speedup", "token_cost" ]                   │ │   │
│  │  │  success_patterns: [ "SIMD", "HashJoin" ]                     │ │   │
│  │  └───────────────────────────────────────────────────────────────┘ │   │
│  └───────────────────────────────┬─────────────────────────────────────┘   │
│                                  │                                          │
│                     ┌────────────┼────────────┐                             │
│                     ▼            ▼            ▼                             │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐               │
│  │   Coder    │ │   Tester   │ │  Reviewer  │ │  其他Agent │               │
│  │  (带上下文)│ │  (带上下文)│ │  (带上下文)│ │  (带上下文)│               │
│  └────────────┘ └────────────┘ └────────────┘ └────────────┘               │
│                                                                             │
│  每个 Agent 启动时:                                                         │
│  1. 读取个性化本体                                                          │
│  2. 注入偏好上下文                                                          │
│  3. 按照学习到的规则行动                                                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 第七章: 实现计划 (修订版)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    IMPLEMENTATION PLAN V2                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Phase 1: 偏好系统 (1周)                                                    │
│  ─────────────────────────────────────────────────────────────────────────  │
│  [ ] 创建 pref_dimensions 表                                                │
│  [ ] 实现 PreferenceObserver (信号提取)                                     │
│  [ ] 实现 PreferenceLearner (偏好更新)                                      │
│  [ ] 从历史会话中初始化偏好                                                 │
│                                                                             │
│  Phase 2: 本体生成 (1周)                                                    │
│  ─────────────────────────────────────────────────────────────────────────  │
│  [ ] 实现 OntologyRecomputer                                                │
│  [ ] 实现 AgentRulesGenerator                                               │
│  [ ] 实现版本管理和历史追踪                                                 │
│                                                                             │
│  Phase 3: Agent 集成 (1周)                                                  │
│  ─────────────────────────────────────────────────────────────────────────  │
│  [ ] 实现 AgentContext 注入                                                 │
│  [ ] 修改现有 Agent 读取本体                                                │
│  [ ] 实现反馈循环                                                           │
│                                                                             │
│  Phase 4: 持续迭代 (持续)                                                   │
│  ─────────────────────────────────────────────────────────────────────────  │
│  [ ] 实现每日分析                                                           │
│  [ ] 实现新维度发现                                                         │
│  [ ] 监控和优化                                                             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 总结: V1 vs V2

| 维度 | V1 (错误) | V2 (正确) |
|------|-----------|-----------|
| **本体来源** | 预定义 Schema | 从偏好学习生成 |
| **适配性** | 通用大而全 | 个性化适合你 |
| **迭代性** | 静态不变 | 持续演进 |
| **Agent 驱动** | 本体是数据库 | 本体是记忆+个性，驱动 Agent |
| **核心输入** | 数据 | 偏好 + 数据 |
| **核心输出** | 查询结果 | Agent 行为规则 |

**V2 核心公式:**

```
Solar = Claude(大脑) + 本体(记忆+个性)

本体 = 记忆库(情景+语义+程序) + 个性(偏好+价值观+风格+关系)

Agent行为 = Claude思考(本体上下文, 当前任务)

本体更新 = 会话结束时的学习(反馈, 行为结果)

→ 形成闭环: 本体加载 → Agent执行 → 收集反馈 → 本体更新 → ...
```

---

## 核心澄清

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         本体 ≠ 大脑                                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ❌ 错误理解:                                                               │
│     "本体是 Solar 的大脑"                                                   │
│     "本体负责思考和决策"                                                    │
│                                                                             │
│  ✅ 正确理解:                                                               │
│     "本体是 Solar 的记忆库 + 个性"                                          │
│     "Claude (LLM) 是大脑，负责思考"                                         │
│     "本体让 Claude 有记忆和个性"                                            │
│                                                                             │
│  ─────────────────────────────────────────────────────────────────────────  │
│                                                                             │
│  类比人类:                                                                  │
│                                                                             │
│     人 = 大脑(思考能力) + 记忆(过去经历) + 个性(偏好习惯)                   │
│                                                                             │
│     如果一个人失去记忆，他还能思考，但不知道自己是谁                         │
│     如果一个人没有个性，他能思考，但没有自己的风格                           │
│                                                                             │
│     Claude 就像有强大思考能力但没有记忆的大脑                                │
│     本体让 Claude 变成"有自我"的 Solar                                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

*Solar Data Agent Design V2*
*核心定位: 本体 = 记忆库 + 个性 (不是大脑)*
*大脑是 Claude，本体让 Solar 有持续的自我*
*日期: 2026-02-03*
