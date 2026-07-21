/**
 * Solar TVS 渲染流程演示
 * 展示 TVS 作为 Solar 唯一渲染器的完整流程
 */

import { card, kv, table, sparkline, progress, section } from 'tvs/termplane';

// ==================== 1. 任务启动 ====================

export const taskStart = card("TASK STARTED", [
  section("header", "Solar Flow Initiated"),
  kv([
    { key: "Task ID", value: "#2024-0130-001" },
    { key: "Type", value: "Research + Architecture" },
    { key: "Phase", value: "P1 → Research" }
  ]),
  section("divider"),
  kv([
    { key: "Agent", value: "@Researcher" },
    { key: "Model", value: "Opus" },
    { key: "Status", value: "RUNNING ✓" }
  ])
]);

// ==================== 2. 研究进度 ====================

export const researchProgress = card("RESEARCH PROGRESS", [
  section("header", "arxiv Agent Memory Papers"),
  table(
    ["#", "Paper", "Status", "Value"],
    [
      ["1", "A-MEM", "✓ Fetched", "★★★★★"],
      ["2", "Memory Survey", "✓ Fetched", "★★★★★"],
      ["3", "Mem0", "✓ Fetched", "★★★★☆"]
    ]
  ),
  section("divider"),
  progress(100, 100, "Fetch Progress"),
  sparkline([10, 30, 50, 70, 90, 100], "Completion")
]);

// ==================== 3. 分析结果 ====================

export const analysisResult = card("ANALYSIS RESULT", [
  section("header", "Key Insights Extracted"),
  kv([
    { key: "Papers Analyzed", value: "3" },
    { key: "Core Patterns", value: "3" },
    { key: "Design Principles", value: "5" }
  ]),
  section("divider"),
  table(
    ["Pattern", "Source", "Applicability"],
    [
      ["Zettelkasten Memory", "A-MEM", "HIGH"],
      ["3D Taxonomy", "Survey", "MEDIUM"],
      ["Graph + Compress", "Mem0", "HIGH"]
    ]
  )
]);

// ==================== 4. 阶段转换 ====================

export const phaseTransition = card("PHASE TRANSITION", [
  section("header", "P1 → P2 Gate Check"),
  kv([
    { key: "From", value: "P1 Research" },
    { key: "To", value: "P2 Design" },
    { key: "Gate", value: "G1" }
  ]),
  section("divider"),
  table(
    ["Check", "Result"],
    [
      ["Research Complete", "✓ PASS"],
      ["Insights Documented", "✓ PASS"],
      ["Feasibility Assessed", "✓ PASS"]
    ]
  ),
  section("divider"),
  kv([
    { key: "Gate Status", value: "PASSED ✓" },
    { key: "Next Agent", value: "@Architect" }
  ])
]);

// ==================== 5. 架构输出 ====================

export const architectureOutput = card("ARCHITECTURE OUTPUT", [
  section("header", "Agent Memory System Design"),
  section("ascii", `
┌─────────────────────────────────────────────────┐
│              Memory Controller                   │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌──────────┐ │
│  │ Write  │ │ Link   │ │ Evolve │ │ Retrieve │ │
│  └───┬────┘ └───┬────┘ └───┬────┘ └────┬─────┘ │
└──────┼──────────┼──────────┼───────────┼───────┘
       └──────────┴──────────┴───────────┘
                      │
       ┌──────────────┼──────────────┐
       ▼              ▼              ▼
   ┌────────┐    ┌────────┐    ┌────────┐
   │Working │    │Episodic│    │Semantic│
   │ Memory │    │ Memory │    │ Memory │
   └────────┘    └────────┘    └────────┘
  `),
  kv([
    { key: "Tables", value: "6 new" },
    { key: "Views", value: "4 new" },
    { key: "Triggers", value: "3 new" }
  ])
]);

// ==================== 6. 任务完成 ====================

export const taskComplete = card("TASK COMPLETED", [
  section("header", "Solar Flow Finished"),
  kv([
    { key: "Task ID", value: "#2024-0130-001" },
    { key: "Duration", value: "3m 42s" },
    { key: "Status", value: "SUCCESS ✓" }
  ]),
  section("divider"),
  table(
    ["Metric", "Value"],
    [
      ["Tokens Used", "12,450"],
      ["Cost", "$0.18"],
      ["Files Created", "4"],
      ["Rules Added", "2"]
    ]
  ),
  section("divider"),
  kv([
    { key: "Output", value: "AGENT_MEMORY_ARCHITECTURE.md" },
    { key: "Rules", value: "infrastructure-as-tables.md, tvs-rendering.md" }
  ])
]);

// ==================== 完整仪表盘布局 ====================

export const layout = `
.root {
  columns: 2;
  gap: 1;
  padding: 1;
}

#task-start { column: 1; row: 1; }
#research-progress { column: 2; row: 1; }
#analysis-result { column: 1; row: 2; }
#phase-transition { column: 2; row: 2; }
#architecture { column: 1 / span 2; row: 3; }
#task-complete { column: 1 / span 2; row: 4; }

@media (max-width: 100) {
  .root { columns: 1; }
}

:focus { border-color: cyan; }
`;

export const dashboard = {
  id: "solar-tvs-demo",
  title: "Solar TVS Flow Demo",
  layout,
  widgets: {
    'task-start': taskStart,
    'research-progress': researchProgress,
    'analysis-result': analysisResult,
    'phase-transition': phaseTransition,
    'architecture': architectureOutput,
    'task-complete': taskComplete
  }
};

export default dashboard;
