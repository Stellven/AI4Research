#!/usr/bin/env npx tsx
/**
 * Solar Agent Dashboard Demo
 *
 * 使用 Solar UI 模块展示完整的 Agent 监控面板
 *
 * Usage:
 *   npx tsx demos/agent-dashboard.ts
 *   npx tsx demos/agent-dashboard.ts --layout=compact
 *   npx tsx demos/agent-dashboard.ts --layout=minimal
 */

import { SolarDashboard, type SolarLayoutPreset } from "../core/ui";

// 解析命令行参数
const args = process.argv.slice(2);
let layout: SolarLayoutPreset = "full";

for (const arg of args) {
  if (arg.startsWith("--layout=")) {
    layout = arg.split("=")[1] as SolarLayoutPreset;
  }
}

console.log("🚀 Starting Solar Agent Dashboard...\n");
console.log(`   Layout: ${layout}`);
console.log("   Press Ctrl+C to exit\n");

// 创建并启动 Dashboard
const dashboard = new SolarDashboard({
  layout,
  refreshHz: 2,
  title: "Solar Agent Dashboard",
});

dashboard.start();
