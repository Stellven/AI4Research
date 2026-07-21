# Solar Unified Orchestrator Design

> 统一编排器 - 串联 Intent → Persona → REE → ARE → Track

## 1. 架构概览

```
┌─────────────────────────────────────────────────────────────────┐
│                    UNIFIED ORCHESTRATOR                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   用户输入                                                       │
│       │                                                         │
│       ▼                                                         │
│   ┌───────────────────────────────────────────────────────┐    │
│   │              Step 1: Intent 解析                       │    │
│   │  ┌─────────┐  ┌─────────┐  ┌─────────┐               │    │
│   │  │ Action  │  │ Domain  │  │Confidence│               │    │
│   │  │ Detect  │  │ Detect  │  │  Score  │               │    │
│   │  └─────────┘  └─────────┘  └─────────┘               │    │
│   └───────────────────────────────────────────────────────┘    │
│       │                                                         │
│       ▼                                                         │
│   ┌───────────────────────────────────────────────────────┐    │
│   │              Step 2: Persona 选择                      │    │
│   │                                                        │    │
│   │  TaskProfile × PersonaProfiles → Affinity Scores      │    │
│   │                                                        │    │
│   │  ┌─────────┐ ┌─────────┐ ┌─────────┐                 │    │
│   │  │scientist│ │engineer │ │ redteam │ ...              │    │
│   │  │  0.41   │ │  0.35   │ │  0.33   │                  │    │
│   │  └─────────┘ └─────────┘ └─────────┘                 │    │
│   │                      │                                 │    │
│   │                      ▼                                 │    │
│   │         Top-N Selection + Softmax Normalization        │    │
│   └───────────────────────────────────────────────────────┘    │
│       │                                                         │
│       ▼                                                         │
│   ┌───────────────────────────────────────────────────────┐    │
│   │              Step 3: REE 资源匹配                      │    │
│   │                                                        │    │
│   │  Priority: Shortcuts → Scripts → Skills → MCP         │    │
│   │                                                        │    │
│   │  ┌──────────┐                                         │    │
│   │  │ 有匹配？ │                                         │    │
│   │  └────┬─────┘                                         │    │
│   │       │                                                │    │
│   │   ┌───┴───┐                                           │    │
│   │   ▼       ▼                                           │    │
│   │  Yes     No                                           │    │
│   │   │       │                                           │    │
│   │   ▼       ▼                                           │    │
│   │ execute  recommend                                    │    │
│   │ _cached  策略                                         │    │
│   └───────────────────────────────────────────────────────┘    │
│       │                                                         │
│       ▼                                                         │
│   ┌───────────────────────────────────────────────────────┐    │
│   │              Step 4: 推荐 & 执行                       │    │
│   │                                                        │    │
│   │  • execute_cached  - 直接执行已缓存资源               │    │
│   │  • delegate_agent  - 委托给 Agent 处理                │    │
│   │  • direct_tool     - 使用内置工具                     │    │
│   │  • generate_new    - 生成新代码并缓存                 │    │
│   └───────────────────────────────────────────────────────┘    │
│       │                                                         │
│       ▼                                                         │
│   ┌───────────────────────────────────────────────────────┐    │
│   │              Step 5: 遥测记录                          │    │
│   │                                                        │    │
│   │  → orchestration_log 表                               │    │
│   └───────────────────────────────────────────────────────┘    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## 2. 核心组件

### 2.1 Intent 解析器

**动作检测:**

| Action | 关键词 |
|--------|--------|
| fetch | 获取, get, fetch, 查询, 查, 看 |
| create | 创建, create, 新建, 生成, 写 |
| modify | 修改, update, edit, 改, 更新 |
| delete | 删除, delete, 移除, remove |
| analyze | 分析, analyze, 研究, investigate |
| execute | 执行, run, 运行, 跑 |
| search | 搜索, search, 找, find |

**领域检测 (复用 TaskAnalyzer):**

| Domain | 关键词 |
|--------|--------|
| code | implement, build, 代码, 实现, 开发 |
| security | security, vulnerab, 安全, 漏洞, xss |
| research | research, analyze, 研究, 分析, paper |
| creative | design, brainstorm, 设计, 创意 |
| product | requirement, feature, 需求, 功能 |
| debug | debug, fix, bug, 修复, 报错 |
| testing | test, verify, 测试, 验证 |
| complex | complex, 分布式, 架构, 高可用, 微服务 |

### 2.2 Persona 选择器

基于 TaskProfile 计算 Affinity Score:

```typescript
AffinityScore =
    0.3 × BigFiveMatch +
    0.4 × DomainMatch +
    0.3 × CognitiveMatch
