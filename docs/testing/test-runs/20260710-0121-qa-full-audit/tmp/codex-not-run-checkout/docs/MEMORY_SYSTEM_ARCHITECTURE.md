# Solar 记忆系统架构设计

> **版本**: v2.0
> **日期**: 2026-02-05
> **作者**: Solar
> **状态**: 已实现

## 1. 架构概览

### 1.1 设计哲学

```
"记忆不是存起来就完了，必须用起来才有价值"
```

Solar 记忆系统的核心理念是**闭环**：输入 → 存储 → 影响决策 → 产生行为 → 记录 → 存储（循环）。

### 1.2 系统全景图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        SOLAR MEMORY SYSTEM v2.0                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                        Layer 4: 闭环集成                             │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                  │   │
│  │  │SessionStart │  │PreToolUse   │  │PostToolUse  │                  │   │
│  │  │ 加载记忆    │  │ 经验提醒    │  │ 记录使用    │                  │   │
│  │  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘                  │   │
│  └─────────┼────────────────┼────────────────┼──────────────────────────┘   │
│            │                │                │                              │
│  ┌─────────┼────────────────┼────────────────┼──────────────────────────┐   │
│  │         │       Layer 3: 核心服务         │                          │   │
│  │         ▼                ▼                ▼                          │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                  │   │
│  │  │memory-hook  │  │hybrid-search│  │procedural-  │                  │   │
│  │  │   .ts       │  │   .ts       │  │ tracker.ts  │                  │   │
│  │  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘                  │   │
│  │         │                │                │                          │   │
│  │  ┌──────┴──────┐  ┌──────┴──────┐  ┌──────┴──────┐                  │   │
│  │  │episodic-    │  │memory-      │  │proficiency- │                  │   │
│  │  │ writer.ts   │  │ embedder.ts │  │ v2.ts       │                  │   │
│  │  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘                  │   │
│  │         │                │                │                          │   │
│  │  ┌──────┴──────┐  ┌──────┴──────┐  ┌──────┴──────┐                  │   │
│  │  │consolidation│  │memory-      │  │(研究模型)   │                  │   │
│  │  │ -engine.ts  │  │ linker.ts   │  │Dreyfus/SM-2 │                  │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘                  │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                        Layer 2: 数据存储                              │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐ │   │
│  │  │evo_memory_  │  │evo_memory_  │  │evo_memory_  │  │sys_favorites│ │   │
│  │  │  episodic   │  │  semantic   │  │ procedural  │  │  (高价值)   │ │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘ │   │
│  │        ↓                ↓                ↓                ↓         │   │
│  │  ┌─────────────────────────────────────────────────────────────────┐│   │
│  │  │                    evo_memory_links (图结构)                     ││   │
│  │  └─────────────────────────────────────────────────────────────────┘│   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                        Layer 1: 基础设施                              │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                  │   │
│  │  │  SQLite     │  │  向量索引   │  │  Tantivy    │                  │   │
│  │  │  (solar.db) │  │  (256维)    │  │  (全文搜索) │                  │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘                  │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 2. 四层记忆模型

### 2.1 记忆类型对比

| 记忆类型 | 存储表 | 内容 | 特点 | 权重 |
|---------|--------|------|------|------|
| **情景记忆** | evo_memory_episodic | 事件、会话、任务 | 时间线、可回溯 | 0.3 |
| **语义记忆** | evo_memory_semantic | 知识、规则、教训 | 结构化、高置信度 | 0.3 |
| **程序记忆** | evo_memory_procedural | 技能、工具使用 | 熟练度、统计 | 0.1 |
| **高价值收藏** | sys_favorites | 监护人指定 | 最高优先级 | 0.3 |

### 2.2 数据模型

#### 2.2.1 情景记忆 (Episodic)

