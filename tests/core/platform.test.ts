/**
 * Platform Layer Test
 *
 * Terminal-native Application Runtime 测试:
 * - RenderProfile (Adaptive Theme + Emoji Fallback)
 * - Widget System (Plugin interface)
 * - OutputSink (Remote streaming)
 * - Layout Compiler (Declarative DSL)
 */

import {
  // RenderProfile
  DEFAULT_RENDER_PROFILE,
  SSH_SAFE_PROFILE,
  LOG_PROFILE,
  detectRenderProfile,
  applyRenderProfile,
  getIcon,
  ICON_FALLBACK,
  BOX_FALLBACK,
  // Widget System
  WidgetRegistry,
  WidgetRuntime,
  Widget,
  // Layout Compiler
  parseLayoutDSL,
  LayoutCompiler,
  // Types
  RenderProfile,
  CardLayout,
} from "tvs/v2";

console.log("🚀 Platform Layer Test\n");
console.log("═".repeat(80));

// ==================== Test 1: RenderProfile Detection ====================

console.log("\n📋 Test 1: RenderProfile Detection\n");

const detectedProfile = detectRenderProfile();
console.log("Detected profile:");
console.log(`  unicode:    ${detectedProfile.unicode}`);
console.log(`  emoji:      ${detectedProfile.emoji}`);
console.log(`  color:      ${detectedProfile.color}`);
console.log(`  colorDepth: ${detectedProfile.colorDepth}`);
console.log(`  theme:      ${detectedProfile.theme}`);

console.log("\nPreset profiles:");
console.log("  DEFAULT:", JSON.stringify(DEFAULT_RENDER_PROFILE));
console.log("  SSH_SAFE:", JSON.stringify(SSH_SAFE_PROFILE));
console.log("  LOG:", JSON.stringify(LOG_PROFILE));

// ==================== Test 2: Emoji Fallback ====================

console.log("\n" + "─".repeat(80));
console.log("\n📋 Test 2: Emoji Fallback\n");

const testContent = `
┌─ 🧠 Agent Status ─────────────────────┐
│ ✅ Status: Running                    │
│ ⏱️ Latency: 14ms                      │
│ 📊 Load: ████████▊ 78%                │
└───────────────────────────────────────┘
`;

console.log("Original (Emoji Mode ON):");
console.log(testContent);

console.log("Fallback (SSH Safe Mode):");
console.log(applyRenderProfile(testContent, SSH_SAFE_PROFILE));

console.log("Fallback (Log Mode - Unicode but no Emoji):");
console.log(applyRenderProfile(testContent, LOG_PROFILE));

// ==================== Test 3: Icon Fallback Table ====================

console.log("\n" + "─".repeat(80));
console.log("\n📋 Test 3: Icon Fallback Table\n");

console.log("Emoji      ASCII Fallback");
console.log("─────────────────────────");
const iconSamples = ["🧠", "📊", "⏱️", "✅", "⚠️", "❌"];
for (const emoji of iconSamples) {
  const fallback = ICON_FALLBACK[emoji] || "[?]";
  console.log(`${emoji.padEnd(10)} ${fallback}`);
}

// ==================== Test 4: Widget System ====================

console.log("\n" + "─".repeat(80));
console.log("\n📋 Test 4: Widget System (Plugin Interface)\n");

// 创建自定义 Widget
class MockAgentWidget implements Widget {
  id = "agent-coder";
  title = "Agent Coder";
  icon = "agent" as const;
  span = 1;

  private loadValue = 0.5;

  poll() {
    // 模拟数据变化
    this.loadValue = Math.random() * 0.5 + 0.3;
    return {
      status: "running",
      load: this.loadValue,
      tasks: Math.floor(Math.random() * 10),
    };
  }

  render(data: { status: string; load: number; tasks: number }): CardLayout {
    return {
      type: "card",
      sections: [
        { type: "header", text: this.title, icon: this.icon },
        { type: "divider" },
        {
          type: "kv",
          items: [
            { key: "Status", value: data?.status || "Unknown" },
            { key: "Load", bar: data?.load || 0 },
            { key: "Tasks", value: String(data?.tasks || 0) },
          ],
        },
      ],
    };
  }
}

class MockSystemWidget implements Widget {
  id = "system";
  title = "System";
  icon = "system" as const;
  span = 2;

  poll() {
    return {
      cpu: Math.random() * 0.4 + 0.2,
      memory: Math.random() * 0.3 + 0.5,
    };
  }

  render(data: { cpu: number; memory: number }): CardLayout {
    return {
      type: "card",
      sections: [
        { type: "header", text: this.title, icon: this.icon },
        { type: "divider" },
        {
          type: "kv",
          items: [
            { key: "CPU", bar: data?.cpu || 0 },
            { key: "Memory", bar: data?.memory || 0 },
          ],
        },
      ],
    };
  }
}

// 注册 Widget
const registry = new WidgetRegistry();
registry.register(new MockAgentWidget());
registry.register(new MockSystemWidget());

console.log("Registered widgets:");
for (const w of registry.all()) {
  console.log(`  - ${w.id}: ${w.title} (span: ${w.span})`);
}

// 测试 WidgetRuntime
const runtime = new WidgetRuntime(registry);
await runtime.pollAll();

console.log("\nWidget data after poll:");
for (const id of registry.ids()) {
  const data = runtime.getData(id);
  console.log(`  ${id}: ${JSON.stringify(data)}`);
}

console.log("\nWidget dirty check:", runtime.isDirty());

// ==================== Test 5: Layout Compiler ====================

console.log("\n" + "─".repeat(80));
console.log("\n📋 Test 5: Layout Compiler (Declarative DSL)\n");

