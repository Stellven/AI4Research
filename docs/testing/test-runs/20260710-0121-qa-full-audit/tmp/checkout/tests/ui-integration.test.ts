#!/usr/bin/env npx tsx
/**
 * Solar UI Integration Test
 *
 * 测试 Solar UI 模块与 TVS termplane 的集成
 */

import {
  // Dashboard
  SolarDashboard,
  // Widgets
  AgentStatusWidget,
  PhaseWidget,
  TaskQueueWidget,
  TokenWidget,
  LogWidget,
  // Quick functions
  renderBanner,
  renderStatusBar,
  renderAgentCard,
  renderProgressCard,
  renderStatsCard,
  // Layouts
  SOLAR_LAYOUTS,
} from "../core/ui";

console.log("🎨 Solar UI Integration Test\n");
console.log("═".repeat(60));

// ==================== Test 1: Banner ====================

console.log("\n📋 Test 1: renderBanner()\n");

const banner = renderBanner({
  project: "ThunderDuck",
  phase: "P3",
  agent: "💻 Coder",
  version: "v1.0.0",
});
console.log(banner);

// ==================== Test 2: Status Bar ====================

console.log("\n" + "─".repeat(60));
console.log("\n📋 Test 2: renderStatusBar()\n");

const statusBar = renderStatusBar({
  phase: "P3",
  agent: "Coder→Guard",
  tokens: 12456,
  rate: 45,
});
console.log(statusBar);

// ==================== Test 3: Quick Widgets ====================

console.log("\n" + "─".repeat(60));
console.log("\n📋 Test 3: Quick Widgets\n");

// Agent Card
console.log("Agent Card:");
const agentCard = renderAgentCard([
  { name: "Researcher", status: "idle" },
  { name: "Coder", status: "running" },
  { name: "Tester", status: "running" },
]);
console.log(agentCard);

console.log("\nProgress Card:");
const progressCard = renderProgressCard("Build Progress", 0.75, "Release");
console.log(progressCard);

console.log("\nStats Card:");
const statsCard = renderStatsCard("System", [
  { key: "CPU", value: "45%", status: "success" },
  { key: "Memory", value: "62%", status: "warning" },
  { key: "Tokens", value: "12.4K" },
]);
console.log(statsCard);

// ==================== Test 4: Widget Classes ====================

console.log("\n" + "─".repeat(60));
console.log("\n📋 Test 4: Widget Classes\n");

const widgets = [
  { name: "AgentStatusWidget", widget: new AgentStatusWidget() },
  { name: "PhaseWidget", widget: new PhaseWidget() },
  { name: "TaskQueueWidget", widget: new TaskQueueWidget() },
  { name: "TokenWidget", widget: new TokenWidget() },
  { name: "LogWidget", widget: new LogWidget() },
];

widgets.forEach(({ name, widget }) => {
  console.log(`✓ ${name}`);
  console.log(`  id: ${widget.id}`);
  console.log(`  title: ${widget.title}`);
});

// ==================== Test 5: Layouts ====================

console.log("\n" + "─".repeat(60));
console.log("\n📋 Test 5: Layout Presets\n");

Object.entries(SOLAR_LAYOUTS).forEach(([name, layout]) => {
  console.log(`${name}:`);
  console.log(`  columns: ${layout.columns}`);
  console.log(`  widgets: ${layout.widgets.length}`);
  console.log(`  width: ${layout.width}`);
});

// ==================== Test 6: Dashboard Render ====================

console.log("\n" + "─".repeat(60));
console.log("\n📋 Test 6: Dashboard Render (minimal layout)\n");

const dashboard = new SolarDashboard({
  layout: "minimal",
  width: 60,
  showHeader: false,
  showFooter: false,
});

console.log(dashboard.renderOnce());

// ==================== Summary ====================

console.log("\n" + "═".repeat(60));
console.log("\n✅ Solar UI Integration Test 完成!\n");
console.log("使用方式:");
console.log("  import { SolarDashboard, renderBanner } from 'solar/core/ui';");
console.log("  ");
console.log("  // 快速启动 Dashboard");
console.log("  const dashboard = new SolarDashboard({ layout: 'full' });");
console.log("  dashboard.start();");
console.log("  ");
console.log("  // 或使用快捷函数");
console.log("  console.log(renderBanner({ project: 'MyProject' }));");
