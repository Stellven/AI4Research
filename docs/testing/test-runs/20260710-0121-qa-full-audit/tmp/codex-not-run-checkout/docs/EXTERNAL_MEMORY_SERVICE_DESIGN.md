# 外置记忆服务设计 (External Memory Service)

> **目标**: 把 Solar 从"依赖对话上下文"升级到"事件溯源+状态编译"
> **设计日期**: 2026-02-09
> **状态**: Draft v1.1 (专家审核后修订)
> **审核专家**: 技术宅(Gemini 2.5 Pro), 千里马(Gemini 3 Pro), 思考驼(DeepSeek R1)

## 专家审核意见摘要

### 可行性评分: 7.5/10 (千里马)

### 关键问题 (必须解决)

1. **事件版本管理** (技术宅): 事件 schema 演进会破坏旧数据兼容性
2. **快照机制缺失** (技术宅): 每次从头编译状态会导致性能下降
3. **State Compiler 过于复杂** (千里马): 4周内难以实现完整编译器
4. **隐性假设风险** (思考驼): 事件边界模糊、状态可编译性存疑

### 采纳的建议

1. ✅ 简化 MVP: 只做 Layer 1 + Lite Layer 3
2. ✅ 增加快照机制
3. ✅ 事件增加版本号字段
4. ✅ 增加人工干预接口 (手动修改 STATE.md)
5. ✅ 编译器输出置信度标注
6. ⏳ Meta-Memory Layer (后续迭代)

## 核心架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        EXTERNAL MEMORY SERVICE                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐         │
│  │  Event Source   │───▶│  Vector Index   │───▶│ State Compiler  │         │
│  │    Layer        │    │    Layer        │    │                 │         │
│  └────────┬────────┘    └────────┬────────┘    └────────┬────────┘         │
│           │                      │                      │                   │
│           ▼                      ▼                      ▼                   │
│  ┌─────────────────────────────────────────────────────────────────┐       │
│  │                     Proof Obligations                           │       │
│  │                   (约束硬校验层)                                 │       │
│  └─────────────────────────────────────────────────────────────────┘       │
│           │                      │                      │                   │
│           ▼                      ▼                      ▼                   │
│  ┌─────────────────────────────────────────────────────────────────┐       │
│  │                      OUTPUT TARGETS                              │       │
│  │  ┌─────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐ │       │
│  │  │STATE.md │  │Prompt Inject│  │ sys_favorites│  │ Checkpoint  │ │       │
│  │  └─────────┘  └─────────────┘  └─────────────┘  └─────────────┘ │       │
│  └─────────────────────────────────────────────────────────────────┘       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 现有机制融合

### 现有数据资产

| 表 | 数据量 | 用途 | 融合方向 |
|----|--------|------|----------|
| `tel_operations` | 37,454 | 工具调用记录 | → Event Source |
| `evo_feedback_v2` | 1,692 | 用户反馈 | → Event Source |
| `sroe_requests` | 598 | 路由决策 | → Event Source |
| `evo_memory_semantic` | 119 | 语义记忆 | → Vector Index |
| `sys_favorites` | 62 | 高价值输出 | → State Compiler |
| `evo_traces` | - | 执行追踪 | → Event Source |
| `evo_baselines` | - | 性能基线 | → Proof Obligations |

### 现有机制映射

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  现有机制                          融合到                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Cortex (数据账本)              →  Event Source + Indexer                   │
│  sys_favorites                  →  State Compiler 输入                      │
│  evo_memory_semantic            →  Vector Index 基础                        │
│  STATE.md                       →  State Compiler 输出                      │
│  evo_baselines                  →  Proof Obligations                        │
│  Hook (PeriodicCheck/SessionEnd)→  Event Capture 触发器                     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Layer 1: Event Sourcing

### 统一事件格式

