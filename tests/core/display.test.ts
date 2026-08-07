/**
 * Display Module Test
 *
 * 测试 TUI 显示服务器:
 * - ANSI 转义序列
 * - Region 分区系统
 * - Display 集成
 */

import {
  // ANSI
  cursor,
  screen,
  style,
  fg,
  bg,
  stripAnsi,
  visibleLength,
  writeAt,
  // Region
  Region,
  RegionManager,
  // Display
  Display,
  createDisplay,
} from "tvs/v2/display";

console.log("☀️ Display Module Test\n");
console.log("═".repeat(80));

// ==================== Test 1: ANSI Sequences ====================

console.log("\n📋 Test 1: ANSI Escape Sequences\n");

console.log("Cursor commands:");
console.log(`  cursor.hide: ${JSON.stringify(cursor.hide)}`);
console.log(`  cursor.show: ${JSON.stringify(cursor.show)}`);
console.log(`  cursor.moveTo(5, 10): ${JSON.stringify(cursor.moveTo(5, 10))}`);
console.log(`  cursor.up(3): ${JSON.stringify(cursor.up(3))}`);

console.log("\nScreen commands:");
console.log(`  screen.clear: ${JSON.stringify(screen.clear)}`);
console.log(`  screen.enterAlt: ${JSON.stringify(screen.enterAlt)}`);
console.log(
  `  screen.setScrollRegion(2, 10): ${JSON.stringify(screen.setScrollRegion(2, 10))}`,
);

console.log("\nStyle commands:");
console.log(`  style.bold: ${JSON.stringify(style.bold)}`);
console.log(`  style.reset: ${JSON.stringify(style.reset)}`);

// ==================== Test 2: ANSI Utilities ====================

console.log("\n" + "─".repeat(80));
console.log("\n📋 Test 2: ANSI Utilities\n");

const coloredText = `${fg.green}Hello${style.reset} ${fg.red}World${style.reset}`;
console.log(`Original: ${coloredText}`);
console.log(`Stripped: ${stripAnsi(coloredText)}`);
console.log(`Visible length: ${visibleLength(coloredText)}`);

// ==================== Test 3: Region ====================

console.log("\n" + "─".repeat(80));
console.log("\n📋 Test 3: Region System\n");

const region = new Region(
  { name: "test", height: 5, scrollable: true },
  { top: 1, bottom: 5, height: 5, width: 40 },
);

// 设置内容
region.setContent([
  "Line 1: First line",
  "Line 2: Second line",
  "Line 3: Third line",
  "Line 4: Fourth line",
  "Line 5: Fifth line",
  "Line 6: Sixth line (scrollable)",
  "Line 7: Seventh line",
]);

console.log("Region info:");
console.log(`  name: ${region.name}`);
console.log(`  height: ${region.height}`);
console.log(`  contentHeight: ${region.contentHeight}`);
console.log(`  scrollable: ${region.scrollable}`);
console.log(`  scrollOffset: ${region.scrollOffset}`);

console.log("\nVisible lines (before scroll):");
for (const line of region.getVisibleLines()) {
  console.log(`  ${line}`);
}

// 滚动
region.scroll(2);
console.log("\nVisible lines (after scroll by 2):");
console.log(`  scrollOffset: ${region.scrollOffset}`);
for (const line of region.getVisibleLines()) {
  console.log(`  ${line}`);
}

// ==================== Test 4: RegionManager ====================

console.log("\n" + "─".repeat(80));
console.log("\n📋 Test 4: RegionManager\n");

const manager = new RegionManager(80, 24);
const layout = manager.createStandardLayout({
  headerHeight: 1,
  footerHeight: 1,
});

console.log("Standard layout created:");
console.log(
  `  header: top=${layout.header.bounds.top}, height=${layout.header.height}`,
);
console.log(
  `  body: top=${layout.body.bounds.top}, height=${layout.body.height}`,
);
if (layout.footer) {
  console.log(
    `  footer: top=${layout.footer.bounds.top}, height=${layout.footer.height}`,
  );
}