```sql
CREATE TABLE evo_memory_episodic (
    memory_id TEXT PRIMARY KEY,
    namespace TEXT NOT NULL,           -- 分类命名空间
    event_type TEXT NOT NULL,          -- 事件类型
    event_summary TEXT NOT NULL,       -- 事件摘要
    event_details JSON,                -- 详细信息
    session_id TEXT,                   -- 会话关联
    trace_id TEXT,                     -- 追踪ID
    related_files JSON,                -- 相关文件
    related_resources JSON,            -- 相关资源
    importance REAL DEFAULT 0.5,       -- 重要性 0-10
    sentiment TEXT,                    -- 情感倾向
    outcome TEXT,                      -- 结果
    embedding BLOB,                    -- 向量嵌入 (256维)
    occurred_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_recalled_at DATETIME,         -- 最后回忆时间
    recall_count INTEGER DEFAULT 0,    -- 回忆次数
    decay_rate REAL DEFAULT 0.01,      -- 衰减率
    consolidated BOOLEAN DEFAULT 0     -- 是否已固化
);
```

#### 2.2.2 语义记忆 (Semantic)

```sql
CREATE TABLE evo_memory_semantic (
    memory_id TEXT PRIMARY KEY,
    namespace TEXT NOT NULL,           -- rule/lesson/wisdom/knowledge
    key TEXT NOT NULL,                 -- 知识键
    value JSON NOT NULL,               -- 知识值
    embedding BLOB,                    -- 向量嵌入
    source_type TEXT,                  -- 来源类型
    source_trace_id TEXT,              -- 来源追踪
    confidence REAL DEFAULT 1.0,       -- 置信度 0-1
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_accessed_at DATETIME,
    access_count INTEGER DEFAULT 0,
    ttl_seconds INTEGER                -- 过期时间
);
```

#### 2.2.3 程序记忆 (Procedural)

```sql
CREATE TABLE evo_memory_procedural (
    memory_id TEXT PRIMARY KEY,
    namespace TEXT NOT NULL,           -- procedural/skill/tool/agent
    procedure_name TEXT NOT NULL,      -- 技能名称
    procedure_type TEXT NOT NULL,      -- skill/tool/agent/script/mcp
    description TEXT,                  -- 描述
    trigger_conditions JSON,           -- 触发条件
    trigger_keywords JSON,             -- 触发关键词
    steps JSON,                        -- 执行步骤
    execution_count INTEGER DEFAULT 0, -- 执行次数
    success_count INTEGER DEFAULT 0,   -- 成功次数
    avg_duration_seconds REAL,         -- 平均耗时
    last_executed_at DATETIME,         -- 最后执行时间
    embedding BLOB,                    -- 向量嵌入
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

#### 2.2.4 记忆链接 (Links)

```sql
CREATE TABLE evo_memory_links (
    link_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,           -- 源记忆ID
    target_id TEXT NOT NULL,           -- 目标记忆ID
    link_type TEXT NOT NULL,           -- 链接类型
    strength REAL DEFAULT 0.5,         -- 链接强度 0-1
    context TEXT,                      -- 链接上下文
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_traversed_at DATETIME,
    traversal_count INTEGER DEFAULT 0
);
```

## 3. 核心组件

### 3.1 组件清单

| 文件 | 职责 | 依赖 |
|------|------|------|
| `memory-hook.ts` | 闭环核心：加载/记录/查询 | hybrid-search, procedural-tracker |
| `episodic-writer.ts` | 情景记忆写入 | memory-embedder |
| `consolidation-engine.ts` | 记忆固化：短期→长期 | memory-linker |
| `memory-embedder.ts` | 向量嵌入服务 (256维 TF-IDF) | - |
| `memory-linker.ts` | 记忆链接：图结构 | memory-embedder |
| `hybrid-search.ts` | 混合搜索：关键词+语义+图 | memory-embedder, memory-linker |
| `procedural-tracker.ts` | 程序记忆追踪 | memory-embedder |
| `proficiency-v2.ts` | 熟练度评估 (基于业界研究) | - |

### 3.2 核心流程

#### 3.2.1 记忆写入流程

```
输入事件
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ episodic-writer.ts                                          │
│   1. 解析事件类型                                            │
│   2. 生成向量嵌入 (memory-embedder)                         │
│   3. 写入 evo_memory_episodic                               │
│   4. 创建初始链接 (memory-linker)                           │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ consolidation-engine.ts (定期运行)                          │
│   1. 扫描 importance >= 7 的情景记忆                        │
│   2. 提取为语义记忆 (规则/教训)                             │
│   3. 更新记忆链接强度                                        │
│   4. 标记已固化                                             │
└─────────────────────────────────────────────────────────────┘
```

#### 3.2.2 记忆检索流程

```
查询请求
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ hybrid-search.ts                                            │
│                                                             │
│   并行执行三种搜索:                                          │
│   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│   │ 关键词搜索  │  │ 语义搜索   │  │ 收藏搜索   │        │
│   │ (Tantivy)   │  │ (向量)     │  │ (favorites) │        │
│   │ 权重: 0.3   │  │ 权重: 0.3  │  │ 权重: 0.3  │        │
│   └──────┬──────┘  └──────┬──────┘  └──────┬──────┘        │
│          │                │                │                │
│          └────────────────┼────────────────┘                │
│                           ▼                                  │
│                    分数合并与排序                            │
│                           │                                  │
│                           ▼                                  │
│                    图扩展 (可选)                             │
│                    权重: 0.1                                 │
│                           │                                  │
│                           ▼                                  │
│                    返回 Top-K 结果                           │
└─────────────────────────────────────────────────────────────┘
```

### 3.3 熟练度评估模型 (v2)

基于业界研究设计，非闭门造车：

| 模型/算法 | 来源 | 用途 |
|----------|------|------|
| **Dreyfus 模型** | Dreyfus & Dreyfus (1980) | 5阶段技能习得 |
| **Ebbinghaus 遗忘曲线** | Ebbinghaus (1885) | 记忆衰减: R = e^(-t/S) |
| **SM-2 算法** | SuperMemo (1987) | 间隔重复调度 |
| **贝叶斯估计** | SEBN (2025) | 置信区间计算 |

```typescript
// Dreyfus 五阶段
type DreyfusStage =
  | 'novice'           // 新手: <10次, <50%成功率
  | 'advanced_beginner' // 高级初学者: 10-30次
  | 'competent'         // 胜任: 30-100次, >70%成功率
  | 'proficient'        // 精通: 100-300次, >85%成功率
  | 'expert';           // 专家: >300次, >95%成功率

