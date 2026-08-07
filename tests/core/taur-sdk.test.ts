/**
 * TAUR SDK Test
 *
 * Terminal Agent UI Runtime 完整测试:
 * - Widget System
 * - TCSS Layout Compiler
 * - TAUR Runtime Integration
 */

import {
  // Core
  Widget,
  createWidget,
  WidgetContext,
  createWidgetContext,
  // Registry
  Registry,
  WIDGETS,
  register,
  Runtime,
  createRuntime,
  // Compiler
  Lexer,
  Parser,
  Compiler,
  compileTCSS,
  EXAMPLE_TCSS,
  // Built-in Widgets
  AgentStatusWidget,
  LatencyWidget,
  GPUWidget,
  LogTailWidget,
  SystemOverviewWidget,
  registerBuiltinWidgets,
  // TAUR
  TAUR,
  createTAUR,
  quickStart,
  // Types
  CardLayout,
  GridLayout,
} from "tvs/v2/sdk";

console.log("☀️ TAUR SDK Test\n");
console.log("═".repeat(80));

// ==================== Test 1: Widget Base Class ====================

console.log("\n📋 Test 1: Widget Base Class\n");

// 使用函数式 API 创建 Widget
const testWidget = createWidget({
  id: "test.widget",
  title: "Test Widget",
  icon: "info",
  refreshHz: 2.0,
  span: 1,
  poll: (ctx) => ({ value: Math.random(), tick: ctx.tickCount }),
  render: (data, ctx) => ({
    type: "card",
    sections: [
      { type: "header", text: "Test Widget" },
      { type: "divider" },
      {
        type: "kv",
        items: [
          { key: "Value", value: data.value.toFixed(2) },
          { key: "Tick", value: String(data.tick) },
        ],
      },
    ],
  }),
});

console.log("Widget created:");
console.log(`  id: ${testWidget.id}`);
console.log(`  title: ${testWidget.title}`);
console.log(`  refreshHz: ${testWidget.refreshHz}`);
console.log(`  lifecycle: ${testWidget.lifecycle}`);

// ==================== Test 2: Widget Context ====================

console.log("\n" + "─".repeat(80));
console.log("\n📋 Test 2: Widget Context\n");

const ctx = createWidgetContext();
console.log("Default context:");
console.log(`  timestamp: ${ctx.timestamp}`);
console.log(`  tickCount: ${ctx.tickCount}`);
console.log(`  viewportWidth: ${ctx.viewportWidth}`);
console.log(`  viewportHeight: ${ctx.viewportHeight}`);
console.log(`  theme: ${ctx.theme}`);

// ==================== Test 3: TCSS Lexer ====================

console.log("\n" + "─".repeat(80));
console.log("\n📋 Test 3: TCSS Lexer\n");

const tcssSource = `
dashboard {
  columns: 3;
  gap: 2;
}

card#agent {
  widget: agent.status;
  span: 1;
}
`;

const lexer = new Lexer(tcssSource);
const tokens = lexer.tokenize();

console.log("Tokens:");
for (const token of tokens.slice(0, 10)) {
  console.log(`  ${token.type.padEnd(12)} ${JSON.stringify(token.value)}`);
}
console.log(`  ... (${tokens.length} total tokens)`);

// ==================== Test 4: TCSS Parser ====================

console.log("\n" + "─".repeat(80));
console.log("\n📋 Test 4: TCSS Parser\n");

const parser = new Parser(tokens);
const ast = parser.parse();

console.log("AST Rules:");
for (const rule of ast.rules) {
  console.log(`  ${rule.selector}:`);
  console.log(`    type: ${rule.selectorType}`);
  if (rule.selectorId) console.log(`    id: ${rule.selectorId}`);
  console.log(`    properties: ${JSON.stringify(rule.properties)}`);
}

// ==================== Test 5: TCSS Compiler ====================

console.log("\n" + "─".repeat(80));
console.log("\n📋 Test 5: TCSS Compiler\n");

const compiled = compileTCSS(EXAMPLE_TCSS);

console.log("Compiled Layout:");
console.log(
  `  Dashboard: columns=${compiled.dashboard.columns}, gap=${compiled.dashboard.gap}`,
);
console.log(`  Cards: ${compiled.cards.length}`);
for (const card of compiled.cards) {
  console.log(
    `    - ${card.id || card.class || "anonymous"}: widget=${card.widget}, span=${card.span}`,
  );
}

// ==================== Test 6: Built-in Widgets ====================

console.log("\n" + "─".repeat(80));
console.log("\n📋 Test 6: Built-in Widgets\n");

// 创建新的注册表
const testRegistry = new Registry();
registerBuiltinWidgets();

