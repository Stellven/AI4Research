/**
 * Console System Test
 *
 * 测试三维一体设计:
 * - Viewport = 空间管理 (虚拟画布裁剪)
 * - Keybinding = 状态切换 (键盘驱动状态机)
 * - Snapshot = 时间维度 (历史回放)
 *
 * 注: 这是非交互式测试，验证核心逻辑
 */

import {
  // Viewport
  Viewport,
  applyViewport,
  // Keybinding
  DEFAULT_KEYBINDINGS,
  parseKeySequence,
  // Snapshot
  SnapshotBuffer,
  // State
  createConsoleState,
  handleKeyAction,
  // Help
  renderHelpPanel,
  // Types
  KeyAction,
} from "tvs/v2";

console.log("🎮 Console System Test\n");
console.log("═".repeat(80));

// ==================== Test 1: Viewport ====================

console.log("\n📋 Test 1: Viewport / Scroll\n");

const vp = new Viewport(0, 0, 40, 10);

console.log(`Initial viewport: (${vp.x}, ${vp.y}) ${vp.width}x${vp.height}`);

// 模拟滚动
vp.scroll(5, 3, 100, 50);
console.log(`After scroll(5, 3): (${vp.x}, ${vp.y})`);

vp.scroll(-10, 0, 100, 50); // 不能超出左边界
console.log(`After scroll(-10, 0): (${vp.x}, ${vp.y}) (clamped)`);

vp.goto(50, 40, 100, 50);
console.log(`After goto(50, 40): (${vp.x}, ${vp.y})`);

vp.reset();
console.log(`After reset(): (${vp.x}, ${vp.y})`);

// ==================== Test 2: applyViewport ====================

console.log("\n" + "─".repeat(80));
console.log("\n📋 Test 2: applyViewport (Frame Clipping)\n");

// 创建一个大的虚拟画布
const fullFrame: string[] = [];
for (let i = 0; i < 20; i++) {
  fullFrame.push(
    `Line ${String(i).padStart(2, "0")}: ${"*".repeat(i + 1).padEnd(60, "-")}`,
  );
}

console.log("Full frame (20 lines, ~60 chars wide):");
console.log(fullFrame.slice(0, 3).join("\n"));
console.log("...");

// 创建小视口
const smallVp = new Viewport(10, 5, 30, 5);
console.log(
  `\nViewport: x=${smallVp.x}, y=${smallVp.y}, ${smallVp.width}x${smallVp.height}`,
);

const visibleFrame = applyViewport(fullFrame, smallVp);
console.log("\nVisible frame after clipping:");
console.log(visibleFrame.join("\n"));

// ==================== Test 3: Keybinding ====================

console.log("\n" + "─".repeat(80));
console.log("\n📋 Test 3: Keybinding System\n");

console.log("Default keybindings:");
const keyTable: Array<{ key: string; action: string }> = [
  { key: "h", action: "scroll left" },
  { key: "j", action: "scroll down" },
  { key: "k", action: "scroll up" },
  { key: "l", action: "scroll right" },
  { key: "Tab", action: "focus next" },
  { key: "r", action: "enter replay" },
  { key: "Esc", action: "return to live" },
  { key: "q", action: "quit" },
];

for (const { key, action } of keyTable) {
  console.log(`  ${key.padEnd(8)} → ${action}`);
}

// 测试按键解析
console.log("\nKey sequence parsing:");
const testKeys = [
  { input: "h", expected: "h" },
  { input: "\x1b[A", expected: "\x1b[A" }, // ↑
  { input: "\x1b[B", expected: "\x1b[B" }, // ↓
  { input: "\x1b[5~", expected: "\x1b[5~" }, // PageUp
];

for (const { input, expected } of testKeys) {
  const parsed = parseKeySequence(input);
  const status = parsed === expected ? "✓" : "✗";
  const display = input
    .replace("\x1b", "ESC")
    .replace("[A", "[A↑")
    .replace("[B", "[B↓");
  console.log(`  ${display.padEnd(12)} → ${status}`);
}

// ==================== Test 4: Snapshot Buffer ====================

console.log("\n" + "─".repeat(80));
console.log("\n📋 Test 4: Snapshot Buffer (Ring Buffer)\n");

const snapshots = new SnapshotBuffer(10); // 最多 10 个

// 添加快照
for (let i = 0; i < 15; i++) {
  snapshots.push({
    frame: [`Frame ${i}`],
    timestamp: Date.now() - (15 - i) * 1000,
    metrics: { value: i },
  });
}

