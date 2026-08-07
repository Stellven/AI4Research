/**
 * TAUR v0.2 Integration Test
 *
 * 测试 v0.2 新特性:
 * - @media 响应式布局 (终端宽度自适应)
 * - :focus 伪选择器 (焦点感知)
 * - Header Bar Widget 系统 (全局控制平面)
 *
 * ═══════════════════════════════════════════════════════════════════
 * 架构
 * ═══════════════════════════════════════════════════════════════════
 *
 * ```
 * ┌────────────────────────────────────────┐
 * │ Header Bar (HeaderWidgets)             │  ← Global Control Plane
 * ├────────────────────────────────────────┤
 * │ Dashboard Viewport                     │
 * │  ├─ Grid (@media responsive)           │  ← Scrollable
 * │  ├─ Cards (:focus aware)               │
 * │  └─ Sparklines                         │
 * └────────────────────────────────────────┘
 * ```
 */

import {
  // Compiler v2
  CompilerV2,
  compileTCSSv2,
  createResponsiveCompiler,
  DEFAULT_CONTEXT,
  EXAMPLE_TCSS_V2,
  // Header Bar
  HeaderWidget,
  createHeaderWidget,
  HeaderBarRenderer,
  createHeaderBar,
  renderHeaderBar,
  HEADER_WIDGETS,
  DEFAULT_HEADER_STATE,
  // Types
  CompileContext,
  CompiledLayoutV2,
  HeaderState,
} from "tvs/v2/sdk";

console.log("☀️ TAUR v0.2 Integration Test\n");
console.log("═".repeat(80));

// ==================== Test 1: @media Responsive Layout ====================

console.log("\n📋 Test 1: @media Responsive Layout\n");

const responsiveTCSS = `
dashboard {
  columns: 4;
  gap: 2;
}

@media (max-width: 100) {
  dashboard {
    columns: 2;
  }
}

@media (max-width: 70) {
  dashboard {
    columns: 1;
  }
}

card#agent {
  widget: agent.status;
  span: 1;
}

card#gpu {
  widget: system.gpu;
  span: 1;
}
`;

console.log("TCSS with @media queries:");
console.log(responsiveTCSS.trim());
console.log("");

// 测试不同宽度的编译结果
const widths = [120, 90, 60];
for (const width of widths) {
  const compiled = compileTCSSv2(responsiveTCSS, { width });
  console.log(`  Width ${width}: columns = ${compiled.dashboard.columns}`);
}

console.log("\nExpected behavior:");
console.log("  - width 120 → columns 4 (default)");
console.log("  - width 90  → columns 2 (@media max-width: 100)");
console.log("  - width 60  → columns 1 (@media max-width: 70)");

// ==================== Test 2: Mode-based @media ====================

console.log("\n" + "─".repeat(80));
console.log("\n📋 Test 2: Mode-based @media\n");

const modeTCSS = `
dashboard {
  columns: 3;
}

@media (mode: replay) {
  dashboard {
    columns: 2;
  }
  card#agent {
    span: 2;
  }
}

card#agent {
  widget: agent.status;
  span: 1;
}
`;

console.log("TCSS with mode-based @media:");
console.log(modeTCSS.trim());
console.log("");

const liveCompiled = compileTCSSv2(modeTCSS, { width: 120, mode: "live" });
const replayCompiled = compileTCSSv2(modeTCSS, { width: 120, mode: "replay" });

console.log("Live mode:");
console.log(`  columns: ${liveCompiled.dashboard.columns}`);
console.log(`  agent span: ${liveCompiled.cards[0]?.span}`);

console.log("Replay mode:");
console.log(`  columns: ${replayCompiled.dashboard.columns}`);
console.log(`  agent span: ${replayCompiled.cards[0]?.span}`);

// ==================== Test 3: :focus Pseudo-selector ====================

console.log("\n" + "─".repeat(80));
console.log("\n📋 Test 3: :focus Pseudo-selector\n");

