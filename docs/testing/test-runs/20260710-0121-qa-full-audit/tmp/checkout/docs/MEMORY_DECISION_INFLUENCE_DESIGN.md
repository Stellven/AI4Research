# Solar 记忆决策影响机制设计

> **核心问题**: 记忆如何影响决策？怎么才是对的？
> **研究日期**: 2026-02-05
> **状态**: 研究完成，待实现

## 一、问题诊断

### 当前状态 (已实现)

```
┌─────────────────────────────────────────────────────────────────┐
│                    CURRENT MEMORY LOOP                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  UserPromptSubmit → learning-capture.sh → episodic memory       │
│                                                                 │
│  PostToolUse → trajectory-db-writer.sh → evo_tool_calls         │
│                                                                 │
│  SessionEnd → session-reflect.sh → semantic memory              │
│                                                                 │
│  Daily Cron → consolidation → procedural memory                 │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 缺失的关键环节

```
┌─────────────────────────────────────────────────────────────────┐
│                    MISSING: DECISION INFLUENCE                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   Memory Storage ✓         Memory Retrieval ?                   │
│   ─────────────────        ─────────────────                    │
│   episodic    ✓            当前没有自动检索机制                  │
│   semantic    ✓            没有在决策前查询记忆                  │
│   procedural  ✓            没有基于记忆调整行为                  │
│   favorites   ✓                                                 │
│                                                                 │
│   ❌ 数据存了，但不用 = 没有价值                                 │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## 二、行业最佳实践研究

### 2.1 MemR³ (Memory Retrieval via Reflective Reasoning)

