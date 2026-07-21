/**
 * ASCII Layout DSL v0.1 - Test Suite
 */

import { render, card, kv, LayoutDSL } from "tvs/v2";

console.log("🎨 ASCII Layout DSL v0.1 Test\n");
console.log("═".repeat(72));

// ==================== Test 1: 基础 Card ====================

console.log("\n📋 Test 1: Enterprise Minimal Card\n");

const dsl1: LayoutDSL = {
  canvas: { width: 48, padding: 1 },
  style: "enterprise_minimal",
  layout: {
    type: "card",
    sections: [
      { type: "header", text: "System Status", align: "center" },
      { type: "divider" },
      {
        type: "kv",
        items: [
          { key: "Service", value: "Inference Engine" },
          { key: "Latency", value: 12, unit: "ms", status: "success" },
          { key: "Load", bar: 0.72 },
        ],
      },
    ],
  },
};

console.log(render(dsl1));

// ==================== Test 2: Solar Default ====================

console.log("\n" + "─".repeat(72));
console.log("\n📋 Test 2: Solar Default Style\n");

const dsl2: LayoutDSL = {
  canvas: { width: 56 },
  style: "solar_default",
  layout: {
    type: "card",
    sections: [
      { type: "header", text: "ThunderDuck Benchmark" },
      { type: "divider" },
      {
        type: "kv",
        items: [
          { key: "Q1", value: "1.23 ms", status: "success" },
          { key: "Q3", value: "2.34 ms", status: "success" },
          { key: "Q6", value: "0.89 ms", status: "success" },
          { key: "Speedup", bar: 0.85 },
        ],
      },
    ],
  },
};

console.log(render(dsl2));

// ==================== Test 3: Research Report (无边框) ====================

console.log("\n" + "─".repeat(72));
console.log("\n📋 Test 3: Research Report (No Border)\n");

const dsl3: LayoutDSL = {
  canvas: { width: 60 },
  style: "research_report",
  layout: {
    type: "card",
    sections: [
      { type: "header", text: "Performance Analysis" },
      { type: "divider" },
      {
        type: "kv",
        items: [
          { key: "Dataset", value: "TPC-H SF1" },
          { key: "Total Queries", value: 22 },
          { key: "Passed", value: 22, status: "success" },
          { key: "Avg Speedup", bar: 0.78 },
        ],
      },
    ],
  },
};

console.log(render(dsl3));

// ==================== Test 4: Cyber Style ====================

console.log("\n" + "─".repeat(72));
console.log("\n📋 Test 4: Cyber Style (Double Border)\n");

const dsl4: LayoutDSL = {
  canvas: { width: 50 },
  style: "cyber",
  layout: {
    type: "card",
    sections: [
      { type: "header", text: "Agent Status" },
      { type: "divider" },
      {
        type: "kv",
        items: [
          { key: "Agent", value: "Coder" },
          { key: "Task", value: "Implementing TVS" },
          { key: "Progress", bar: 0.65 },
        ],
      },
    ],
  },
};

console.log(render(dsl4));

// ==================== Test 5: 快捷 API ====================

console.log("\n" + "─".repeat(72));
console.log("\n📋 Test 5: Quick API - card()\n");

console.log(
  card(
    "Quick Status",
    [
      { key: "CPU", bar: 0.45 },
      { key: "Memory", bar: 0.72 },
      { key: "Disk", value: "128 GB" },
    ],
    { width: 48 },
  ),
);

// ==================== Test 6: 快捷 KV ====================

console.log("\n" + "─".repeat(72));
console.log("\n📋 Test 6: Quick API - kv()\n");

console.log(
  kv([
    { key: "Version", value: "3.2.1" },
    { key: "Build", value: "2026-01-29" },
    { key: "Status", value: "Production" },
  ]),
);

// ==================== Test 7: List Section ====================

console.log("\n" + "─".repeat(72));
console.log("\n📋 Test 7: List Section\n");

const dsl7: LayoutDSL = {
  canvas: { width: 50 },
  style: "solar_default",
  layout: {
    type: "card",
    sections: [
      { type: "header", text: "Task List" },
      { type: "divider" },
      {
        type: "list",
        variant: "checkbox",
        items: [
          { text: "Design Schema", checked: true, status: "success" },
          { text: "Implement Renderer", checked: true, status: "success" },
          { text: "Write Tests", checked: false },
          { text: "Documentation", checked: false },
        ],
      },
    ],
  },
};

console.log(render(dsl7));

// ==================== Test 8: Text Section ====================

console.log("\n" + "─".repeat(72));
console.log("\n📋 Test 8: Text Section\n");

const dsl8: LayoutDSL = {
  canvas: { width: 60 },
  style: "enterprise_minimal",
  layout: {
    type: "card",
    sections: [
      { type: "header", text: "Summary" },
      { type: "divider" },
      {
        type: "text",
        content:
          "The ASCII Layout DSL provides a semantic intermediate representation for terminal UI. It separates concerns between intent (DSL) and presentation (Renderer).",
      },
    ],
  },
};

console.log(render(dsl8));

// ==================== Test 9: Bar Section ====================

console.log("\n" + "─".repeat(72));
console.log("\n📋 Test 9: Standalone Bar\n");

const dsl9: LayoutDSL = {
  canvas: { width: 60 },
  style: "solar_default",
  layout: {
    type: "card",
    sections: [
      { type: "header", text: "Progress" },
      { type: "divider" },
      { type: "bar", value: 0.68, label: "Complete", showPercent: true },
    ],
  },
};

console.log(render(dsl9));

// ==================== Summary ====================

console.log("\n" + "═".repeat(72));
console.log("\n✅ All ASCII Layout DSL v0.1 tests completed!\n");
console.log("Available styles:");
console.log("  • enterprise_minimal - Single border, uppercase headers");
console.log("  • solar_default     - Rounded border, centered headers");
console.log("  • research_report   - No border, airy spacing");
console.log("  • cyber             - Double border, compact");
console.log("  • compact           - Single border, tight spacing");
console.log("\nUsage:");
console.log("  render(dsl)         - Render full DSL");
console.log("  card(title, items)  - Quick card");
console.log("  kv(items)           - Quick KV list");