```sql
CREATE TABLE mem_events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,      -- 'tool_call' | 'output' | 'decision' | 'feedback' | 'checkpoint'
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,

    -- 版本管理 (技术宅建议)
    schema_version INTEGER DEFAULT 1,  -- 事件 schema 版本，用于向后兼容

    -- 上下文
    session_id TEXT,
    task_id TEXT,
    module TEXT,                   -- 任务模块 (e.g., 'state-persistence', 'brain-router')

    -- 事件内容
    command TEXT,                  -- 工具/命令名
    input_summary TEXT,            -- 输入摘要 (压缩)
    output_summary TEXT,           -- 输出摘要 (压缩)
    diff_summary TEXT,             -- 变更摘要 (文件diff)

    -- 指标
    metrics JSON,                  -- {duration_ms, tokens_in, tokens_out, success, error_code}

    -- 向量
    embedding BLOB,                -- 事件嵌入 (用于语义检索)

    -- 溯源
    parent_event_id TEXT,          -- 因果链

    FOREIGN KEY (parent_event_id) REFERENCES mem_events(event_id)
);

-- Schema 迁移记录
CREATE TABLE mem_schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    description TEXT
);

-- 索引
CREATE INDEX idx_mem_events_type ON mem_events(event_type);
CREATE INDEX idx_mem_events_module ON mem_events(module);
CREATE INDEX idx_mem_events_session ON mem_events(session_id);
CREATE INDEX idx_mem_events_time ON mem_events(timestamp);
```

### 事件采集器

```typescript
// ~/.claude/core/memory-service/event-collector.ts

interface MemEvent {
  event_type: 'tool_call' | 'output' | 'decision' | 'feedback' | 'checkpoint';
  session_id: string;
  task_id?: string;
  module?: string;
  command?: string;
  input_summary?: string;
  output_summary?: string;
  diff_summary?: string;
  metrics?: {
    duration_ms: number;
    tokens_in?: number;
    tokens_out?: number;
    success: boolean;
    error_code?: string;
  };
  parent_event_id?: string;
}

class EventCollector {
  // 从现有表同步
  async syncFromTelOperations(since: Date): Promise<number>;
  async syncFromSroeRequests(since: Date): Promise<number>;
  async syncFromFeedback(since: Date): Promise<number>;

  // 实时采集
  async captureToolCall(tool: string, input: any, output: any, metrics: any): Promise<string>;
  async captureDecision(decision: string, reason: string, context: any): Promise<string>;
  async captureCheckpoint(state: any): Promise<string>;
}
```

### 摘要压缩

```typescript
// 大输出自动压缩成摘要
function summarizeOutput(output: string, maxLen: number = 500): string {
  if (output.length <= maxLen) return output;

  // 优先保留:
  // 1. 错误信息
  // 2. 关键指标 (数字)
  // 3. 文件路径
  // 4. 命令输出首尾

  return compressWithPriority(output, maxLen);
}

// Diff 摘要
function summarizeDiff(diff: string): string {
  // +N lines, -M lines, files: [...]
  return extractDiffStats(diff);
}
```

---

## Layer 2: Vector Index

### 多维度索引

```sql
CREATE TABLE mem_index (
    index_id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL,

    -- 索引维度
    dimension TEXT NOT NULL,       -- 'task' | 'module' | 'file' | 'error' | 'metric'
    dimension_value TEXT NOT NULL, -- 具体值

    -- 嵌入
    embedding BLOB,

    -- 元数据
    relevance_score REAL,          -- 相关性分数 (用于排序)

    FOREIGN KEY (event_id) REFERENCES mem_events(event_id)
);

CREATE INDEX idx_mem_index_dimension ON mem_index(dimension, dimension_value);
```

### 检索接口