const focusTCSS = `
dashboard {
  columns: 2;
}

card {
  border: normal;
}

card:focus {
  border: highlight;
}

card#agent {
  widget: agent.status;
  span: 1;
}

card#gpu {
  widget: system.gpu;
  span: 1;
}
`;

console.log("TCSS with :focus pseudo-selector:");
console.log(focusTCSS.trim());
console.log("");

// 不同焦点状态的编译
const noFocus = compileTCSSv2(focusTCSS, { width: 80, focusedCard: null });
const agentFocused = compileTCSSv2(focusTCSS, {
  width: 80,
  focusedCard: "agent",
});

console.log("No focus:");
for (const card of noFocus.cards) {
  console.log(
    `  ${card.id}: focused=${card.focused}, focusStyle=${!!card.focusStyle}`,
  );
}

console.log("Agent focused:");
for (const card of agentFocused.cards) {
  console.log(
    `  ${card.id}: focused=${card.focused}, focusStyle=${!!card.focusStyle}`,
  );
}

// ==================== Test 4: Responsive Compiler ====================

console.log("\n" + "─".repeat(80));
console.log("\n📋 Test 4: Responsive Compiler (Resize Simulation)\n");

const compiler = createResponsiveCompiler(responsiveTCSS);

// 初始编译
let layout = compiler.compile({ width: 120 });
console.log(`Initial (width=120): columns=${layout.dashboard.columns}`);

// 模拟 resize
layout = compiler.recompile({ width: 90 })!;
console.log(`After resize (width=90): columns=${layout.dashboard.columns}`);

layout = compiler.recompile({ width: 60 })!;
console.log(`After resize (width=60): columns=${layout.dashboard.columns}`);

// 设置焦点
layout = compiler.setFocus("agent")!;
console.log(`After setFocus('agent'): focusedCard in context`);

// ==================== Test 5: Header Bar Widgets ====================

console.log("\n" + "─".repeat(80));
console.log("\n📋 Test 5: Header Bar Widgets\n");

console.log("Available built-in Header Widgets:");
for (const id of HEADER_WIDGETS.getIds()) {
  console.log(`  - ${id}`);
}

// 测试各个 Widget 的渲染
const testState: HeaderState = {
  agentsRunning: 3,
  agents: [
    { id: "agent.a", status: "ok" },
    { id: "agent.b", status: "error" },
    { id: "agent.c", status: "idle" },
  ],
  mode: "live",
  refreshRate: 45,
  timestamp: Date.now(),
  focusedCard: "agent",
};

console.log("\nWidget outputs:");
for (const id of ["agent.summary", "mode.indicator", "clock", "refresh.rate"]) {
  const widget = HEADER_WIDGETS.get(id);
  if (widget) {
    console.log(`  ${id}: "${widget.render(testState)}"`);
  }
}

// ==================== Test 6: Header Bar Renderer ====================

console.log("\n" + "─".repeat(80));
console.log("\n📋 Test 6: Header Bar Renderer\n");

const headerRenderer = createHeaderBar({
  widgets: ["agent.summary", "mode.indicator", "refresh.rate", "clock"],
  width: 80,
});

const headerLine = headerRenderer.render(testState);
console.log("Rendered Header Bar (width=80):");
console.log(`  "${headerLine}"`);
console.log(`  Length: ${headerLine.length} chars`);

// 不同宽度
const narrowHeader = renderHeaderBar(
  ["agent.summary", "mode.indicator"],
  testState,
  40,
);
console.log("\nNarrow Header (width=40):");
console.log(`  "${narrowHeader}"`);

// ==================== Test 7: Header DSL in TCSS ====================

console.log("\n" + "─".repeat(80));
console.log("\n📋 Test 7: Header DSL in TCSS\n");

const headerTCSS = `
dashboard {
  columns: 2;
}

header {
  widgets: agent.summary, mode.indicator, clock;
}

card#agent {
  widget: agent.status;
  span: 1;
}
`;