console.log(`Buffer length: ${snapshots.length} (max 10)`);
console.log(`Latest: ${snapshots.latest()?.frame[0]}`);
console.log(`Index -1: ${snapshots.get(-1)?.frame[0]}`);
console.log(`Index -5: ${snapshots.get(-5)?.frame[0]}`);
console.log(`Index -10: ${snapshots.get(-10)?.frame[0]}`);
console.log(`Index -11: ${snapshots.get(-11)} (out of range)`);

// ==================== Test 5: State Machine ====================

console.log("\n" + "─".repeat(80));
console.log("\n📋 Test 5: Console State Machine\n");

let state = createConsoleState({ width: 80, height: 24 });

console.log("Initial state:");
console.log(`  mode: ${state.mode}`);
console.log(`  focusIndex: ${state.focusIndex}`);
console.log(`  viewport: (${state.viewport.x}, ${state.viewport.y})`);
console.log(`  replayIndex: ${state.replayIndex}`);

// 模拟状态变化
state.cardCount = 5;
state.frameWidth = 200;
state.frameHeight = 100;

// 测试 focus_next
const action1: KeyAction = { type: "focus_next" };
state = handleKeyAction(state, action1);
console.log(`\nAfter focus_next: focusIndex = ${state.focusIndex}`);

// 测试 scroll
const action2: KeyAction = { type: "scroll", dx: 10, dy: 5 };
state = handleKeyAction(state, action2);
console.log(
  `After scroll(10, 5): viewport = (${state.viewport.x}, ${state.viewport.y})`,
);

// 测试 mode 切换
const action3: KeyAction = { type: "mode", mode: "replay" };
state = handleKeyAction(state, action3);
console.log(`After mode('replay'): mode = ${state.mode}`);

// 测试 replay 导航
state.snapshots.push({ frame: ["test1"], timestamp: Date.now() - 3000 });
state.snapshots.push({ frame: ["test2"], timestamp: Date.now() - 2000 });
state.snapshots.push({ frame: ["test3"], timestamp: Date.now() - 1000 });

const action4: KeyAction = { type: "replay_prev" };
state = handleKeyAction(state, action4);
console.log(`After replay_prev: replayIndex = ${state.replayIndex}`);

const action5: KeyAction = { type: "mode", mode: "live" };
state = handleKeyAction(state, action5);
console.log(
  `After mode('live'): mode = ${state.mode}, replayIndex = ${state.replayIndex}`,
);

// ==================== Test 6: Help Panel ====================

console.log("\n" + "─".repeat(80));
console.log("\n📋 Test 6: Help Panel\n");

console.log(renderHelpPanel(DEFAULT_KEYBINDINGS));

// ==================== Test 7: 完整系统架构图 ====================

console.log("\n" + "─".repeat(80));
console.log("\n📋 Test 7: 完整系统架构\n");

console.log("┌──────────────┐");
console.log("│ Input (Key)  │ ← Raw key capture");
console.log("└─────┬────────┘");
console.log("      ↓");
console.log("┌──────────────┐");
console.log("│ State Update │ ← focus / viewport / mode");
console.log("└─────┬────────┘");
console.log("      ↓");
console.log("┌──────────────┐");
console.log("│ Render Full  │ ← Grid + Card + Sparkline");
console.log("└─────┬────────┘");
console.log("      ↓");
console.log("┌──────────────┐");
console.log("│ Viewport Cut │ ← applyViewport()");
console.log("└─────┬────────┘");
console.log("      ↓");
console.log("┌──────────────┐");
console.log("│ Diff Refresh │ ← FrameBuffer.diff()");
console.log("└──────────────┘");

// ==================== Summary ====================

console.log("\n" + "═".repeat(80));
console.log("\n✅ Console System Test Completed!\n");

console.log("三维一体设计:");
console.log("  • Viewport = 空间管理 (虚拟画布裁剪)");
console.log("  • Keybinding = 状态切换 (键盘驱动状态机)");
console.log("  • Snapshot = 时间维度 (历史回放)");

console.log("\n核心原则:");
console.log("  • 所有交互 = 改 state");
console.log("  • state 改变 → 重渲染");
console.log("  • 显示层只做 diff");
console.log("  • Renderer 永远无副作用");

console.log("\n产品级能力:");
console.log("  • 超大 Dashboard (Viewport scroll)");
console.log("  • 卡片焦点系统 (Tab 切换)");
console.log("  • 时间回放 (Replay mode)");
console.log("  • Vim 风格操作 (hjkl)");
console.log("  • SSH 友好 (纯终端)");

console.log("\n使用场景:");
console.log("  • Agent 实时控制台");
console.log("  • AIOS system dashboard");
console.log("  • 研究实验监控");
console.log("  • Multi-Agent orchestration UI");
console.log("  • TUI 版 LangGraph / AutoGPT Monitor\n");
