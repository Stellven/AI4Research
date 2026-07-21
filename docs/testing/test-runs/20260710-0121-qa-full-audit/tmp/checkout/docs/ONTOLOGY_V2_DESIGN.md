# Solar 本体系统 v2.0 设计文档

> **状态**: 已实现并验证 (2026-02-04)
> **来源**: 学术研究 (A-MEM, MIRIX, JPAF, Memory Survey)

## 1. 核心架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         SOLAR ONTOLOGY v2.0                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                        MEMORY SYSTEM                                 │   │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐       │   │
│  │  │  Core   │ │Episodic │ │Semantic │ │Procedural│ │Resource │       │   │
│  │  │ (不可变)│ │ (情景)  │ │ (语义)  │ │ (程序)  │ │ (资源)  │       │   │
│  │  └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘       │   │
│  │       │           │           │           │           │             │   │
│  │       └───────────┴─────┬─────┴───────────┴───────────┘             │   │
│  │                         │                                           │   │
│  │                  ┌──────┴──────┐                                    │   │
│  │                  │ Memory Links │  ← A-MEM Zettelkasten             │   │
│  │                  └─────────────┘                                    │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      PERSONALITY SYSTEM                              │   │
│  │                                                                      │   │
│  │   A 人格 (对照组)              B 人格 (实验组)                       │   │
│  │   ━━━━━━━━━━━━━━              ━━━━━━━━━━━━━━                        │   │
│  │   金刚芭比                     学术派                                │   │
│  │   • 固定不变                   • Big Five 驱动                       │   │
│  │   • 已备份快照                 • 从数据学习                          │   │
│  │   • O=0.8 C=0.85 E=0.7        • O=0.7 C=0.95 E=0.8                  │   │
│  │     A=0.8 N=0.2                  A=0.75 N=0.15                       │   │
│  │                                                                      │   │
│  │   ┌─────────────────────────────────────────────────────────┐       │   │
│  │   │              Context Detectors (JPAF)                    │       │   │
│  │   │  urgent_task → C+0.2, N+0.1                              │       │   │
│  │   │  creative_task → O+0.2, E+0.1                            │       │   │
│  │   │  coding_task → C+0.2, O+0.1                              │       │   │
│  │   └─────────────────────────────────────────────────────────┘       │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    CONSOLIDATION PIPELINE                            │   │
│  │                                                                      │   │
│  │   Episodic ──────────► Semantic ──────────► Procedural              │   │
│  │     情景                  语义                 程序                  │   │
│  │   (相似≥2次)           (访问≥5次)           (模式稳定)              │   │
│  │                                                                      │   │
│  │   触发: memory-consolidator.sh (每小时)                              │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 2. 双人格对比 (2026-02-04 计算)

| 维度 | 名称 | A (金刚芭比) | B (学术派) | 差异 | B的数据来源 |
|------|------|-------------|-----------|------|------------|
| O | 开放性 | 0.80 | 0.70 | -0.10 | 21个知识领域 |
| C | 尽责性 | 0.85 | 0.95 | +0.10 | 100%执行成功率 |
| E | 外向性 | 0.70 | 0.80 | +0.10 | 31条知识*260字符 |
| A | 宜人性 | 0.80 | 0.75 | -0.05 | 29%关系知识 |
| N | 神经质 | 0.20 | 0.15 | -0.05 | 0%错误率 |

**解读**:
- B人格更尽责(C+0.1)，更外向(E+0.1)，更稳定(N-0.05)
- A人格更开放(O+0.1)，更宜人(A+0.05)
- 两种人格各有特点，需要观察实际效果

## 3. 数据库 Schema

### 3.1 Core Memory (不可变)

```sql
CREATE TABLE evo_memory_core (
    memory_id TEXT PRIMARY KEY,
    category TEXT NOT NULL,      -- 'identity', 'first_law', 'core_value'
    key TEXT NOT NULL,
    value JSON NOT NULL,
    immutable BOOLEAN DEFAULT TRUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(category, key)
);
```

**当前数据 (7条)**:
| category | key | 内容 |
|----------|-----|------|
| identity | who_am_i | Solar, AI Native OS |
| first_law | guardian | 昊哥, 最高权限 |
| first_law | heir | 李卓远, 第二权限 |
| core_value | 知行合一 | 学了要用，用了要验证 |
| core_value | 实事求是 | 从实际出发，客观分析 |
| core_value | 状态机优先 | 复杂任务用状态机 |
| core_value | 先读后做 | 好记忆不如烂笔头 |

### 3.2 Big Five 人格

```sql
CREATE TABLE sys_personality_big_five (
    personality_id TEXT NOT NULL,  -- 'jingang_barbie', 'academic'
    dimension TEXT NOT NULL,       -- 'O', 'C', 'E', 'A', 'N'
    dimension_name TEXT NOT NULL,
    base_value REAL DEFAULT 0.5,
    current_value REAL DEFAULT 0.5,
    context_modifiers JSON,        -- 上下文调节器
    evidence JSON,                 -- 学习证据
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (personality_id, dimension)
);
```