```typescript
// ~/.claude/core/memory-service/retriever.ts

interface RetrievalQuery {
  // 精确匹配
  task_id?: string;
  module?: string;
  file_path?: string;
  error_code?: string;

  // 语义搜索
  semantic_query?: string;

  // 时间范围
  since?: Date;
  until?: Date;

  // 限制
  limit?: number;
  min_relevance?: number;
}

class MemoryRetriever {
  // 检索相关历史
  async retrieve(query: RetrievalQuery): Promise<MemEvent[]>;

  // 按任务检索完整链路
  async getTaskHistory(task_id: string): Promise<MemEvent[]>;

  // 按错误码检索类似问题
  async getSimilarErrors(error_code: string): Promise<MemEvent[]>;

  // 按文件检索变更历史
  async getFileHistory(file_path: string): Promise<MemEvent[]>;

  // 语义检索
  async semanticSearch(query: string, limit: number): Promise<MemEvent[]>;
}
```

### 与 Tantivy 集成

```typescript
// 复用现有 Tantivy 索引
import { SolarSearch } from '~/Solar/core/search';

class HybridRetriever extends MemoryRetriever {
  private tantivy: SolarSearch;

  // 混合检索: 向量 + 全文
  async hybridSearch(query: string): Promise<MemEvent[]> {
    const [vectorResults, ftsResults] = await Promise.all([
      this.semanticSearch(query, 20),
      this.tantivy.search(query, 20)
    ]);

    return this.mergeAndRank(vectorResults, ftsResults);
  }
}
```

---

## 快照机制 (技术宅建议)

> **问题**: 每次从头编译状态会导致性能下降
> **解决**: 定期保存状态快照，只从最近快照开始重放

### 快照表设计

```sql
CREATE TABLE mem_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    -- 快照时的状态
    state_json JSON NOT NULL,         -- CompiledState 的 JSON 序列化

    -- 边界信息
    last_event_id TEXT NOT NULL,      -- 快照包含的最后一个事件
    last_event_time DATETIME NOT NULL,

    -- 元数据
    event_count INTEGER,              -- 快照覆盖的事件数量
    compression_ratio REAL,           -- 压缩比 (事件数/状态大小)

    FOREIGN KEY (last_event_id) REFERENCES mem_events(event_id)
);

CREATE INDEX idx_snapshots_time ON mem_snapshots(created_at);
```

### 快照策略

```typescript
// 快照触发条件 (满足任一即触发)
const SNAPSHOT_POLICY = {
  max_events_since_last: 100,    // 超过100个新事件
  max_time_since_last: 4 * 3600, // 超过4小时
  on_session_end: true,          // 会话结束时
  on_explicit_save: true         // 用户主动 /save 时
};

class SnapshotManager {
  async shouldCreateSnapshot(): Promise<boolean>;
  async createSnapshot(state: CompiledState, lastEventId: string): Promise<string>;
  async loadLatestSnapshot(): Promise<{snapshot: Snapshot, newEvents: MemEvent[]}>;
}
```

### 增量编译

```typescript
// 不从头编译，从快照开始
async compileState(): Promise<CompiledState> {
  const { snapshot, newEvents } = await this.snapshots.loadLatestSnapshot();

  if (newEvents.length === 0) {
    return snapshot.state;
  }

  // 只处理快照之后的新事件
  return this.applyEvents(snapshot.state, newEvents);
}
```

---

## Layer 3: State Compiler

### 状态编译流程

```
事件流 (mem_events)
    │
    ▼
┌─────────────────┐
│ Event Filter    │  ← 按 session/task/module 过滤
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Event Reducer   │  ← 聚合相关事件
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ State Synthesizer│  ← 合成当前状态
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Output Formatter│  ← 格式化输出
└────────┬────────┘
         │
    ┌────┴────┬─────────────┬─────────────┐
    ▼         ▼             ▼             ▼
STATE.md   Prompt      sys_favorites   Checkpoint
```

### 状态编译器实现