// 记忆保持率 (Ebbinghaus)
function calculateRetention(daysSince: number, stability: number): number {
  return Math.exp(-daysSince / stability);
}

// 贝叶斯熟练度估计
function bayesianProficiency(successes: number, failures: number): {
  mean: number;      // 期望值
  lower95: number;   // 95%置信下界
  upper95: number;   // 95%置信上界
}
```

## 4. 闭环集成

### 4.1 Hook 配置

```json
{
  "hooks": {
    "UserPromptSubmit": ["~/.claude/hooks/learning-capture.sh"],
    "PreToolUse:Write": ["~/.claude/hooks/experience-reminder.sh"],
    "PreToolUse:Edit": ["~/.claude/hooks/experience-reminder.sh"],
    "PostToolUse:Write": ["~/.claude/hooks/solar-post-tool.sh"],
    "PostToolUse:Edit": ["~/.claude/hooks/solar-post-tool.sh"],
    "PostToolUse:Read": ["~/.claude/hooks/solar-post-tool.sh"],
    "PostToolUse:Bash": ["~/.claude/hooks/solar-post-tool.sh"],
    "PostToolUse:Grep": ["~/.claude/hooks/solar-post-tool.sh"],
    "PostToolUse:Glob": ["~/.claude/hooks/solar-post-tool.sh"],
    "PostToolUse:Task": ["~/.claude/hooks/solar-post-tool.sh"],
    "SessionStart": ["~/.claude/hooks/solar-session-start.sh"],
    "SessionEnd": ["~/.claude/hooks/session-reflect.sh"]
  }
}
```

### 4.2 闭环数据流

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           MEMORY CLOSED LOOP                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  会话开始 (SessionStart)                                                    │
│      │                                                                      │
│      ▼                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ solar-session-start.sh                                               │   │
│  │   └─ bun memory-hook.ts load "$PROJECT_CONTEXT"                     │   │
│  │      • 加载最近情景记忆 (24小时内, importance >= 5)                  │   │
│  │      • 加载高价值语义知识 (confidence >= 0.8)                        │   │
│  │      • 推荐技能 (基于使用频率)                                       │   │
│  │      • 警告低成功率技能                                              │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│      │                                                                      │
│      ▼                                                                      │
│  用户请求任务                                                               │
│      │                                                                      │
│      ▼                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ experience-reminder.sh (PreToolUse:Write/Edit, 首次触发)             │   │
│  │   └─ bun memory-hook.ts query "$CONTEXT"                            │   │
│  │      • 查询相关铁律                                                  │   │
│  │      • 查询历史教训                                                  │   │
│  │      • 输出提醒消息                                                  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│      │                                                                      │
│      ▼                                                                      │
│  执行工具 (Read/Write/Edit/Bash/Grep/Glob/Task)                            │
│      │                                                                      │
│      ▼                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ solar-post-tool.sh (PostToolUse)                                     │   │
│  │   └─ memory-record.sh "$TOOL_NAME" "$SUCCESS"                       │   │
│  │      └─ bun memory-hook.ts record "$TOOL_NAME" "$SUCCESS"           │   │
│  │         • 更新 evo_memory_procedural                                 │   │
│  │         • execution_count++                                          │   │
│  │         • success_count++ (if success)                               │   │
│  │         • 更新熟练度                                                 │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│      │                                                                      │
│      ▼                                                                      │
│  下次会话 → 基于历史数据推荐技能 (闭环完成)                                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 4.3 Hook 脚本说明

| 脚本 | 触发时机 | 功能 |
|------|---------|------|
| `learning-capture.sh` | UserPromptSubmit | 从用户输入提取学习信号 |
| `solar-session-start.sh` | SessionStart | 加载自我模型 + 相关记忆 + 检查点 |
| `experience-reminder.sh` | PreToolUse:Write/Edit | 首次编码前提醒相关经验和铁律 |
| `solar-post-tool.sh` | PostToolUse:* | 记录工具使用到程序记忆 |
| `memory-record.sh` | 被 solar-post-tool.sh 调用 | 异步记录，不阻塞主流程 |
| `session-reflect.sh` | SessionEnd | 会话结束时自动反思 |

### 4.4 学习信号提取

用户输入会被自动分析，识别以下信号类型：

| 信号类型 | 触发模式 | 重要性 |
|----------|---------|--------|
| `correction` | "不对"、"错了"、"应该是" | 8 |
| `teaching` | "记住"、"必须"、"规则是" | 9 |
| `positive_feedback` | "好"、"可以"、"不错" | 4 |
| `negative_feedback` | "不好"、"重做" | 7 |
| `important_info` | 关键词密度 ≥2 | 6 |

### 4.5 定时任务

```bash
# cron 每日凌晨 3 点执行
0 3 * * * ~/.claude/core/memory/daily-consolidation.sh
```

定时任务功能：
1. 运行 consolidation-engine (短期→长期)
2. 清理过期记忆 (30天未访问 + 重要性<3)
3. 更新记忆衰减
4. 生成统计报告

## 5. 混合搜索

### 5.1 搜索权重配置

```typescript
const DEFAULT_WEIGHTS = {
  keyword: 0.3,    // 关键词搜索 (Tantivy)
  semantic: 0.3,   // 语义搜索 (向量)
  graph: 0.1,      // 图扩展
  favorites: 0.3   // 收藏加权 (高价值数据)
};
```

### 5.2 分数计算

```
最终分数 = Σ (搜索结果分数 × 权重)

