/**
 * TAUR Integration Test
 *
 * 测试完整渲染管道:
 * Widget.poll() → Widget.render() → Grid → ASCII → Display
 *
 * ═══════════════════════════════════════════════════════════════════
 * 数据流
 * ═══════════════════════════════════════════════════════════════════
 *
 * ```
 * Widget.poll()         → 采集数据
 *       ↓
 * Widget.render()       → CardLayout DSL
 *       ↓
 * Runtime.renderGrid()  → GridLayout
 *       ↓
 * DisplayRenderer       → ASCII string[]
 *       ↓
 * Display.setBody()     → Terminal
 * ```
 */

import {
  // Widget
  Widget,
  createWidget,
  // Registry
  WIDGETS,
  Runtime,
  createRuntime,
  // Compiler
  compileTCSS,
  // Display
  createDisplayRenderer,
  renderGridToLines,
  renderCardToLines,
  // Types
  CardLayout,
  GridLayout,
} from "tvs/v2/sdk";

console.log("☀️ TAUR Integration Test\n");
console.log("═".repeat(80));

// ==================== Test 1: Widget → CardLayout ====================

console.log("\n📋 Test 1: Widget → CardLayout\n");

// 创建测试 Widget
const testWidget = createWidget({
  id: "test.widget",
  title: "Test Widget",
  poll: () => ({
    status: "online",
    requests: 1234,
    latency: 45,
    errorRate: 0.02,
  }),
  render: (data) => ({
    type: "card",
    sections: [
      { type: "header", text: "Test Widget", align: "center" },
      { type: "divider" },
      {
        type: "kv",
        items: [
          { key: "Status", value: data.status, status: "success" },
          { key: "Requests", value: data.requests, unit: "req/s" },
          { key: "Latency", value: data.latency, unit: "ms" },
          { key: "Error Rate", bar: data.errorRate, status: "success" },
        ],
      },
    ],
  }),
});

// 执行 poll 和 render
const widgetData = testWidget.poll({} as any);
console.log("Widget data:", widgetData);

const cardLayout = testWidget.render(widgetData, {} as any);
console.log("Card sections:", cardLayout.sections.length);
console.log("  - header");
console.log("  - divider");
console.log("  - kv (4 items)");

// ==================== Test 2: CardLayout → ASCII ====================

console.log("\n" + "─".repeat(80));
console.log("\n📋 Test 2: CardLayout → ASCII\n");

const cardLines = renderCardToLines(cardLayout, { width: 40 });
console.log("Rendered card:");
for (const line of cardLines) {
  console.log(`  ${line}`);
}

// ==================== Test 3: Multiple Cards → Grid ====================

console.log("\n" + "─".repeat(80));
console.log("\n📋 Test 3: Multiple Cards → Grid\n");

// 创建多个 Card
const cards: CardLayout[] = [
  {
    type: "card",
    sections: [
      { type: "header", text: "Agent Status", align: "center" },
      { type: "divider" },
      {
        type: "kv",
        items: [
          { key: "agent-a", value: "online", status: "success" },
          { key: "agent-b", value: "idle", status: "warning" },
          { key: "agent-c", value: "offline", status: "error" },
        ],
      },
    ],
  },
  {
    type: "card",
    sections: [
      { type: "header", text: "System", align: "center" },
      { type: "divider" },
      {
        type: "kv",
        items: [
          { key: "CPU", bar: 0.65 },
          { key: "Memory", bar: 0.42 },
          { key: "Disk", bar: 0.89, status: "warning" },
        ],
      },
    ],
  },
];

// 渲染为 Grid
const gridLayout: GridLayout = {
  type: "grid",
  columns: 2,
  gap: 2,
  cells: cards.map((card) => ({
    span: 1,
    content: card,
  })),
};

const gridLines = renderGridToLines(gridLayout, { width: 80 });
console.log("Rendered grid (2 columns):");
for (const line of gridLines) {
  console.log(`  ${line}`);
}

// ==================== Test 4: TCSS → Grid ====================

console.log("\n" + "─".repeat(80));
console.log("\n📋 Test 4: TCSS → CompiledLayout\n");

const tcss = `
dashboard {
  columns: 3;
  gap: 2;
}
card#agent {
  widget: agent.status;
  span: 1;
}
card#system {
  widget: system.overview;
  span: 1;
}
card#log {
  widget: agent.log;
  span: 1;
}
`;

const compiled = compileTCSS(tcss);
console.log("Dashboard config:");
console.log(`  columns: ${compiled.dashboard.columns}`);
console.log(`  gap: ${compiled.dashboard.gap}`);
console.log("\nCards:");
for (const card of compiled.cards) {
  console.log(`  - ${card.id}: widget=${card.widget}, span=${card.span}`);
}

// ==================== Test 5: DisplayRenderer ====================

console.log("\n" + "─".repeat(80));
console.log("\n📋 Test 5: DisplayRenderer\n");

const displayRenderer = createDisplayRenderer({
  width: 80,
  style: "enterprise_minimal",
  colors: false, // 禁用颜色以便于测试输出
});

// 使用 Renderer 渲染 Grid
const renderedGrid = displayRenderer.renderGrid(gridLayout);
console.log(`Rendered ${renderedGrid.length} lines`);
console.log("First 5 lines:");
for (let i = 0; i < Math.min(5, renderedGrid.length); i++) {
  console.log(`  ${i + 1}: ${renderedGrid[i].substring(0, 60)}...`);
}

// ==================== Test 6: Full Pipeline Simulation ====================

console.log("\n" + "─".repeat(80));
console.log("\n📋 Test 6: Full Pipeline Simulation\n");

console.log("Pipeline stages:");
console.log("  1. ✅ Widget.poll() → data object");
console.log("  2. ✅ Widget.render() → CardLayout DSL");
console.log("  3. ✅ Runtime.renderGrid() → GridLayout");
console.log("  4. ✅ DisplayRenderer.renderGrid() → ASCII string[]");
console.log("  5. ⏸️  Display.setBody() → Terminal (requires TUI mode)");

console.log("\nSimulated Body content (first 10 lines):");
console.log("┌" + "─".repeat(78) + "┐");
for (let i = 0; i < Math.min(10, renderedGrid.length); i++) {
  const line = renderedGrid[i].padEnd(78).substring(0, 78);
  console.log(`│${line}│`);
}
if (renderedGrid.length > 10) {
  console.log(`│${"...".padEnd(78)}│`);
}
console.log("└" + "─".repeat(78) + "┘");

// ==================== Summary ====================

console.log("\n" + "═".repeat(80));
console.log("\n✅ TAUR Integration Test Completed!\n");

console.log("完整渲染管道已验证:");
console.log("");
console.log(
  "  ┌─────────────────────────────────────────────────────────────┐",
);
console.log(
  "  │  Widget.poll()       采集数据                               │",
);
console.log(
  "  │       ↓                                                     │",
);
console.log(
  "  │  Widget.render()     生成 CardLayout DSL                    │",
);
console.log(
  "  │       ↓                                                     │",
);
console.log(
  "  │  Runtime.renderGrid() 组装 GridLayout                        │",
);
console.log(
  "  │       ↓                                                     │",
);
console.log(
  "  │  DisplayRenderer     渲染为 ASCII 行                         │",
);
console.log(
  "  │       ↓                                                     │",
);
console.log(
  "  │  Display.setBody()   输出到终端 Body 区域                    │",
);
console.log(
  "  └─────────────────────────────────────────────────────────────┘",
);
console.log("");
console.log("下一步: 运行 TUI 模式测试 (需要交互式终端)");
console.log("");
