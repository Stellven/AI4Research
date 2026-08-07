/**
 * Grid / Dashboard Layout Test
 *
 * Terminal 世界的 CSS Grid
 */

import {
  render,
  renderGrid,
  dashboard,
  LayoutDSL,
  GridLayout,
} from "tvs/v2";

console.log("🎨 Grid / Dashboard Layout Test\n");
console.log("═".repeat(100));

// ==================== Test 1: 基础 3 列 Grid ====================

console.log("\n📋 Test 1: Basic 3-Column Grid\n");

const grid1: GridLayout = {
  type: "grid",
  columns: 3,
  gap: 2,
  cells: [
    {
      span: 1,
      content: {
        type: "card",
        sections: [
          { type: "header", text: "Agent A" },
          { type: "divider" },
          {
            type: "kv",
            items: [
              { key: "Status", value: "Running" },
              { key: "Load", bar: 0.65 },
            ],
          },
        ],
      },
    },
    {
      span: 1,
      content: {
        type: "card",
        sections: [
          { type: "header", text: "Agent B" },
          { type: "divider" },
          {
            type: "kv",
            items: [
              { key: "Status", value: "Idle" },
              { key: "Load", bar: 0.25 },
            ],
          },
        ],
      },
    },
    {
      span: 1,
      content: {
        type: "card",
        sections: [
          { type: "header", text: "Agent C" },
          { type: "divider" },
          {
            type: "kv",
            items: [
              { key: "Status", value: "Busy" },
              { key: "Load", bar: 0.92 },
            ],
          },
        ],
      },
    },
  ],
};

console.log(renderGrid(grid1, { width: 100 }));

// ==================== Test 2: Span 跨列 ====================

console.log("\n" + "─".repeat(100));
console.log("\n📋 Test 2: Column Spanning\n");

const grid2: GridLayout = {
  type: "grid",
  columns: 3,
  gap: 2,
  cells: [
    {
      span: 1,
      content: {
        type: "card",
        sections: [
          { type: "header", text: "CPU" },
          { type: "divider" },
          { type: "kv", items: [{ key: "Usage", bar: 0.45 }] },
        ],
      },
    },
    {
      span: 2, // 跨 2 列
      content: {
        type: "card",
        sections: [
          { type: "header", text: "System Overview" },
          { type: "divider" },
          {
            type: "kv",
            items: [
              { key: "Uptime", value: "14 days" },
              { key: "Memory", bar: 0.72 },
              { key: "Disk", bar: 0.38 },
            ],
          },
        ],
      },
    },
    {
      span: 2, // 跨 2 列
      content: {
        type: "card",
        sections: [
          { type: "header", text: "Network" },
          { type: "divider" },
          {
            type: "kv",
            items: [
              { key: "In", value: "125 MB/s" },
              { key: "Out", value: "89 MB/s" },
            ],
          },
        ],
      },
    },
    {
      span: 1,
      content: {
        type: "card",
        sections: [
          { type: "header", text: "GPU" },
          { type: "divider" },
          { type: "kv", items: [{ key: "Usage", bar: 0.88 }] },
        ],
      },
    },
  ],
};

console.log(renderGrid(grid2, { width: 100 }));

// ==================== Test 3: dashboard() 快捷 API ====================

console.log("\n" + "─".repeat(100));
console.log("\n📋 Test 3: dashboard() Quick API\n");

console.log(
  dashboard(
    [
      {
        title: "Coder",
        items: [
          { key: "Task", value: "Impl TVS" },
          { key: "Progress", bar: 0.75 },
        ],
      },
      {
        title: "Tester",
        items: [
          { key: "Task", value: "Unit Tests" },
          { key: "Progress", bar: 0.45 },
        ],
      },
      {
        title: "Reviewer",
        items: [
          { key: "Task", value: "Code Review" },
          { key: "Progress", bar: 0.2 },
        ],
      },
    ],
    { width: 100, columns: 3 },
  ),
);