其中:
- 关键词分数: Tantivy BM25 得分，归一化到 0-1
- 语义分数: 余弦相似度
- 图分数: 链接强度 × 衰减系数
- 收藏分数: (importance/10) × 0.95 × (1 + importance/20)
```

### 5.3 搜索优化

1. **并行执行**: 关键词、语义、收藏搜索并行
2. **早停**: 如果关键词精确匹配，跳过语义搜索
3. **图扩展可选**: 只对 Top-5 结果做图扩展
4. **缓存**: 热门查询结果缓存 5 分钟

## 6. 规则体系

### 6.1 相关规则文件

| 文件 | 内容 |
|------|------|
| `memory-loop.md` | 记忆闭环铁律：必须用起来 |
| `research-first.md` | 研究先行：不闭门造车 |
| `learning-evidence.md` | 学习证据：不说空话 |

### 6.2 核心铁律

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           记忆系统铁律                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  1. 闭环原则: 记忆必须影响决策，不是存起来就完了                            │
│                                                                             │
│  2. 研究先行: 设计算法/模型前必须查业界实践                                 │
│                                                                             │
│  3. 学习证据: 说"学到了"必须有证据，不说空话                               │
│                                                                             │
│  4. 失败优先: 失败的经验比成功的更重要 (importance更高)                     │
│                                                                             │
│  5. 衰减机制: 长期不用的记忆要衰减，避免噪声积累                            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 7. 性能指标

### 7.1 当前数据

```
程序记忆: 11 个技能，17 次执行
语义记忆: rule/lesson/wisdom 命名空间
情景记忆: 按会话和任务组织
视图数量: 38 个分析视图
```

### 7.2 性能目标

| 指标 | 目标 | 当前 |
|------|------|------|
| 记忆加载延迟 | < 100ms | ~50ms |
| 混合搜索延迟 | < 200ms | ~150ms |
| 工具记录延迟 | 异步，不阻塞 | ✓ |
| 向量嵌入维度 | 256 | 256 |

## 8. 未来演进

### 8.1 待实现功能

| 优先级 | 功能 | 描述 |
|--------|------|------|
| P1 | 定时固化 | cron 每日运行 consolidation-engine |
| P1 | 主动遗忘 | 清理低价值、长期未访问的记忆 |
| P2 | 可视化仪表盘 | 记忆分布、熟练度趋势 |
| P2 | 跨会话学习 | 从历史会话提取模式 |
| P3 | 外部知识注入 | 从文档/论文导入语义记忆 |

### 8.2 架构演进方向

```
当前: 单机 SQLite + 本地向量
     │
     ▼