**来源**: [arXiv 2512.20237](https://arxiv.org/abs/2512.20237) (2025.12)

**核心机制**:
1. **Router (路由器)**: 在 retrieve/reflect/answer 三个动作中选择
2. **Evidence-Gap Tracker**: 追踪已收集的证据和缺失的信息

```
┌─────────────────────────────────────────────────────────────────┐
│                    MemR³ CLOSED-LOOP CONTROL                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   Query → Router → [Retrieve | Reflect | Answer]                │
│              ↑                    │                             │
│              │                    ▼                             │
│              └── Evidence-Gap Tracker                           │
│                   (知道还缺什么信息)                             │
│                                                                 │
│   效果: GPT-4.1-mini 上 RAG +7.29%, Zep +1.94%                  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Solar 启发**: 在处理用户请求前，先评估"我是否需要检索记忆？"

### 2.2 AgeMem (Agentic Memory)

**来源**: [arXiv 2601.01885](https://arxiv.org/html/2601.01885v1) (2026.01)

**核心机制**:
1. **Tool-Based Memory Interface**: 记忆操作暴露为工具调用
2. **三阶段强化学习**:
   - Stage 1: LTM 构建 (学习存什么)
   - Stage 2: STM 控制 (学习过滤噪声)
   - Stage 3: 集成推理 (协调记忆完成任务)

```
┌─────────────────────────────────────────────────────────────────┐
│                    AgeMem TOOL INTERFACE                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   LTM Tools: Add, Update, Delete                                │
│   STM Tools: Retrieve, Summary, Filter                          │
│                                                                 │
│   Agent 自主决定:                                                │
│   • 什么时候存储 (识别高价值信息)                                │
│   • 什么时候检索 (任务相关时)                                    │
│   • 什么时候更新 (信息变化时)                                    │
│   • 什么时候删除 (信息过时时)                                    │
│                                                                 │
│   复合奖励: 任务表现 + 上下文效率 + 记忆质量                     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Solar 启发**: 记忆操作应该是 Agent 的主动行为，而不是被动触发

### 2.3 A-RAG (Agentic RAG)

**来源**: [arXiv 2602.03442](https://arxiv.org/html/2602.03442) (2026.02)

**核心机制**:
1. **Hierarchical Retrieval Interface**: 三层检索工具
   - `keyword_search`: 精确匹配
   - `semantic_search`: 语义相似
   - `chunk_read`: 深度阅读
2. **Adaptive Retrieval**: 根据任务动态选择检索策略

**Solar 启发**: 不同类型的记忆需要不同的检索方式

### 2.4 Memory-R1 (Memory Distillation)

**来源**: 之前研究

**核心机制**:
1. **Memory Manager**: ADD/UPDATE/DELETE/NOOP 四操作
2. **Memory Distillation**: 检索后过滤，减少噪声

**Solar 启发**: 检索到的记忆需要过滤，不是越多越好

### 2.5 DRAGIN (Dynamic Retrieval)

**来源**: RAG 综述

**核心机制**:
- 基于熵的置信度信号触发检索
- 模型自评难度动态路由

**Solar 启发**: 只有在"不确定"时才检索记忆

## 三、Solar 记忆决策影响架构设计

### 3.1 总体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                SOLAR MEMORY-INFLUENCED DECISION                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   User Request                                                  │
│        │                                                        │
│        ▼                                                        │
│   ┌─────────────────────────────────────────────────────────┐  │
│   │         DECISION INFLUENCE LAYER (新增)                  │  │
│   │                                                         │  │
│   │  1. Intent Classification                               │  │
│   │     └── 判断请求类型和复杂度                             │  │
│   │                                                         │  │
│   │  2. Memory Need Assessment                              │  │
│   │     └── 评估是否需要检索记忆                             │  │
│   │                                                         │  │
│   │  3. Multi-Source Retrieval                              │  │
│   │     └── 从多个记忆源检索相关信息                         │  │
│   │                                                         │  │
│   │  4. Memory Distillation                                 │  │
│   │     └── 过滤噪声，保留高价值记忆                         │  │
│   │                                                         │  │
│   │  5. Context Augmentation                                │  │
│   │     └── 将记忆注入决策上下文                             │  │
│   │                                                         │  │
│   └─────────────────────────────────────────────────────────┘  │
│        │                                                        │
│        ▼                                                        │
│   LLM Decision (with memory context)                            │
│        │                                                        │
│        ▼                                                        │
│   Action Execution                                              │
│        │                                                        │
│        ▼                                                        │
│   Outcome Recording (现有)                                      │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 记忆需求评估 (Memory Need Assessment)

**触发条件矩阵**:

| 请求类型 | 需要记忆? | 检索源 | 示例 |
|----------|----------|--------|------|
| 简单操作 | 否 | - | "读取这个文件" |
| 重复任务 | 是 | procedural | "帮我提交代码" |
| 用户偏好 | 是 | favorites + semantic | "生成报告" |
| 技术决策 | 是 | semantic + episodic | "选哪个架构?" |
| 历史相关 | 是 | episodic | "上次那个bug..." |
| 规则相关 | 是 | semantic (rules) | "性能测试要求?" |

**评估算法**:

```typescript
function assessMemoryNeed(request: string): MemoryNeedResult {
  // 1. 关键词匹配 (低成本)
  if (hasTemporalReference(request)) {
    return { need: true, sources: ['episodic'], reason: 'temporal_reference' };
  }

  if (hasPreferenceIndicator(request)) {
    return { need: true, sources: ['favorites', 'semantic'], reason: 'preference' };
  }

  if (hasRepetitionIndicator(request)) {
    return { need: true, sources: ['procedural'], reason: 'repetition' };
  }

  // 2. 任务复杂度评估
  const complexity = estimateComplexity(request);
  if (complexity > COMPLEXITY_THRESHOLD) {
    return { need: true, sources: ['semantic', 'episodic'], reason: 'complex_task' };
  }

  // 3. 不确定性评估 (类似 DRAGIN)
  // 如果模型对如何处理不确定，则检索

  return { need: false, reason: 'simple_task' };
}
```

### 3.3 多源检索策略 (Multi-Source Retrieval)

```
┌─────────────────────────────────────────────────────────────────┐
│                    MULTI-SOURCE RETRIEVAL                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   Request: "帮我写个性能测试的脚本"                              │
│                                                                 │
│   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐            │
│   │  Semantic   │  │  Procedural │  │  Favorites  │            │
│   │  Memory     │  │  Memory     │  │  Memory     │            │
│   ├─────────────┤  ├─────────────┤  ├─────────────┤            │
│   │ "性能测试   │  │ "过去的测试 │  │ "用户偏好   │            │
│   │  规则和要求"│  │  脚本模式" │  │  的测试风格"│            │
│   └──────┬──────┘  └──────┬──────┘  └──────┬──────┘            │
│          │                │                │                    │
│          └────────────────┼────────────────┘                    │
│                           ▼                                     │
│                  ┌─────────────────┐                            │
│                  │ Memory Fusion   │                            │
│                  └────────┬────────┘                            │
│                           │                                     │
│                           ▼                                     │
│                  Augmented Context                              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 3.4 记忆蒸馏 (Memory Distillation)

**过滤规则**:

1. **相关性过滤**: cosine_similarity > 0.6
2. **时效性过滤**: 对于 episodic，优先最近的
3. **置信度过滤**: confidence > 0.7
4. **冲突解决**: 新记忆优先于旧记忆
5. **数量限制**: 最多 5 条最相关记忆

```typescript
function distillMemories(memories: Memory[]): Memory[] {
  return memories
    .filter(m => m.relevance > 0.6)
    .filter(m => m.confidence > 0.7)
    .sort((a, b) => {
      // 综合排序: 相关性 × 0.5 + 时效性 × 0.3 + 重要性 × 0.2
      const scoreA = a.relevance * 0.5 + a.recency * 0.3 + a.importance * 0.2;
      const scoreB = b.relevance * 0.5 + b.recency * 0.3 + b.importance * 0.2;
      return scoreB - scoreA;
    })
    .slice(0, 5);  // 最多 5 条
}
```

### 3.5 上下文增强 (Context Augmentation)

**记忆注入格式**:

```xml
<solar_memory_context>
  <semantic_rules>
    - 性能测试铁律: 修改优化器后必须运行 /benchmark tpch
    - 性能回退 >5% 必须阻止提交
  </semantic_rules>

  <procedural_patterns>
    - 过去写测试脚本时，总是先检查现有测试框架
    - 成功模式: pytest + fixtures + parametrize
  </procedural_patterns>

  <user_preferences>
    - 偏好简洁的测试代码，不要过度工程
    - 喜欢有清晰的测试输出
  </user_preferences>

  <relevant_episodes>
    - 2026-02-02: TPC-H Q14 回归事件，因为没跑性能测试
  </relevant_episodes>
</solar_memory_context>
```

## 四、实现方案

### 4.1 Phase 1: 基础检索 (最小可行)

**目标**: 在 SessionStart 时加载相关记忆

**实现**:
1. 修改 `memory-hook.ts` 的 `loadMemoriesForSession()`
2. 基于会话上下文做简单的关键词检索
3. 将检索到的记忆格式化后注入 system prompt

**预期效果**: 基本的记忆感知

### 4.2 Phase 2: 智能检索 (中期目标)

**目标**: 根据请求类型动态检索

**实现**:
1. 创建 `memory-retriever.ts` 实现多源检索
2. 创建 `memory-distiller.ts` 实现记忆过滤
3. 在 PreToolUse hook 中判断是否需要记忆增强

**预期效果**: 任务相关的精准记忆

### 4.3 Phase 3: 闭环控制 (长期目标)

**目标**: 类似 MemR³ 的闭环控制

**实现**:
1. 实现 Evidence-Gap Tracker
2. 实现 Router (retrieve/reflect/answer)
3. 基于任务结果反馈优化检索策略

**预期效果**: 自主决定何时检索、检索什么

## 五、立即可实现的改进

### 5.1 SessionStart 记忆加载增强

当前 `ontology-load.sh` 只加载固定规则，改进为:

```bash
#!/bin/bash
# ontology-load.sh (增强版)

# 1. 加载核心规则 (现有)
# ...

# 2. 加载最近学习 (新增)
RECENT_LESSONS=$(sqlite3 ~/.solar/solar.db "
SELECT key, value FROM evo_memory_semantic
WHERE namespace = 'lesson'
AND last_accessed_at > datetime('now', '-7 day')
ORDER BY confidence DESC
LIMIT 5;
")

# 3. 加载用户偏好 (新增)
PREFERENCES=$(sqlite3 ~/.solar/solar.db "
SELECT preference_key, value FROM ont_preferences
WHERE active = 1
ORDER BY weight DESC
LIMIT 10;
")

# 4. 构建增强上下文
cat << EOF
<solar_memory_loaded>
Recent Lessons:
$RECENT_LESSONS

User Preferences:
$PREFERENCES
</solar_memory_loaded>
EOF
```

### 5.2 PreToolUse 记忆检查

在执行重要工具前检查相关记忆:

```bash
#!/bin/bash
# memory-check.sh (新增 hook)

TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name')

# 只对重要操作检查
if [[ "$TOOL_NAME" == "Write" || "$TOOL_NAME" == "Edit" || "$TOOL_NAME" == "Bash" ]]; then
  FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // .tool_input.command' | head -c 100)

  # 检索相关记忆
  RELEVANT=$(sqlite3 ~/.solar/solar.db "
    SELECT key, value FROM evo_memory_semantic
    WHERE namespace = 'rule'
    AND (key LIKE '%${TOOL_NAME}%' OR value LIKE '%${FILE_PATH}%')
    LIMIT 3;
  ")

  if [[ -n "$RELEVANT" ]]; then
    echo "<memory_reminder>"
    echo "$RELEVANT"
    echo "</memory_reminder>"
  fi
fi
```

## 六、度量指标

### 6.1 记忆影响度量

| 指标 | 计算方式 | 目标 |
|------|----------|------|
| 记忆命中率 | 检索到相关记忆的比例 | >60% |
| 记忆采纳率 | 采纳记忆建议的比例 | >80% |
| 错误避免率 | 因记忆避免的错误 | 可追踪 |
| 任务效率提升 | 有记忆 vs 无记忆的完成时间 | >10% |

### 6.2 记录表

```sql
CREATE TABLE IF NOT EXISTS evo_memory_influences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    request_summary TEXT,
    memory_retrieved TEXT,          -- 检索到的记忆
    memory_adopted BOOLEAN,         -- 是否采纳
    task_outcome TEXT,              -- 任务结果
    influence_type TEXT,            -- 影响类型: avoid_error, improve_quality, speed_up
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

## 七、结论

### 正确的记忆影响决策方式

```
┌─────────────────────────────────────────────────────────────────┐
│                    THE RIGHT WAY                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   1. 不是所有决策都需要记忆 (按需检索)                           │
│   2. 记忆需要过滤，不是越多越好 (记忆蒸馏)                       │
│   3. 检索策略要匹配任务类型 (多源检索)                           │
│   4. 记忆影响要可追溯 (度量记录)                                 │
│   5. 闭环反馈优化检索质量 (持续学习)                             │
│                                                                 │
│   核心原则:                                                      │
│   • 相关性 > 数量                                                │
│   • 精准 > 全面                                                  │
│   • 可验证 > 感觉好                                              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 下一步行动

1. **立即**: 增强 SessionStart 记忆加载
2. **短期**: 实现 PreToolUse 记忆检查
3. **中期**: 实现完整的 Memory Retriever + Distiller
4. **长期**: 实现闭环控制和自动优化

---

## 参考文献

1. [MemR³: Memory Retrieval via Reflective Reasoning](https://arxiv.org/abs/2512.20237)
2. [AgeMem: Agentic Memory for LLM Agents](https://arxiv.org/html/2601.01885v1)
3. [A-RAG: Scaling Agentic Retrieval-Augmented Generation](https://arxiv.org/html/2602.03442)
4. [A-MEM: Agentic Memory for LLM Agents](https://arxiv.org/abs/2502.12110)
5. [ICLR 2026 Workshop: MemAgents](https://openreview.net/pdf?id=U51WxL382H)
6. [RAG Comprehensive Survey](https://arxiv.org/abs/2410.12837)

---

*Solar Memory Decision Influence Design v1.0*
*研究日期: 2026-02-05*
*状态: 研究完成，待实现*