// ==================== Test 4: 2 列布局 ====================

console.log("\n" + "─".repeat(100));
console.log("\n📋 Test 4: 2-Column Layout\n");

console.log(
  dashboard(
    [
      {
        title: "ThunderDuck",
        items: [
          { key: "Version", value: "v38" },
          { key: "Speedup", value: "3.5x" },
          { key: "Coverage", bar: 0.95 },
        ],
      },
      {
        title: "DuckDB",
        items: [
          { key: "Version", value: "0.9.2" },
          { key: "Baseline", value: "1.0x" },
          { key: "Coverage", bar: 1.0 },
        ],
      },
    ],
    { width: 80, columns: 2 },
  ),
);

// ==================== Test 5: 通过 render() 自动检测 Grid ====================

console.log("\n" + "─".repeat(100));
console.log("\n📋 Test 5: Auto-detect Grid via render()\n");

const dsl: LayoutDSL = {
  canvas: { width: 100 },
  style: "solar_default",
  layout: {
    type: "grid",
    columns: 2,
    gap: 2,
    cells: [
      {
        content: {
          type: "card",
          sections: [
            { type: "header", text: "Cell 1" },
            { type: "divider" },
            { type: "text", content: "This is rendered via render()" },
          ],
        },
      },
      {
        content: {
          type: "card",
          sections: [
            { type: "header", text: "Cell 2" },
            { type: "divider" },
            { type: "text", content: "Grid layout auto-detected" },
          ],
        },
      },
    ],
  },
};

console.log(render(dsl));

// ==================== Test 6: 多行复杂布局 ====================

console.log("\n" + "─".repeat(100));
console.log("\n📋 Test 6: Multi-Row Complex Layout\n");

const grid6: GridLayout = {
  type: "grid",
  columns: 4,
  gap: 1,
  rowGap: 1,
  cells: [
    // Row 1: 4 个小卡片
    {
      content: {
        type: "card",
        sections: [
          { type: "header", text: "Q1" },
          { type: "kv", items: [{ key: "Time", value: "1.2ms" }] },
        ],
      },
    },
    {
      content: {
        type: "card",
        sections: [
          { type: "header", text: "Q3" },
          { type: "kv", items: [{ key: "Time", value: "2.3ms" }] },
        ],
      },
    },
    {
      content: {
        type: "card",
        sections: [
          { type: "header", text: "Q6" },
          { type: "kv", items: [{ key: "Time", value: "0.9ms" }] },
        ],
      },
    },
    {
      content: {
        type: "card",
        sections: [
          { type: "header", text: "Q18" },
          { type: "kv", items: [{ key: "Time", value: "5.1ms" }] },
        ],
      },
    },
    // Row 2: 1 个全宽卡片
    {
      span: 4,
      content: {
        type: "card",
        sections: [
          { type: "header", text: "TPC-H Benchmark Summary" },
          { type: "divider" },
          {
            type: "kv",
            items: [
              { key: "Total Queries", value: 22 },
              { key: "Passed", value: 22, status: "success" },
              { key: "Avg Speedup", value: "3.5x" },
              { key: "Overall", bar: 0.92 },
            ],
          },
        ],
      },
    },
  ],
};

console.log(renderGrid(grid6, { width: 100 }));

// ==================== Summary ====================

console.log("\n" + "═".repeat(100));
console.log("\n✅ All Grid / Dashboard tests completed!\n");
console.log("Grid 特性:");
console.log("  • columns - 列数定义");
console.log("  • span    - 跨列支持");
console.log("  • gap     - 列间距");
console.log("  • rowGap  - 行间距");
console.log("  • 自动换行 - cursor 追踪");
console.log("  • 高度对齐 - Row Stitching");
console.log("\n使用方式:");
console.log("  renderGrid(layout, { width, style })");
console.log("  dashboard([cells], { width, columns })");
console.log("  render(dsl) - 自动检测 Grid");