// 设置内容
layout.header.setLine(
  0,
  " 🟢 agent-a │ 🟡 agent-b │ 🔵 agent-c │ LIVE │ Rate: 45% ",
);
layout.body.setContent([
  "┌─────────────────────────────────────────────────────────────────────────────┐",
  "│                              Dashboard Body                                  │",
  "├─────────────────────────────────────────────────────────────────────────────┤",
  "│ This is the scrollable content area.                                         │",
  "│ You can scroll up and down with j/k keys.                                   │",
  "│                                                                              │",
  "│ Line 1                                                                       │",
  "│ Line 2                                                                       │",
  "│ Line 3                                                                       │",
  "│ Line 4                                                                       │",
  "│ Line 5                                                                       │",
  "│ Line 6                                                                       │",
  "│ Line 7                                                                       │",
  "│ Line 8                                                                       │",
  "│ Line 9                                                                       │",
  "│ Line 10                                                                      │",
  "└─────────────────────────────────────────────────────────────────────────────┘",
]);
if (layout.footer) {
  layout.footer.setLine(
    0,
    " [q] Quit  [j/k] Scroll  [g/G] Top/Bottom  [?] Help ",
  );
}

console.log("\nHeader content:");
console.log(`  ${layout.header.getLine(0)}`);

console.log("\nBody visible lines:");
for (const line of layout.body.getVisibleLines().slice(0, 5)) {
  console.log(`  ${line}`);
}
console.log("  ...");

// ==================== Test 5: Display Config ====================

console.log("\n" + "─".repeat(80));
console.log("\n📋 Test 5: Display Configuration\n");

const display = createDisplay({
  alternateScreen: true,
  hideCursor: true,
  headerHeight: 1,
  footerHeight: 1,
  title: "TAUR Dashboard",
  fps: 30,
});

console.log("Display created (not started):");
console.log(`  state: ${display.getState()}`);

// 注意: 不实际启动 Display，因为会进入 TUI 模式

// ==================== Test 6: Architecture Diagram ====================

console.log("\n" + "─".repeat(80));
console.log("\n📋 Test 6: TUI Architecture\n");

console.log(
  "┌─────────────────────────────────────────────────────────────────────────────┐",
);
console.log(
  "│                          TUI Display Server                                 │",
);
console.log(
  "├─────────────────────────────────────────────────────────────────────────────┤",
);
console.log(
  "│                                                                             │",
);
console.log(
  "│  ┌───────────────────────────────────────────────────────────────────────┐ │",
);
console.log(
  "│  │ Header (Fixed, size=1)                                                │ │",
);
console.log(
  "│  │ 🟢 agent-a │ 🟡 agent-b │ 🔵 agent-c │ LIVE │ Rate: 45%               │ │",
);
console.log(
  "│  ├───────────────────────────────────────────────────────────────────────┤ │",
);
console.log(
  "│  │ Body (Scrollable)                                                     │ │",
);
console.log(
  "│  │                                                                       │ │",
);
console.log(
  "│  │   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                  │ │",
);
console.log(
  "│  │   │   Widget    │  │   Widget    │  │   Widget    │                  │ │",
);
console.log(
  "│  │   │   Card 1    │  │   Card 2    │  │   Card 3    │                  │ │",
);
console.log(
  "│  │   └─────────────┘  └─────────────┘  └─────────────┘                  │ │",
);
console.log(
  "│  │                                                                       │ │",
);
console.log(
  "│  ├───────────────────────────────────────────────────────────────────────┤ │",
);
console.log(
  "│  │ Footer (Fixed, size=1)                                                │ │",
);
console.log(
  "│  │ [q] Quit  [j/k] Scroll  [g/G] Top/Bottom  [?] Help                   │ │",
);
console.log(
  "│  └───────────────────────────────────────────────────────────────────────┘ │",
);
console.log(
  "│                                                                             │",
);
console.log(
  "└─────────────────────────────────────────────────────────────────────────────┘",
);

// ==================== Summary ====================

console.log("\n" + "═".repeat(80));
console.log("\n✅ Display Module Test Completed!\n");

console.log("TUI Display Server 实现要点:");
console.log("");
console.log("  1. 接管终端:");
console.log("     • 进入 Alternate Screen Buffer");
console.log("     • 隐藏光标");
console.log("     • 自己管理屏幕缓冲区");
console.log("");
console.log("  2. 区域分离:");
console.log("     • Header (固定顶部, 不滚动)");
console.log("     • Body (可滚动)");
console.log("     • Footer (固定底部)");
console.log("");
console.log("  3. 增量刷新:");
console.log("     • 只刷新脏区域");
console.log("     • 减少闪烁");
console.log("");
console.log("  4. 优雅退出:");
console.log("     • 恢复光标");
console.log("     • 退出 Alternate Screen");
console.log("     • 重置样式");
console.log("");