```typescript
// ~/.claude/core/memory-service/state-compiler.ts

interface CompiledState {
  mission: string;
  constraints: string[];
  decisions: Decision[];
  progress: {
    done: string[];
    in_progress: string[];
    blocked: string[];
  };
  next_actions: Action[];

  // 上下文
  relevant_history: MemEvent[];
  active_warnings: string[];

  // 置信度标注 (思考驼建议)
  confidence: {
    overall: number;           // 0-1, 整体置信度
    mission: number;           // Mission 推断置信度
    progress: number;          // Progress 推断置信度
    next_actions: number;      // Next Actions 推断置信度
    low_confidence_fields: string[];  // 置信度<0.6的字段
  };

  // 编译元数据
  compiled_at: Date;
  events_processed: number;
  from_snapshot: boolean;
}

class StateCompiler {
  private retriever: MemoryRetriever;

  // 从事件流编译状态
  async compile(context: {
    session_id?: string;
    task_id?: string;
    module?: string;
    lookback_hours?: number;
  }): Promise<CompiledState> {

    // 1. 获取相关事件
    const events = await this.retriever.retrieve({
      session_id: context.session_id,
      task_id: context.task_id,
      module: context.module,
      since: new Date(Date.now() - (context.lookback_hours || 24) * 3600 * 1000)
    });

    // 2. 提取决策
    const decisions = this.extractDecisions(events);

    // 3. 计算进度
    const progress = this.computeProgress(events);

    // 4. 推断下一步
    const next_actions = this.inferNextActions(events, progress);

    // 5. 检测警告
    const warnings = await this.checkProofObligations(events);

    return {
      mission: this.extractMission(events),
      constraints: this.extractConstraints(events),
      decisions,
      progress,
      next_actions,
      relevant_history: events.slice(0, 10),
      active_warnings: warnings
    };
  }

  // 输出到 STATE.md
  async writeToStateMd(state: CompiledState): Promise<void>;

  // 注入到 Prompt
  formatForPrompt(state: CompiledState): string;
}
```

### 增量更新

```typescript
// 只更新变化的部分，不重写全文
async updateStateMd(newState: CompiledState): Promise<void> {
  const current = await this.parseStateMd();
  const diff = this.computeDiff(current, newState);

  if (diff.decisions.added.length > 0) {
    await this.appendDecisions(diff.decisions.added);
  }

  if (diff.progress.changed) {
    await this.updateProgress(newState.progress);
  }

  if (diff.next_actions.changed) {
    await this.updateNextActions(newState.next_actions);
  }
}
```

### 人工干预接口 (千里马建议)

> **问题**: 编译器可能出错，需要人工覆盖
> **解决**: STATE.md 手动修改优先于编译器推断

```typescript
// 人工干预优先级: 手动 > 编译器
class HumanOverrideManager {
  // 检测 STATE.md 是否有手动修改
  async detectManualChanges(lastCompiled: Date): Promise<ManualChanges | null>;

  // 合并: 保留手动修改，只更新未手动修改的部分
  async mergeWithManual(compiled: CompiledState): Promise<CompiledState>;
}

// 合并策略
const MERGE_STRATEGY = {
  // 这些字段如果被手动修改，永远保留手动版本
  preserve_manual: ['mission', 'constraints'],

  // 这些字段智能合并
  smart_merge: ['progress', 'decisions'],

  // 这些字段总是用编译器版本
  always_compile: ['relevant_history', 'active_warnings']
};
```

### 置信度告警

```typescript
// 低置信度时主动询问
async compileWithFeedback(): Promise<CompiledState> {
  const state = await this.compile();

  if (state.confidence.overall < 0.6) {
    // 输出告警，请求人工确认
    console.log(`
    ┌─ ⚠️ 状态编译置信度低 ─────────────────────┐
    │ 整体置信度: ${(state.confidence.overall * 100).toFixed(0)}%
    │ 低置信度字段: ${state.confidence.low_confidence_fields.join(', ')}
    │
    │ 建议: 手动检查 STATE.md 并修正
    └──────────────────────────────────────────┘
    `);
  }

  return state;
}
```

---