const layoutSource = `
// Dashboard 配置
dashboard {
  grid: 3;
  gap: 2;
}

// Agent 卡片
card.agent-coder {
  span: 1;
}

// System 卡片
card.system {
  span: 2;
}
`;

console.log("Layout Source:");
console.log(layoutSource);

const compiler = new LayoutCompiler();
compiler.load(layoutSource);

console.log("\nParsed AST:");
for (const node of compiler.getAST()) {
  console.log(
    `  ${node.type}${node.selector ? "." + node.selector : ""}: ${JSON.stringify(node.properties)}`,
  );
}

console.log("\nDashboard config:", compiler.getDashboardConfig());
console.log(
  "Card config (agent-coder):",
  compiler.getCardConfig("agent-coder"),
);
console.log("Card config (system):", compiler.getCardConfig("system"));

// ==================== Test 6: Grid Compilation ====================

console.log("\n" + "─".repeat(80));
console.log("\n📋 Test 6: Grid Compilation\n");

const grid = runtime.renderAll(compiler.getDashboardConfig().columns);

console.log("Compiled Grid:");
console.log(`  type: ${grid.type}`);
console.log(`  columns: ${grid.columns}`);
console.log(`  gap: ${grid.gap}`);
console.log(`  cells: ${grid.cells.length}`);

for (let i = 0; i < grid.cells.length; i++) {
  const cell = grid.cells[i];
  console.log(
    `    Cell ${i}: span=${cell.span}, sections=${cell.content.sections.length}`,
  );
}

// ==================== Test 7: RenderProfile Comparison ====================

console.log("\n" + "─".repeat(80));
console.log("\n📋 Test 7: Same DSL, Different Output\n");

const sampleCard = `
╭─────────────────────────────────╮
│ 🤖 Agent Coder                  │
├─────────────────────────────────┤
│ Status │ ✅ Running             │
│ Load   │ ████████▊ 78%          │
│ Tasks  │ 5                      │
╰─────────────────────────────────╯
`;

const profiles: Array<{ name: string; profile: RenderProfile }> = [
  { name: "Full (Default)", profile: DEFAULT_RENDER_PROFILE },
  { name: "Log (No Emoji)", profile: LOG_PROFILE },
  { name: "SSH Safe", profile: SSH_SAFE_PROFILE },
];

for (const { name, profile } of profiles) {
  console.log(`[${name}]`);
  console.log(applyRenderProfile(sampleCard, profile));
}

// ==================== Test 8: Platform Architecture ====================

console.log("\n" + "─".repeat(80));
console.log("\n📋 Test 8: Platform Architecture\n");

console.log("┌─────────────────────────────────────────────────────────────┐");
console.log("│              Terminal-native Application Runtime            │");
console.log("├─────────────────────────────────────────────────────────────┤");
console.log("│                                                             │");
console.log("│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐       │");
console.log("│  │   Widget    │   │   Widget    │   │   Widget    │       │");
console.log("│  │   (Agent)   │   │  (System)   │   │   (GPU)     │       │");
console.log("│  └──────┬──────┘   └──────┬──────┘   └──────┬──────┘       │");
console.log("│         │                 │                 │              │");
console.log("│         └────────────────┬┘─────────────────┘              │");
console.log("│                          ↓                                 │");
console.log("│  ┌─────────────────────────────────────────────────┐       │");
console.log("│  │              Widget Runtime                     │       │");
console.log("│  │   poll() → data → render() → CardLayout DSL    │       │");
console.log("│  └──────────────────────┬──────────────────────────┘       │");
console.log("│                         ↓                                  │");
console.log("│  ┌─────────────────────────────────────────────────┐       │");
console.log("│  │              Layout Compiler                    │       │");
console.log("│  │   DSL Text → AST → GridLayout                   │       │");
console.log("│  └──────────────────────┬──────────────────────────┘       │");
console.log("│                         ↓                                  │");
console.log("│  ┌─────────────────────────────────────────────────┐       │");
console.log("│  │              Renderer                           │       │");
console.log("│  │   GridLayout → Frame → RenderProfile Apply      │       │");
console.log("│  └──────────────────────┬──────────────────────────┘       │");
console.log("│                         ↓                                  │");
console.log("│  ┌─────────────────────────────────────────────────┐       │");
console.log("│  │              Output Sink                        │       │");
console.log("│  │   TTY / WebSocket / SSH / File                  │       │");
console.log("│  └─────────────────────────────────────────────────┘       │");
console.log("│                                                             │");
console.log("└─────────────────────────────────────────────────────────────┘");

// ==================== Summary ====================

console.log("\n" + "═".repeat(80));
console.log("\n✅ Platform Layer Test Completed!\n");

console.log("产品化三板斧:");
console.log("  1. 适配性:");
console.log("     • Adaptive Theme (dark/light 自动检测)");
console.log("     • Emoji Fallback (SSH / Log / CI 安全)");
console.log("     • Unicode Fallback (最大兼容性)");
console.log("");
console.log("  2. 可扩展性:");
console.log("     • Widget System (插件化卡片)");
console.log("     • WidgetRegistry (注册表)");
console.log("     • WidgetRuntime (poll/render 循环)");
console.log("");
console.log("  3. 可分发性:");
console.log("     • OutputSink 抽象层");
console.log("     • TTYSink (本地终端)");
console.log("     • WebSocketSink (浏览器)");
console.log("     • MultiSink (多端推送)");
console.log("");
console.log("  4. 声明式布局:");
console.log("     • Layout Compiler (类 CSS 语法)");
console.log("     • Layout 和 Data 解耦");
console.log("     • LLM 友好生成");
console.log("");
console.log("定位: Terminal-native Application Runtime");
console.log("       (Agent UI / Research UI / Ops UI)\n");