Phase 2: 向量数据库集成 (Qdrant/Milvus)
     │
     ▼
Phase 3: 分布式记忆 (多 Solar 实例共享)
     │
     ▼
Phase 4: 联邦学习 (隐私保护的跨实例学习)
```

## 9. 文件清单

### 9.1 核心代码

```
~/.claude/core/memory/
├── memory-hook.ts          # 闭环核心
├── learning-extractor.ts   # 学习信号提取 [NEW]
├── session-reflector.ts    # 会话反思引擎 [NEW]
├── daily-consolidation.sh  # 每日固化脚本 [NEW]
├── episodic-writer.ts      # 情景记忆写入
├── consolidation-engine.ts # 记忆固化
├── memory-embedder.ts      # 向量嵌入
├── memory-linker.ts        # 记忆链接
├── hybrid-search.ts        # 混合搜索
├── procedural-tracker.ts   # 程序记忆追踪
├── proficiency-analyzer.ts # 熟练度分析 (v1, 废弃)
└── proficiency-v2.ts       # 熟练度分析 (v2, 基于研究)
```

### 9.2 Hook 脚本

```
~/.claude/hooks/
├── learning-capture.sh     # 学习信号捕获 [NEW]
├── session-reflect.sh      # 会话反思 [NEW]
├── solar-session-start.sh  # 会话启动
├── solar-post-tool.sh      # 工具调用后
├── experience-reminder.sh  # 经验提醒
└── memory-record.sh        # 记录脚本
```

### 9.3 规则文件

```
~/.claude/rules/
├── memory-loop.md          # 记忆闭环铁律
├── research-first.md       # 研究先行
└── learning-evidence.md    # 学习证据
```

### 9.4 数据库表

```
~/.solar/solar.db
├── evo_memory_episodic     # 情景记忆
├── evo_memory_semantic     # 语义记忆
├── evo_memory_procedural   # 程序记忆
├── evo_memory_links        # 记忆链接
├── sys_favorites           # 高价值收藏
└── v_evo_*                 # 38个分析视图
```

---

*Solar Memory System Architecture v2.0*
*知行合一 - 学了要用，用了要记*
*研究先行 - 站在巨人的肩膀上*