## Layer 4: Proof Obligations

### 约束定义

```sql
CREATE TABLE mem_proof_obligations (
    obligation_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,        -- 'performance' | 'memory' | 'api' | 'security'

    -- 约束条件
    condition_type TEXT NOT NULL,  -- 'threshold' | 'pattern' | 'invariant'
    condition_spec JSON NOT NULL,  -- 具体条件

    -- 检查配置
    check_frequency TEXT,          -- 'on_event' | 'periodic' | 'on_compile'
    severity TEXT,                 -- 'error' | 'warning' | 'info'

    -- 状态
    enabled BOOLEAN DEFAULT true,
    last_checked DATETIME,
    last_result TEXT               -- 'pass' | 'fail' | 'skip'
);

-- 预置约束
INSERT INTO mem_proof_obligations VALUES
  ('perf-p99', 'P99 延迟阈值', 'performance', 'threshold',
   '{"metric": "duration_p99", "max_ms": 5000}', 'on_compile', 'error', true, NULL, NULL),

  ('mem-usage', '内存使用阈值', 'memory', 'threshold',
   '{"metric": "memory_mb", "max_mb": 1024}', 'periodic', 'warning', true, NULL, NULL),

  ('api-compat', 'API 兼容性', 'api', 'invariant',
   '{"check": "no_breaking_changes", "baseline": "v1.0"}', 'on_event', 'error', true, NULL, NULL),

  ('regression', '性能回退检测', 'performance', 'pattern',
   '{"check": "no_regression", "threshold_pct": 5}', 'on_compile', 'error', true, NULL, NULL);
```

### 校验器实现

```typescript
// ~/.claude/core/memory-service/proof-checker.ts

interface ProofResult {
  obligation_id: string;
  passed: boolean;
  message: string;
  evidence?: any;
}

class ProofChecker {
  // 检查单个约束
  async check(obligation_id: string, events: MemEvent[]): Promise<ProofResult>;

  // 检查所有约束
  async checkAll(events: MemEvent[]): Promise<ProofResult[]>;

  // 预置检查器
  private checkers: {
    // P99 检查
    checkP99Threshold(events: MemEvent[], spec: any): ProofResult;

    // 内存检查
    checkMemoryUsage(spec: any): ProofResult;

    // 回退检查
    checkNoRegression(events: MemEvent[], spec: any): ProofResult;

    // API 兼容检查
    checkApiCompatibility(events: MemEvent[], spec: any): ProofResult;
  };
}
```

### 与现有 Baseline 集成

```typescript
// 复用 evo_baselines
async checkNoRegression(events: MemEvent[]): Promise<ProofResult> {
  const baseline = await db.get(`
    SELECT * FROM evo_baselines
    WHERE name = 'tpch_performance'
    ORDER BY created_at DESC LIMIT 1
  `);

  const current = this.extractMetrics(events);

  const regression = this.compareWithBaseline(current, baseline);

  if (regression.pct > 5) {
    return {
      obligation_id: 'regression',
      passed: false,
      message: `性能回退 ${regression.pct}% (阈值 5%)`,
      evidence: { baseline, current, regression }
    };
  }

  return { obligation_id: 'regression', passed: true, message: 'OK' };
}
```

---

## 集成入口

### 统一服务接口

```typescript
// ~/.claude/core/memory-service/index.ts

export class ExternalMemoryService {
  private collector: EventCollector;
  private retriever: MemoryRetriever;
  private compiler: StateCompiler;
  private checker: ProofChecker;

  // 初始化 (SessionStart 调用)
  async initialize(session_id: string): Promise<void>;

  // 事件采集 (Hook 调用)
  async captureEvent(event: MemEvent): Promise<void>;

  // 状态编译 (定时/checkpoint 调用)
  async compileState(): Promise<CompiledState>;

  // 约束校验
  async checkObligations(): Promise<ProofResult[]>;

  // 检索历史
  async retrieve(query: RetrievalQuery): Promise<MemEvent[]>;

  // 一键恢复 (新会话启动)
  async restore(): Promise<{
    state: CompiledState;
    prompt_injection: string;
  }>;
}

// CLI 入口
// bun ~/.claude/core/memory-service/index.ts compile
// bun ~/.claude/core/memory-service/index.ts retrieve --module state-persistence
// bun ~/.claude/core/memory-service/index.ts check-proofs
```