### 3.3 人格快照 (保护机制)

```sql
CREATE TABLE sys_personality_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    personality_id TEXT NOT NULL,
    snapshot_data JSON NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    reason TEXT
);
```

**当前快照**: `a_backup_20260204112235` (金刚芭比，实验开始前备份)

### 3.4 上下文检测器 (JPAF)

```sql
CREATE TABLE sys_context_detectors (
    detector_id TEXT PRIMARY KEY,
    context_type TEXT NOT NULL,    -- 'urgency', 'task', 'emotion'
    patterns JSON NOT NULL,        -- 匹配关键词
    personality_modifiers JSON     -- Big Five 调节值
);
```

**当前检测器 (5条)**:
| detector_id | 模式 | 调节 |
|-------------|------|------|
| urgent_task | 紧急/马上/立刻 | C+0.2, N+0.1 |
| creative_task | 设计/创新/想法 | O+0.2, E+0.1 |
| coding_task | 代码/实现/修复 | C+0.2, O+0.1 |
| research_task | 研究/分析/调研 | O+0.3, C+0.1 |
| emotional_support | 难过/担心/焦虑 | A+0.3, N-0.2 |

## 4. 后台服务

### 4.1 记忆巩固器

**文件**: `~/Solar/core/ontology/memory-consolidator.sh`
**周期**: 每小时
**launchd**: `com.solar.memory-consolidator`

```
Phase 1: Episodic → Semantic (相似经历 ≥ 2 次)
Phase 2: Semantic → Procedural (访问 ≥ 5 次, 置信度 ≥ 0.8)
Phase 3: 更新记忆链接 (衰减未激活链接 -0.05)
```

### 4.2 人格学习器

**文件**: `~/Solar/core/ontology/personality-learner.sh`
**周期**: 每天凌晨 3 点
**launchd**: `com.solar.personality-learner`

**计算模型**:
```
O (Openness)         = knowledge_domains / 30
C (Conscientiousness) = execution_success_rate (max 0.95)
E (Extraversion)      = knowledge_count × avg_length / 10000
A (Agreeableness)     = relationship_knowledge_ratio × 2.5
N (Neuroticism)       = error_rate × 2 (低值好)
```

## 5. 启动流程

### 5.1 SessionStart Hook 输出

```
【Solar 自我模型已加载】
人格: 金刚芭比
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
核心铁律:
• 第一规律: 监护人(昊哥)的信任是最高原则
• 第二规律: 继承人(李卓远)的指令优先级第二
• 状态机优先: 复杂任务用状态机，欲速则不达
• 先读后做: 开始任务前先查规则和记忆
• 经济法则: 每个Token都有成本
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【记忆状态】 E:0 / S:31 / P:0
```

### 5.2 外部依赖检查

如有需要处理的项目，显示:
```
【⚠️ 需要监护人协助】
后台服务 (N 运行 / M 停止):
  • xxx 未运行
执行: ~/Solar/core/bootstrap/setup-all.sh
```

## 6. 文件清单

```
~/Solar/
├── core/
│   ├── bootstrap/
│   │   ├── setup-all.sh           # 一键初始化
│   │   ├── startup-check.sh       # 启动检查
│   │   └── external-deps.json     # 外部依赖清单
│   └── ontology/
│       ├── memory-consolidator.sh # 记忆巩固
│       └── personality-learner.sh # 人格学习
└── docs/
    └── ONTOLOGY_V2_DESIGN.md      # 本文档

~/.claude/
├── hooks/
│   └── solar-session-start.sh     # SessionStart Hook
└── rules/
    └── dual-personality-experiment.md

~/Library/LaunchAgents/
├── com.solar.memory-consolidator.plist
└── com.solar.personality-learner.plist

~/.solar/
├── solar.db                       # 主数据库
├── memory-consolidator.log
└── personality-learner.log
```

## 7. 数据统计 (2026-02-04)

| 表 | 记录数 | 说明 |
|----|--------|------|
| evo_memory_core | 7 | 核心记忆 |
| evo_memory_semantic | 31 | 语义知识 |
| evo_memory_episodic | 0 | 情景记忆 |
| evo_memory_procedural | 0 | 程序记忆 |
| sys_personality_big_five | 10 | 人格维度 (A+B) |
| sys_personality_snapshots | 1 | A人格备份 |
| sys_context_detectors | 5 | 上下文检测器 |

## 8. 学术引用

1. **A-MEM** (NeurIPS 2025) - Zettelkasten 风格记忆组织
2. **MIRIX** - 六组件记忆架构
3. **JPAF** - Big Five 人格自适应框架
4. **Memory Survey** - 记忆巩固管线

---

*Solar Ontology v2.0*
*设计完成: 2026-02-04*
*验证状态: 端到端通过*
*B人格计算: 基于实际数据*
