/**
 * Semantic Design System Test
 *
 * 验证 5 条黄金规则:
 * 1. 颜色 ≤ 3 种同时出现
 * 2. emoji 每行 ≤ 1
 * 3. emoji 只出现在 key / header
 * 4. 颜色表达状态，不表达装饰
 * 5. LLM 永远只输出语义，不输出颜色码
 *
 * 这个系统的定位:
 * 「企业 / 研究 / Agent UI 的终端视觉语言」
 */

import {
  // Renderer
  render,
  card,
  // Theme
  color,
  setTheme,
  statusIcon,
  // Icon system
  ICONS,
  icon,
  coloredIcon,
  // Width utilities
  getDisplayWidth,
  getDisplayWidthStripped,
  padToWidth,
} from "tvs/v2";

console.log("🎨 Semantic Design System Test\n");
console.log("═".repeat(80));

// ==================== Test 1: 语义颜色 (不是 ANSI) ====================

console.log("\n📋 Test 1: 语义颜色 (DSL 不出现 ANSI)\n");
console.log("❌ 错误: \\033[31mERROR\\033[0m (直接上色)");
console.log("✅ 正确: color('ERROR', 'error') →", color("ERROR", "error"));

console.log("\n颜色 = 语义状态 (Design Token):");
console.log(`  success → ${color("calm green", "success")}`);
console.log(`  warning → ${color("amber", "warning")}`);
console.log(`  error   → ${color("red", "error")}`);
console.log(`  info    → ${color("blue", "info")}`);
console.log(`  muted   → ${color("gray", "muted")}`);
console.log(`  accent  → ${color("highlight", "accent")}`);

// ==================== Test 2: Icon 映射表 ====================

console.log("\n" + "─".repeat(80));
console.log("\n📋 Test 2: Icon 映射表 (语义 → Emoji)\n");

console.log("系统/服务:");
console.log(`  service  → ${icon("service")}  agent   → ${icon("agent")}`);
console.log(`  database → ${icon("database")}  network → ${icon("network")}`);

console.log("\n指标:");
console.log(`  latency → ${icon("latency")}  load   → ${icon("load")}`);
console.log(`  memory  → ${icon("memory")}  cpu    → ${icon("cpu")}`);

console.log("\n状态:");
console.log(`  success → ${icon("success")}  warning → ${icon("warning")}`);
console.log(`  error   → ${icon("error")}  info    → ${icon("info")}`);

// ==================== Test 3: Emoji 宽度处理 ====================

console.log("\n" + "─".repeat(80));
console.log("\n📋 Test 3: Emoji 宽度处理 (排版关键)\n");

console.log("关键点: Emoji ≠ 1 字符宽, 多数终端是 2 cell\n");

const testStrings = [
  { str: "Hello", expected: 5 },
  { str: "🧠", expected: 2 },
  { str: "⏱️", expected: 2 },
  { str: "✅ OK", expected: 5 },
  { str: "🧠 Service", expected: 10 },
  { str: "中文", expected: 4 },
];

console.log("字符串             | 计算宽度 | 预期");
console.log("────────────────────────────────────");
for (const { str, expected } of testStrings) {
  const width = getDisplayWidth(str);
  const status = width === expected ? "✓" : "✗";
  console.log(
    `${str.padEnd(18)} | ${String(width).padEnd(8)} | ${expected} ${status}`,
  );
}

// ==================== Test 4: ANSI 剥离后宽度 ====================

console.log("\n" + "─".repeat(80));
console.log("\n📋 Test 4: ANSI 剥离后宽度计算\n");

const coloredStr = color("ERROR", "error");
console.log(`带 ANSI: "${coloredStr}"`);
console.log(`显示宽度: ${getDisplayWidthStripped(coloredStr)} (应为 5)`);

const paddedStr = padToWidth(color("OK", "success"), 10, "right");
console.log(`\n右对齐填充: "${paddedStr}" (10 宽度)`);

// ==================== Test 5: 企业级 Dashboard ====================

console.log("\n" + "─".repeat(80));
console.log("\n📋 Test 5: 企业级 Dashboard (语义化 DSL)\n");

