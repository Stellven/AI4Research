/**
 * Realtime Visualization Engine Test
 *
 * 测试:
 * - Braille Sparkline (连续折线)
 * - Time Series Buffer
 * - Frame Buffer Diff
 * - Dashboard 组合
 */

import {
  renderSparkline,
  TimeSeriesBuffer,
  FrameBuffer,
  sparklineCard,
  stitchCards,
  renderGrid,
  GridLayout,
} from "tvs/v2";

console.log("🎨 Realtime Visualization Engine Test\n");
console.log("═".repeat(80));

// ==================== Test 1: Braille Sparkline (Line) ====================

console.log("\n📋 Test 1: Braille Sparkline - Line Variant\n");

const data1 = [0.1, 0.2, 0.35, 0.5, 0.45, 0.6, 0.75, 0.7, 0.85, 0.9, 0.8, 0.72];

console.log("Data: ", data1.map((v) => v.toFixed(2)).join(", "));
console.log("\nLine Sparkline (连续折线):");
console.log(renderSparkline(data1, 40, 2, "line"));

// ==================== Test 2: Braille Sparkline (Area) ====================

console.log("\n" + "─".repeat(80));
console.log("\n📋 Test 2: Braille Sparkline - Area Variant\n");

console.log("Area Sparkline (面积图):");
console.log(renderSparkline(data1, 40, 2, "area"));

// ==================== Test 3: 对比 Line vs Area ====================

console.log("\n" + "─".repeat(80));
console.log("\n📋 Test 3: Line vs Area Comparison\n");

const sineData: number[] = [];
for (let i = 0; i < 30; i++) {
  sineData.push((Math.sin((i / 30) * Math.PI * 2) + 1) / 2);
}

console.log("Sine Wave Data (30 points)\n");

console.log("Line:");
console.log(renderSparkline(sineData, 50, 2, "line"));

console.log("\nArea:");
console.log(renderSparkline(sineData, 50, 2, "area"));

// ==================== Test 4: Time Series Buffer ====================

console.log("\n" + "─".repeat(80));
console.log("\n📋 Test 4: Time Series Buffer\n");

const tsBuffer = new TimeSeriesBuffer(20);

// 模拟数据流
for (let i = 0; i < 25; i++) {
  tsBuffer.push(Math.random() * 0.5 + 0.25);
}

console.log(`Buffer length: ${tsBuffer.length} (max: 20)`);
console.log(`Latest value: ${tsBuffer.latest?.toFixed(3)}`);
console.log("\nLast 10 values:");
console.log(
  tsBuffer
    .getLast(10)
    .map((v) => v.toFixed(2))
    .join(", "),
);

console.log("\nSampled to 15 points:");
console.log(renderSparkline(tsBuffer.getSampled(15), 40, 1, "line"));

// ==================== Test 5: Frame Buffer Diff ====================

console.log("\n" + "─".repeat(80));
console.log("\n📋 Test 5: Frame Buffer Diff\n");

const fb = new FrameBuffer();

// 第一帧
fb.update(`┌──────────────┐
│ CPU: 45%     │
│ MEM: 72%     │
└──────────────┘`);

console.log("Frame 1:");
console.log(fb.getFullFrame());

// 第二帧 (只有 CPU 变化)
fb.update(`┌──────────────┐
│ CPU: 52%     │
│ MEM: 72%     │
└──────────────┘`);

console.log("\nFrame 2 (CPU changed to 52%):");
const diffs = fb.diff();
console.log(`Changed lines: ${diffs.length}`);
for (const d of diffs) {
  console.log(`  Row ${d.row}: "${d.oldLine}" → "${d.newLine}"`);
}

// ==================== Test 6: Sparkline Card ====================

console.log("\n" + "─".repeat(80));
console.log("\n📋 Test 6: Sparkline Card\n");

const cpuData = [0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.58, 0.52, 0.48];

console.log(
  sparklineCard("CPU Usage", cpuData, {
    width: 40,
    height: 2,
    variant: "line",
    currentValue: cpuData[cpuData.length - 1],
    unit: "%",
  }),
);

// ==================== Test 7: Multi-Card Dashboard ====================