### Hook 集成

```bash
# ~/.claude/hooks/memory-capture.sh
# PostToolUse 时采集事件

bun ~/.claude/core/memory-service/index.ts capture \
  --type tool_call \
  --command "$TOOL_NAME" \
  --input "$TOOL_INPUT" \
  --output "$TOOL_OUTPUT" \
  --success "$TOOL_SUCCESS"
```

```bash
# ~/.claude/hooks/state-compile.sh
# PeriodicCheck 时编译状态

bun ~/.claude/core/memory-service/index.ts compile --write-state-md
```

---

## 实现路线 (千里马建议: MVP 优先)

> **核心洞察**: 4周全量实现风险太高，应先跑通最小闭环

### MVP Phase (Week 1-2): 先跑通闭环

**目标**: 实现 "写入事件 → 更新 STATE.md" 的闭环

**Week 1: Layer 1 - Event Sourcing**
- [ ] 创建 mem_events 表 (含 schema_version)
- [ ] 实现简化版 EventCollector (只支持 tool_call/checkpoint)
- [ ] PostToolUse Hook 集成
- [ ] 验证: 工具调用自动写入 mem_events

**Week 2: Layer 3 Lite - Simple State Updater**
- [ ] 实现最简 StateUpdater (非完整 Compiler)
  - 不推断 Mission (从 STATE.md 读取)
  - 只更新 Progress (基于 checkpoint 事件)
  - 只更新 Next Actions (基于最近事件)
- [ ] PeriodicCheck 集成 (5分钟触发)
- [ ] 验证: 事件自动同步到 STATE.md

```typescript
// MVP: 简化版 State Updater
class LiteStateUpdater {
  async update(): Promise<void> {
    // 1. 读取当前 STATE.md (Mission/Constraints 不动)
    const current = await this.readStateMd();

    // 2. 获取最近事件
    const events = await this.getRecentEvents(30); // 最近30分钟

    // 3. 只更新 Progress 和 Next Actions
    current.progress = this.extractProgress(events);
    current.next_actions = this.inferNextActions(events);

    // 4. 写回
    await this.writeStateMd(current);
  }
}
```

### Phase 2 (Week 3-4): 完善功能

**Week 3: 快照 + 检索**
- [ ] 实现 mem_snapshots 表
- [ ] 快照创建/加载
- [ ] 基础检索 (按 module/session)

**Week 4: 置信度 + 告警**
- [ ] 置信度计算
- [ ] 低置信度告警
- [ ] 人工覆盖检测

### Phase 3 (后续迭代): 高级功能

**Future: Vector Index**
- [ ] 语义嵌入
- [ ] 与 Tantivy 混合检索
- [ ] 相似错误检索

**Future: Proof Obligations**
- [ ] 约束定义表
- [ ] 性能回退检测
- [ ] 与 evo_baselines 集成

**Future: Meta-Memory (思考驼建议)**
- [ ] 记忆系统自我评估
- [ ] 渐进抽象机制
- [ ] 记忆"消化"周期

---

## 与 Anthropic 最佳实践对齐

参考 Anthropic Cookbook 的 Agent Pattern:

1. **会话记忆压缩** → State Compiler 的摘要能力
2. **长会话管理** → Event Sourcing + 增量状态
3. **工具结果缓存** → mem_events 存储
4. **上下文优化** → Proof Obligations 约束

---

*External Memory Service Design v1.0*
*设计日期: 2026-02-09*
*状态: Draft - 待专家团队审核*
