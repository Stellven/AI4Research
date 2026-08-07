/**
 * Theme / Color Profile System Test
 *
 * 测试:
 * - 语义颜色应用
 * - 终端检测
 * - 主题切换
 * - 与 Renderer 集成
 */

import {
  // Theme exports
  ThemeManager,
  getThemeManager,
  color,
  setTheme,
  getCurrentTheme,
  statusIcon,
  detectTerminalMode,
  detectColorSupport,
  THEMES,
  STATUS_ICONS,
  // Renderer exports
  render,
  card,
} from "tvs/v2";

console.log("🎨 Theme / Color Profile System Test\n");
console.log("═".repeat(80));

// ==================== Test 1: Terminal Detection ====================

console.log("\n📋 Test 1: Terminal Detection\n");

const terminalMode = detectTerminalMode();
const colorSupport = detectColorSupport();

console.log(`Terminal Mode: ${terminalMode}`);
console.log(`Color Support: ${colorSupport}`);

// ==================== Test 2: Theme Manager ====================

console.log("\n" + "─".repeat(80));
console.log("\n📋 Test 2: Theme Manager\n");

const tm = getThemeManager();
console.log(`Current Theme: ${tm.getTheme().name}`);
console.log(`Available Themes: ${tm.listThemes().join(", ")}`);

// ==================== Test 3: Color Application ====================

console.log("\n" + "─".repeat(80));
console.log("\n📋 Test 3: Color Application (语义颜色)\n");

console.log(color("This is success text", "success"));
console.log(color("This is warning text", "warning"));
console.log(color("This is error text", "error"));
console.log(color("This is info text", "info"));
console.log(color("This is muted text", "muted"));
console.log(color("This is accent text", "accent"));
console.log(color("This is heading text", "heading"));
console.log(color("This is highlight text", "highlight"));

// ==================== Test 4: Status Icons ====================

console.log("\n" + "─".repeat(80));
console.log("\n📋 Test 4: Status Icons (带颜色)\n");

console.log(`Success: ${statusIcon("success")} Operation completed`);
console.log(`Warning: ${statusIcon("warning")} Deprecated API`);
console.log(`Error:   ${statusIcon("error")} Connection failed`);
console.log(`Info:    ${statusIcon("info")} New version available`);
console.log(`Pending: ${statusIcon("pending")} Waiting for input`);
console.log(`Active:  ${statusIcon("active")} Currently running`);

// ==================== Test 5: Theme Switching ====================

console.log("\n" + "─".repeat(80));
console.log("\n📋 Test 5: Theme Switching\n");

const themes = ["dark", "light", "solar", "cyber", "mono"];

for (const themeName of themes) {
  setTheme(themeName);
  console.log(`\n[${themeName.toUpperCase()}]`);
  console.log(
    `  ${color("Success", "success")} | ${color("Warning", "warning")} | ${color("Error", "error")} | ${color("Info", "info")}`,
  );
}

// Reset to dark for remaining tests
setTheme("dark");

// ==================== Test 6: Renderer Integration ====================

console.log("\n" + "─".repeat(80));
console.log("\n📋 Test 6: Renderer Integration (Card with Colors)\n");

const coloredCard = card(
  "Agent Status",
  [
    { key: "Service", value: "Inference Engine" },
    { key: "Status", value: "Running", status: "success" },
    { key: "Health", value: "Degraded", status: "warning" },
    { key: "Error", value: "Connection timeout", status: "error" },
    { key: "Load", bar: 0.72 },
  ],
  { width: 60, style: "enterprise_minimal" },
);

console.log(coloredCard);

// ==================== Test 7: Full DSL with Colors ====================

console.log("\n" + "─".repeat(80));
console.log("\n📋 Test 7: Full DSL with Colors\n");

const fullDsl = render({
  canvas: { width: 60 },
  style: "solar_default",
  layout: {
    type: "card",
    sections: [
      { type: "header", text: "System Dashboard", align: "center" },
      { type: "divider" },
      {
        type: "kv",
        items: [
          { key: "CPU", value: "45%", status: "success" },
          { key: "Memory", value: "78%", status: "warning" },
          { key: "Disk", value: "92%", status: "error" },
          { key: "Network", bar: 0.35 },
        ],
      },
      { type: "divider", label: "Agents" },
      {
        type: "list",
        variant: "checkbox",
        items: [
          { text: "Coder Agent", checked: true, status: "success" },
          { text: "Tester Agent", checked: true, status: "info" },
          { text: "Reviewer Agent", checked: false, status: "warning" },
        ],
      },
    ],
  },
});

console.log(fullDsl);

// ==================== Test 8: Solar Theme Showcase ====================

console.log("\n" + "─".repeat(80));
console.log("\n📋 Test 8: Solar Theme Showcase\n");

setTheme("solar");

console.log(
  color("┌─ ☀️ Solar ──────────────────────────────────────┐", "border"),
);
console.log(
  color("│", "border") +
    color(" Solar Multi-Agent Development Framework  ", "heading") +
    color("│", "border"),
);
console.log(
  color("├─────────────────────────────────────────────────┤", "border"),
);
console.log(
  color("│", "border") +
    ` Phase: ${color("P3 Implementation", "accent")}                        ` +
    color("│", "border"),
);
console.log(
  color("│", "border") +
    ` Agent: ${color("💻 Coder", "info")}                                ` +
    color("│", "border"),
);
console.log(
  color("│", "border") +
    ` Status: ${statusIcon("success")} ${color("Running", "success")}                          ` +
    color("│", "border"),
);
console.log(
  color("└─────────────────────────────────────────────────┘", "border"),
);

// ==================== Test 9: Cyber Theme Showcase ====================

console.log("\n" + "─".repeat(80));
console.log("\n📋 Test 9: Cyber Theme Showcase\n");

setTheme("cyber");

console.log(
  color("╔══════════════════════════════════════════════════╗", "border"),
);
console.log(
  color("║", "border") +
    color(" NEURAL INTERFACE ONLINE ", "heading").padEnd(50) +
    color("║", "border"),
);
console.log(
  color("╠══════════════════════════════════════════════════╣", "border"),
);
console.log(
  color("║", "border") +
    ` ${color("SYSTEM", "muted")}   ${color("ACTIVE", "success")}                                 ` +
    color("║", "border"),
);
console.log(
  color("║", "border") +
    ` ${color("NETWORK", "muted")}  ${color("SCANNING", "warning")}                              ` +
    color("║", "border"),
);
console.log(
  color("║", "border") +
    ` ${color("ALERT", "muted")}    ${color("INTRUSION DETECTED", "error")}                     ` +
    color("║", "border"),
);
console.log(
  color("╚══════════════════════════════════════════════════╝", "border"),
);

// ==================== Summary ====================

console.log("\n" + "═".repeat(80));
console.log("\n✅ All Theme tests completed!\n");

setTheme("dark"); // Reset

console.log("特性:");
console.log(
  "  • 语义颜色角色: fg/bg/border/heading/success/warning/error/info/muted/accent/highlight",
);
console.log("  • 终端自动检测: dark/light mode, 256/truecolor support");
console.log("  • 预置主题: dark/light/solar/cyber/mono");
console.log("  • Renderer 集成: header/status/kv 自动着色");
console.log("\n使用方式:");
console.log("  color(text, role)    // 应用语义颜色");
console.log("  setTheme(name)       // 切换主题");
console.log("  statusIcon(status)   // 获取带颜色图标");
console.log("  getThemeManager()    // 获取 ThemeManager 实例");