console.log("\n" + "─".repeat(80));
console.log("\n📋 Test 7: Multi-Card Dashboard (Stitched)\n");

const memData = [0.6, 0.62, 0.65, 0.7, 0.72, 0.75, 0.73, 0.7, 0.68, 0.72];
const netData = [0.1, 0.15, 0.3, 0.5, 0.45, 0.2, 0.15, 0.25, 0.4, 0.35];

const cards = [
  sparklineCard("CPU", cpuData, { width: 30, height: 1, currentValue: 0.48 }),
  sparklineCard("Memory", memData, {
    width: 30,
    height: 1,
    currentValue: 0.72,
  }),
  sparklineCard("Network", netData, {
    width: 30,
    height: 1,
    currentValue: 0.35,
  }),
];

console.log(stitchCards(cards, 2));

// ==================== Test 8: Grid + Sparkline Integration ====================

console.log("\n" + "─".repeat(80));
console.log("\n📋 Test 8: Grid + Sparkline Integration\n");

// 使用 Grid 布局展示带 Sparkline 的卡片
const grid: GridLayout = {
  type: "grid",
  columns: 2,
  gap: 2,
  cells: [
    {
      span: 1,
      content: {
        type: "card",
        sections: [
          { type: "header", text: "Agent Coder" },
          { type: "divider" },
          {
            type: "kv",
            items: [
              { key: "Status", value: "Running", status: "success" },
              { key: "Load", bar: 0.65, render: "braille" },
            ],
          },
          {
            type: "sparkline",
            data: cpuData,
            label: "History",
            render: "braille",
          },
        ],
      },
    },
    {
      span: 1,
      content: {
        type: "card",
        sections: [
          { type: "header", text: "Agent Tester" },
          { type: "divider" },
          {
            type: "kv",
            items: [
              { key: "Status", value: "Testing", status: "info" },
              { key: "Load", bar: 0.42, render: "braille" },
            ],
          },
          {
            type: "sparkline",
            data: memData,
            label: "History",
            render: "braille",
          },
        ],
      },
    },
  ],
};

console.log(renderGrid(grid, { width: 80, style: "solar_default" }));

// ==================== Test 9: Realtime Loop Simulation ====================

console.log("\n" + "─".repeat(80));
console.log("\n📋 Test 9: Realtime Loop Simulation (5 frames)\n");

const buffer = new TimeSeriesBuffer(30);
const frameBuf = new FrameBuffer();

// 初始化数据
for (let i = 0; i < 20; i++) {
  buffer.push(Math.random() * 0.5 + 0.2);
}

// 模拟 5 帧更新
for (let frame = 1; frame <= 5; frame++) {
  // 添加新数据点
  buffer.push(Math.random() * 0.5 + 0.2);

  // 渲染新帧
  const sparkline = renderSparkline(buffer.getSampled(20), 30, 1, "line");
  const content = `Frame ${frame}: ${sparkline.replace(/\n/g, "")}`;

  frameBuf.update(content);
  const diffs = frameBuf.diff();

  console.log(content);
  console.log(
    `  → Changed: ${diffs.length > 0 ? "Yes" : "No"} (${diffs.length} lines)`,
  );
}

// ==================== Summary ====================

console.log("\n" + "═".repeat(80));
console.log("\n✅ All Realtime Visualization tests completed!\n");
console.log("特性:");
console.log("  • Braille Sparkline - 连续折线 (Bresenham)");
console.log("  • Area Sparkline - 面积填充图");
console.log("  • Time Series Buffer - 历史数据缓冲");
console.log("  • Frame Buffer Diff - 增量刷新");
console.log("  • ANSI Cursor Control - 终端光标控制");
console.log("  • RealtimeDashboard - 完整实时循环");
console.log("\n使用方式:");
console.log("  renderSparkline(values, width, height, 'line'|'area')");
console.log("  sparklineCard(title, values, options)");
console.log("  stitchCards([card1, card2], gap)");
console.log("  new RealtimeDashboard(renderFn).start(fps)");
console.log("\n刷新频率建议:");
console.log("  Agent 状态: 2-5 Hz");
console.log("  Sparkline:  1-2 Hz");
console.log("  Dashboard:  ≤10 Hz (终端极限)");