const builtinWidgets = [
  new AgentStatusWidget(),
  new LatencyWidget(),
  new GPUWidget(),
  new LogTailWidget(),
  new SystemOverviewWidget(),
];

console.log("Built-in Widgets:");
for (const w of builtinWidgets) {
  console.log(`  - ${w.id}: ${w.title} (span=${w.span}, hz=${w.refreshHz})`);
}

// ==================== Test 7: Widget Runtime ====================

console.log("\n" + "─".repeat(80));
console.log("\n📋 Test 7: Widget Runtime\n");

// 注册 Widgets
const registry = new Registry();
for (const w of builtinWidgets) {
  registry.register(w);
}

const runtime = createRuntime(registry);
runtime.setLayout(["agent.status", "agent.latency", "system.gpu"]);

// 挂载
await runtime.mount();
console.log("Widgets mounted");

// Poll 数据
await runtime.tick();
console.log("First tick completed");

// 检查数据
console.log("\nWidget data:");
for (const id of ["agent.status", "agent.latency", "system.gpu"]) {
  const data = runtime.getData(id);
  console.log(`  ${id}: ${JSON.stringify(data).slice(0, 60)}...`);
}

// 渲染 Grid
const grid = runtime.renderGrid(3, 2);
console.log(`\nGrid: ${grid.cells.length} cells, ${grid.columns} columns`);

// ==================== Test 8: TAUR Integration ====================

console.log("\n" + "─".repeat(80));
console.log("\n📋 Test 8: TAUR Integration\n");

const taur = createTAUR({ registerBuiltins: false });

// 手动注册 (因为上面已经注册过了)
for (const w of builtinWidgets) {
  WIDGETS.register(w);
}

// 加载布局
taur.loadLayout(`
  dashboard { columns: 3; gap: 2; }
  card#agent { widget: agent.status; span: 1; }
  card#latency { widget: agent.latency; span: 1; }
  card#gpu { widget: system.gpu; span: 1; }
  card#log { widget: agent.log; span: 2; }
  card#system { widget: system.overview; span: 1; }
`);

console.log("Layout loaded");
console.log(`  Dashboard: ${JSON.stringify(taur.getDashboardConfig())}`);

// 启动
await taur.start();
console.log(`  State: ${taur.getState()}`);

// 渲染一帧
const frame = await taur.render();
console.log(`\nRendered frame:`);
console.log(`  Cells: ${frame.cells.length}`);
console.log(`  Columns: ${frame.columns}`);

// 检查每个 Cell
for (let i = 0; i < frame.cells.length; i++) {
  const cell = frame.cells[i];
  const sections = cell.content.sections.length;
  console.log(`  Cell ${i}: span=${cell.span}, sections=${sections}`);
}

// 停止
await taur.stop();
console.log(`\nStopped: ${taur.getState()}`);

// ==================== Test 9: Quick Start ====================

console.log("\n" + "─".repeat(80));
console.log("\n📋 Test 9: Quick Start API\n");

const { taur: quickTaur, grid: quickGrid } = await quickStart(
  `
  dashboard { columns: 2; gap: 1; }
  card#agent { widget: agent.status; span: 1; }
  card#system { widget: system.overview; span: 1; }
`,
  { registerBuiltins: false },
);

console.log("Quick start result:");
console.log(`  State: ${quickTaur.getState()}`);
console.log(`  Grid cells: ${quickGrid.cells.length}`);

await quickTaur.stop();

// ==================== Summary ====================

console.log("\n" + "═".repeat(80));
console.log("\n✅ TAUR SDK Test Completed!\n");

console.log("TAUR (Terminal Agent UI Runtime) v0.1");
console.log("");
console.log("Architecture:");
console.log("  ┌────────────────────────────────────────────────────────┐");
console.log("  │                    TAUR Runtime                        │");
console.log("  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │");
console.log("  │  │   Widget     │  │    TCSS      │  │   Renderer   │ │");
console.log("  │  │   System     │  │   Compiler   │  │  Integration │ │");
console.log("  │  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘ │");
console.log("  │         │                 │                 │         │");
console.log("  │         └────────────────┬┘─────────────────┘         │");
console.log("  │                          ↓                            │");
console.log("  │  ┌────────────────────────────────────────────────┐   │");
console.log("  │  │  poll() → data → render() → DSL → ASCII/Frame  │   │");
console.log("  │  └────────────────────────────────────────────────┘   │");
console.log("  └────────────────────────────────────────────────────────┘");
console.log("");
console.log("Features:");
console.log("  • 插件化: Widget = 数据源 + 语义渲染器");
console.log("  • 声明式: TCSS Layout DSL (类 CSS 语法)");
console.log("  • 可回放: Snapshot Buffer 支持时间旅行");
console.log("  • 多端流式: OutputSink 抽象 (TTY/WebSocket/SSH)");
console.log("");