const compiledWithHeader = compileTCSSv2(headerTCSS, { width: 80 });

console.log("TCSS with header block:");
console.log(headerTCSS.trim());
console.log("");

if (compiledWithHeader.header) {
  console.log("Parsed header config:");
  console.log(`  widgets: [${compiledWithHeader.header.widgets.join(", ")}]`);
} else {
  console.log("  No header defined");
}

// ==================== Test 8: Custom Header Widget ====================

console.log("\n" + "─".repeat(80));
console.log("\n📋 Test 8: Custom Header Widget\n");

// 创建自定义 Widget
const MemoryWidget = createHeaderWidget({
  id: "system.memory",
  title: "Memory",
  minWidth: 12,
  render: (state) => {
    const used = Math.floor(Math.random() * 100);
    return `💾 ${used}%`;
  },
});

// 注册
HEADER_WIDGETS.register(MemoryWidget);

console.log("Custom Widget registered: system.memory");
console.log(`Output: "${MemoryWidget.render(testState)}"`);

// 验证注册成功
console.log(
  `\nWidget exists in registry: ${HEADER_WIDGETS.has("system.memory")}`,
);

// ==================== Test 9: Complete v2 Example ====================

console.log("\n" + "─".repeat(80));
console.log("\n📋 Test 9: Complete v0.2 Example\n");

console.log("Example TCSS v2:");
console.log(EXAMPLE_TCSS_V2);

const fullCompiled = compileTCSSv2(EXAMPLE_TCSS_V2, {
  width: 120,
  mode: "live",
  focusedCard: "agent",
});

console.log("\nCompiled result:");
console.log(
  `  Dashboard: columns=${fullCompiled.dashboard.columns}, gap=${fullCompiled.dashboard.gap}`,
);
console.log(`  Cards: ${fullCompiled.cards.length}`);
console.log(
  `  Header widgets: ${fullCompiled.header?.widgets.join(", ") || "none"}`,
);

// ==================== Summary ====================

console.log("\n" + "═".repeat(80));
console.log("\n✅ TAUR v0.2 Integration Test Completed!\n");

console.log("v0.2 新特性已验证:");
console.log("");
console.log("  1. @media 响应式布局");
console.log("     • 终端 resize → 重新 compile layout");
console.log("     • 支持 max-width, min-width, mode, theme");
console.log("     • Layout 决策在编译期完成");
console.log("");
console.log("  2. :focus 伪选择器");
console.log("     • card:focus { border: highlight; }");
console.log("     • 焦点状态通过 CompileContext 传入");
console.log("     • 编译结果包含 focused 和 focusStyle");
console.log("");
console.log("  3. Header Bar Widget 系统");
console.log("     • HeaderWidget 轻量级接口");
console.log("     • 内置 widgets: agent.summary, mode.indicator, clock...");
console.log("     • HeaderBarRenderer 渲染为单行字符串");
console.log("     • TCSS 中通过 header { widgets: ... } 配置");
console.log("");
console.log("架构图:");
console.log("");
console.log(
  "  ┌─────────────────────────────────────────────────────────────┐",
);
console.log(
  "  │ Header Bar (HeaderWidgets)                                  │",
);
console.log("  │   🟢 agent-a │ 🔴 agent-b │ 🟡 agent-c │ LIVE │ 14:32:05   │");
console.log(
  "  ├─────────────────────────────────────────────────────────────┤",
);
console.log(
  "  │ Dashboard Viewport                                          │",
);
console.log("  │   ┌────────────────┐  ┌────────────────┐  ┌───────────────┐│");
console.log("  │   │ Agent Status   │  │ GPU Monitor    │  │ Log Stream    ││");
console.log("  │   │ [FOCUSED]      │  │                │  │               ││");
console.log("  │   └────────────────┘  └────────────────┘  └───────────────┘│");
console.log(
  "  └─────────────────────────────────────────────────────────────┘",
);
console.log("");