```

**Top-N 选择 + Softmax 归一化:**

```typescript
// Softmax 温度 = 1.0
expScores = topN.map(s => Math.exp(s.affinity_score / temperature))
sumExp = expScores.reduce((a, b) => a + b, 0)
normalized_weight = expScore / sumExp
```

**角色分配:**
- Primary (i=0): 主要执行人格
- Secondary (i=1...n-2): 辅助人格
- Validator (i=n-1): 验证人格

### 2.3 REE 资源匹配器

**匹配优先级:**

| 优先级 | 类型 | 延迟 | 匹配方式 |
|--------|------|------|----------|
| P1 | Shortcuts | ~50ms | trigger_phrases JSON 数组 |
| P2 | Scripts | ~100ms | intent_keywords JSON 数组 |
| P3 | Skills | ~200ms | command + keywords |
| P4 | MCP | ~500ms | 硬编码关键词映射 |

**数据库查询:**

```sql
-- Shortcuts (JOIN sys_resources)
SELECT s.shortcut_id, r.name, r.description, s.trigger_phrases
FROM sys_shortcuts s
JOIN sys_resources r ON s.shortcut_id = r.resource_id
WHERE r.status = 'active';

-- Scripts (直接查询)
SELECT script_id, name, description, intent_keywords, file_path, runtime
FROM sys_scripts
WHERE status = 'active';

-- Skills (JOIN sys_resources)
SELECT s.skill_id, r.name, s.command, r.description, r.keywords
FROM sys_skills s
JOIN sys_resources r ON s.skill_id = r.resource_id
WHERE r.status = 'active' AND s.user_invocable = TRUE;
```

### 2.4 推荐策略

```typescript
function generateRecommendation(intent, resourceMatch) {
  // 有缓存资源 → 直接执行
  if (resourceMatch) {
    return { action: 'execute_cached', ... };
  }

  // 复杂或低置信度 → 委托 Agent
  if (intent.domain === 'complex' || intent.confidence < 0.5) {
    return { action: 'delegate_to_agent', ... };
  }

  // fetch/search/analyze → 内置工具
  if (['fetch', 'search', 'analyze'].includes(intent.action)) {
    return { action: 'direct_tool', ... };
  }

  // 其他 → 生成新代码
  return { action: 'generate_new', ... };
}
```

## 3. 数据库 Schema

### 3.1 orchestration_log 表

```sql
CREATE TABLE orchestration_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_text TEXT,           -- 用户输入 (截断到500字)
    intent_action TEXT,          -- 解析的动作
    intent_domain TEXT,          -- 解析的领域
    intent_confidence REAL,      -- 置信度 0-1
    personas_selected TEXT,      -- JSON: 选择的人格ID列表
    resource_matched INTEGER,    -- 1=匹配, 0=未匹配
    resource_type TEXT,          -- shortcut/script/skill/mcp/null
    duration_ms INTEGER,         -- 编排耗时
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

## 4. 使用方式

### CLI

```bash
# 分析单个请求
bun ~/.claude/core/orchestrator/index.ts "帮我查一下北京天气"

# 输出示例
Input: 帮我查一下北京天气
────────────────────────────────────────────────────────────

📋 Intent:
   Action: fetch
   Domain: code
   Confidence: 65%

👥 Personas (Top-3):
   scientist  | Weight: 37% | Role: primary
   engineer   | Weight: 35% | Role: secondary
   pm         | Weight: 27% | Role: validator

🔍 Resource Match:
   Type: script
   Name: weather-fetch
   Confidence: 55%
   Command: bun ~/.claude/core/ree/scripts/9416537535f2.ts

💡 Recommendation:
   Action: execute_cached
   Details: Use cached script: weather-fetch
```

### TypeScript API

```typescript
import { orchestrator } from '~/.claude/core/orchestrator';

const result = await orchestrator.analyze({
  user_input: "帮我查一下北京天气",
  context: {
    session_id: "xxx",
    project: "Solar"
  }
});

// result.intent
// result.personas
// result.resource_match
// result.recommendation
```

## 5. 测试验证

| 输入 | Intent | Domain | Personas | Resource | Recommendation |
|------|--------|--------|----------|----------|----------------|
| 帮我查北京天气 | fetch | code | scientist→engineer→pm | weather-fetch | execute_cached |
| 分析代码安全漏洞 | analyze | security | reviewer→scientist→redteam | - | direct_tool |
| 搜索最近邮件 | search | code | scientist→engineer→pm | /search | execute_cached |
| 设计分布式缓存架构 | unknown | complex | scientist→reviewer→pm | - | delegate_agent |

## 6. 文件位置

```
~/.claude/core/orchestrator/
└── index.ts              # 主入口

~/Solar/core/persona/
├── evaluator.ts          # TaskAnalyzer + PersonaMatcher
└── EVALUATION_DESIGN.md  # 评估模型设计文档

~/.solar/solar.db         # 数据库
├── orchestration_log     # 编排日志
├── persona_executions    # 人格执行记录
└── persona_priors        # 贝叶斯先验
```

## 7. 后续计划

- [ ] Hook 集成: 将 Orchestrator 集成到 PreToolUse Hook
- [ ] MCP Server: 封装为 MCP 工具供外部调用
- [ ] 遥测分析: 基于 orchestration_log 优化匹配规则
- [ ] 人格权重学习: 实现完整的 Bayesian 更新闭环

---

*Unified Orchestrator Design v1.0*
*Created: 2026-02-06*
*Author: Solar*
