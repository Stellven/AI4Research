/**
 * Agent Memory Architecture Dashboard
 * TVS VDL 格式 - 可直接由 termplane 渲染
 */

import { card, kv, table, sparkline, progress, section } from 'tvs/termplane';

// ==================== Layout (TCSS) ====================

export const layout = `
/* 主布局: 3列网格 */
.root {
  columns: 3;
  gap: 1;
  padding: 1;
}

/* 论文卡片 - 第一行 */
#paper-amem { column: 1; row: 1; }
#paper-survey { column: 2; row: 1; }
#paper-mem0 { column: 3; row: 1; }

/* 架构图 - 第二行跨全宽 */
#architecture { column: 1 / span 3; row: 2; }

/* 实施建议 - 第三行 */
#phase1 { column: 1; row: 3; }
#phase2 { column: 2; row: 3; }
#phase3 { column: 3; row: 3; }

/* 收益指标 - 第四行 */
#benefits { column: 1 / span 3; row: 4; }

/* 响应式: 窄终端 */
@media (max-width: 120) {
  .root { columns: 2; }
  #paper-mem0 { column: 1; row: 2; }
  #architecture { column: 1 / span 2; row: 3; }
}

@media (max-width: 80) {
  .root { columns: 1; }
}

/* Focus 样式 */
:focus {
  border-color: cyan;
  border-style: double;
}
`;

// ==================== Widgets (VDL) ====================

export const widgets = {
  // 论文1: A-MEM
  'paper-amem': card("A-MEM", [
    section("header", "NeurIPS 2025"),
    kv([
      { key: "Core", value: "Zettelkasten Network" },
      { key: "Innovation", value: "Memory Evolution" },
      { key: "Link", value: "arxiv:2502.12110" }
    ]),
    section("divider"),
    kv([
      { key: "Write", value: "Generate structured notes" },
      { key: "Link", value: "Auto-connect memories" },
      { key: "Evolve", value: "Trigger updates" }
    ])
  ]),

  // 论文2: Memory Survey
  'paper-survey': card("MEMORY SURVEY", [
    section("header", "Comprehensive Review"),
    kv([
      { key: "Framework", value: "3D Taxonomy" },
      { key: "Dimensions", value: "Form×Function×Dynamics" },
      { key: "Link", value: "arxiv:2512.13564" }
    ]),
    section("divider"),
    table(
      ["Dimension", "Categories"],
      [
        ["Form", "Token | Parametric | Latent"],
        ["Function", "Factual | Experiential | Working"],
        ["Dynamics", "Formation | Evolution | Retrieval"]
      ]
    )
  ]),

  // 论文3: Mem0
  'paper-mem0': card("MEM0", [
    section("header", "Production Ready"),
    kv([
      { key: "Type", value: "Scalable System" },
      { key: "Feature", value: "Graph Memory" },
      { key: "Link", value: "arxiv:2504.19413" }
    ]),
    section("divider"),
    kv([
      { key: "Latency", value: "-91% ↓" },
      { key: "Token Cost", value: "-90% ↓" },
      { key: "Improvement", value: "+26%" }
    ]),
    progress(91, 100, "Latency Reduction")
  ]),

  // 架构图
  'architecture': card("SOLAR MEMORY ARCHITECTURE", [
    section("ascii", `
┌─────────────────────────────────────────────────────────────────────────┐
│                         Memory Controller                                │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐            │
│  │  Write   │  │  Link    │  │  Evolve  │  │   Retrieve   │            │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └──────┬───────┘            │
└───────┼─────────────┼─────────────┼───────────────┼────────────────────┘
        │             │             │               │
        ▼             ▼             ▼               ▼
┌───────────────────────────────────────────────────────────────────────┐
│                     Memory Store (三层结构)                            │
│   ┌─────────────────────────────────────────────────────────────────┐ │
│   │  L1: Working Memory    │ 当前会话 │ 活跃任务 │ 临时缓存        │ │
│   ├─────────────────────────────────────────────────────────────────┤ │
│   │  L2: Episodic Memory   │ 会话历史 │ 交互记录 │ 决策日志        │ │
│   ├─────────────────────────────────────────────────────────────────┤ │
│   │  L3: Semantic Memory   │ 知识图谱 │ 概念网络 │ 压缩摘要        │ │
│   └─────────────────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────────────┘
    `)
  ]),

  // 实施阶段
  'phase1': card("PHASE 1", [
    section("header", "基础记忆表 (1周)"),
    kv([
      { key: "sys_memories", value: "记忆条目" },
      { key: "sys_memory_links", value: "关联链接" }
    ]),
    sparkline([10, 20, 30, 40, 60, 80, 100], "Progress")
  ]),

  'phase2': card("PHASE 2", [
    section("header", "图记忆层 (2周)"),
    kv([
      { key: "sys_memory_nodes", value: "实体节点" },
      { key: "sys_memory_edges", value: "关系边" }
    ]),
    sparkline([10, 15, 25, 35, 50, 70, 90], "Progress")
  ]),

  'phase3': card("PHASE 3", [
    section("header", "Memory Controller (2周)"),
    kv([
      { key: "write()", value: "智能提取" },
      { key: "link()", value: "自动关联" },
      { key: "evolve()", value: "记忆演化" },
      { key: "recall()", value: "语义检索" }
    ]),
    sparkline([5, 10, 20, 30, 45, 60, 80], "Progress")
  ]),

  // 收益指标
  'benefits': card("EXPECTED BENEFITS", [
    table(
      ["Metric", "Current", "After", "Source"],
      [
        ["Context Utilization", "~30%", "~80%", "Mem0"],
        ["Token Cost", "Baseline", "-90%", "Mem0"],
        ["P95 Latency", "Baseline", "-91%", "Mem0"],
        ["Memory Consistency", "Low", "High", "A-MEM"],
        ["Knowledge Accumulation", "Session", "Cross-session", "Survey"]
      ]
    )
  ])
};

// ==================== Dashboard Export ====================

export const dashboard = {
  id: "agent-memory-architecture",
  title: "Agent Memory Architecture",
  version: "1.0",
  layout,
  widgets
};

export default dashboard;