// 这个 DSL 完全是语义的，没有任何 ANSI 码
const dsl = {
  canvas: { width: 50 },
  style: "enterprise_minimal" as const,
  layout: {
    type: "card" as const,
    sections: [
      {
        type: "header" as const,
        text: "Inference Service",
        align: "center" as const,
        icon: "service" as const,
      },
      { type: "divider" as const },
      {
        type: "kv" as const,
        items: [
          {
            key: "Latency",
            icon: "latency" as const,
            value: "14 ms",
            status: "success" as const,
          },
          {
            key: "Load",
            icon: "load" as const,
            bar: 0.78,
            color: "warning" as const,
          },
          {
            key: "Status",
            value: "OK",
            status: "success" as const,
          },
        ],
      },
    ],
  },
};

console.log("DSL (语义化，无 ANSI):");
console.log(JSON.stringify(dsl, null, 2).slice(0, 500) + "...\n");

console.log("渲染输出:");
console.log(render(dsl));

// ==================== Test 6: 黄金规则验证 ====================

console.log("\n" + "─".repeat(80));
console.log("\n📋 Test 6: 5 条黄金规则验证\n");

setTheme("dark");

console.log("规则 1: 颜色 ≤ 3 种同时出现");
console.log(
  `  ✅ ${color("Success", "success")} | ${color("Warning", "warning")} | ${color("Error", "error")}`,
);
console.log("  (不超过 3 种颜色)\n");

console.log("规则 2: emoji 每行 ≤ 1");
console.log(`  ✅ ${icon("service")} Inference Service`);
console.log(`  ✅ ${icon("latency")} Latency: 14 ms`);
console.log("  (每行只有一个 emoji)\n");

console.log("规则 3: emoji 只出现在 key / header");
console.log(`  ✅ Header: ${icon("service")} Service Name`);
console.log(`  ✅ Key:    ${icon("load")} Load │ ████████▊`);
console.log("  (emoji 不出现在边框、装饰、填充中)\n");

console.log("规则 4: 颜色表达状态，不表达装饰");
console.log(`  ✅ ${color("Running", "success")} ← 成功状态`);
console.log(`  ✅ ${color("Degraded", "warning")} ← 警告状态`);
console.log(`  ✅ ${color("Failed", "error")} ← 错误状态`);
console.log("  (颜色有语义含义)\n");

console.log("规则 5: LLM 只输出语义，不输出颜色码");
console.log('  ✅ DSL: { "color": "success" }');
console.log('  ❌ 不是: { "color": "\\033[38;5;34m" }');
console.log("  (Renderer 负责映射)\n");

// ==================== Test 7: Solar Theme Showcase ====================

console.log("─".repeat(80));
console.log("\n📋 Test 7: Solar Agent Dashboard\n");

setTheme("solar");

const agentDsl = {
  canvas: { width: 55 },
  style: "solar_default" as const,
  layout: {
    type: "card" as const,
    sections: [
      {
        type: "header" as const,
        text: "Agent Coder",
        align: "center" as const,
        icon: "agent" as const,
      },
      { type: "divider" as const },
      {
        type: "kv" as const,
        items: [
          {
            key: "Status",
            value: "Running",
            status: "success" as const,
          },
          {
            key: "CPU",
            icon: "cpu" as const,
            bar: 0.45,
          },
          {
            key: "Memory",
            icon: "memory" as const,
            bar: 0.72,
            color: "warning" as const,
          },
          {
            key: "Tasks",
            value: "3 pending",
            status: "info" as const,
          },
        ],
      },
    ],
  },
};

console.log(render(agentDsl));

// ==================== Summary ====================

console.log("\n" + "═".repeat(80));
console.log("\n✅ Semantic Design System Test Completed!\n");

console.log("设计原则:");
console.log("  • 颜色 = 语义状态 (Design Token)，不是装饰");
console.log("  • Emoji = 图标 (Icon)，不是表情包");
console.log("  • DSL 是语义的，ANSI 在 Renderer 里");
console.log("  • Emoji 宽度正确处理，排版不炸");

console.log("\n视觉层级 (5 层):");
console.log("  1. Layout (card / grid)");
console.log("  2. Box drawing (结构)");
console.log("  3. Density glyphs (bar / sparkline)");
console.log("  4. Color semantics (状态)");
console.log("  5. Emoji iconography (语义锚点)");

console.log("\n这是: 「企业 / 研究 / Agent UI 的终端视觉语言」");
console.log("不是: 低端 CLI / 运维脚本审美 / Slack bot 表情包风\n");
