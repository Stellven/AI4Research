/**
 * Terminal Visual System - Comprehensive Test
 *
 * 测试完整的 TVS 流水线: IR → Layout → Render
 */

import { tvs, TVS, SemanticIR } from "tvs";

console.log("🎨 Terminal Visual System Test\n");
console.log("═".repeat(70));

// ==================== Test 1: Simple KV ====================

console.log("\n📋 Test 1: KV Component\n");

const kvOutput = tvs.render({
  canvas: { width: 50 },
  style: "solar_default",
  root: {
    type: "kv",
    items: [
      { key: "Service", value: "Inference Engine" },
      { key: "Version", value: "3.2.1" },
      { key: "Latency", value: 12, unit: "ms", status: "success" },
      { key: "Load", bar: 0.72 },
    ],
  },
});

console.log(kvOutput);

// ==================== Test 2: Card with Header ====================

console.log("\n" + "─".repeat(70));
console.log("\n📋 Test 2: Card with Header\n");

const cardOutput = tvs.render({
  canvas: { width: 60 },
  style: "solar_default",
  root: {
    type: "card",
    header: "System Status",
    sections: [
      {
        type: "kv",
        items: [
          { key: "Service", value: "Inference Engine" },
          { key: "Latency", value: "12 ms", status: "success" },
          { key: "Load", bar: 0.72 },
        ],
      },
    ],
  },
});

console.log(cardOutput);

// ==================== Test 3: Table ====================

console.log("\n" + "─".repeat(70));
console.log("\n📋 Test 3: Table\n");

const tableOutput = tvs.render({
  canvas: { width: 60 },
  style: "solar_default",
  root: {
    type: "table",
    columns: [
      { key: "query", label: "Query" },
      { key: "td", label: "ThunderDuck" },
      { key: "ddb", label: "DuckDB" },
      { key: "speedup", label: "Speedup" },
    ],
    rows: [
      { query: "Q1", td: "1.23 ms", ddb: "4.56 ms", speedup: "3.7x" },
      { query: "Q3", td: "2.34 ms", ddb: "8.90 ms", speedup: "3.8x" },
      { query: "Q6", td: "0.89 ms", ddb: "3.21 ms", speedup: "3.6x" },
    ],
  },
});

console.log(tableOutput);

// ==================== Test 4: Tree ====================

console.log("\n" + "─".repeat(70));
console.log("\n📋 Test 4: Tree\n");

const treeOutput = tvs.render({
  canvas: { width: 50 },
  style: "solar_default",
  root: {
    type: "tree",
    root: {
      label: "solar",
      icon: "📁",
      children: [
        {
          label: "core",
          icon: "📁",
          children: [
            { label: "tvs", icon: "📁", status: "success" },
            { label: "daemon", icon: "📁" },
            { label: "nerve", icon: "📁" },
          ],
        },
        { label: "bin", icon: "📁" },
        { label: "package.json", icon: "📄" },
      ],
    },
  },
});

console.log(treeOutput);

// ==================== Test 5: List ====================

console.log("\n" + "─".repeat(70));
console.log("\n📋 Test 5: List\n");

const listOutput = tvs.render({
  canvas: { width: 50 },
  style: "solar_default",
  root: {
    type: "list",
    variant: "checkbox",
    items: [
      { text: "Design IR types", checked: true, status: "success" },
      { text: "Implement compiler", checked: true, status: "success" },
      { text: "Implement renderer", checked: true, status: "success" },
      { text: "Write tests", checked: false },
      { text: "Documentation", checked: false },
    ],
  },
});

console.log(listOutput);

// ==================== Test 6: Bar + Sparkline ====================

console.log("\n" + "─".repeat(70));
console.log("\n📋 Test 6: Bar + Sparkline\n");

const vizOutput = tvs.render({
  canvas: { width: 60 },
  style: "solar_default",
  root: {
    type: "stack",
    direction: "vertical",
    gap: 1,
    items: [
      { type: "bar", value: 0.72, label: "CPU", showPercent: true },
      { type: "bar", value: 0.45, label: "Memory", showPercent: true },
      { type: "bar", value: 0.88, label: "Disk", showPercent: true },
      {
        type: "sparkline",
        data: [0.2, 0.3, 0.5, 0.4, 0.6, 0.8, 0.7, 0.72],
        label: "History",
      },
    ],
  },
});

console.log(vizOutput);

// ==================== Test 7: Different Styles ====================

console.log("\n" + "─".repeat(70));
console.log("\n📋 Test 7: Different Styles\n");

const ir: SemanticIR = {
  canvas: { width: 50 },
  root: {
    type: "card",
    header: "Status",
    sections: [
      {
        type: "kv",
        items: [
          { key: "Load", bar: 0.72 },
          { key: "Status", value: "OK", status: "success" },
        ],
      },
    ],
  },
};

console.log("solar_default:");
console.log(tvs.render({ ...ir, style: "solar_default" }));

console.log("\nenterprise_minimal:");
console.log(tvs.render({ ...ir, style: "enterprise_minimal" }));

// ==================== Test 8: Convenience API ====================

console.log("\n" + "─".repeat(70));
console.log("\n📋 Test 8: Convenience API\n");

console.log("tvs.heading():");
console.log(tvs.heading("Hello TVS", 1, { width: 40 }));

console.log("\ntvs.divider():");
console.log(tvs.divider("Section", { width: 40 }));

console.log("\ntvs.bar():");
console.log(tvs.bar(0.65, { label: "Progress", width: 40 }));

console.log("\ntvs.list():");
console.log(tvs.list(["Item 1", "Item 2", "Item 3"], { width: 40 }));

// ==================== Test 9: Complex Card ====================

console.log("\n" + "─".repeat(70));
console.log("\n📋 Test 9: Complex Card (Agent Announcement)\n");

const agentCard = tvs.render({
  canvas: { width: 55 },
  style: "solar_default",
  root: {
    type: "card",
    header: { type: "heading", level: 1, text: "💻 Coder", align: "left" },
    sections: [
      { type: "text", content: "Task: Implement TVS rendering pipeline" },
      { type: "divider" },
      {
        type: "list",
        variant: "numbered",
        items: [
          "Design component types",
          "Implement layout compiler",
          "Implement glyph renderer",
          "Test and verify",
        ],
      },
    ],
  },
});

console.log(agentCard);

// ==================== Summary ====================

console.log("\n" + "═".repeat(70));
console.log("\n✅ All TVS tests completed!\n");
console.log("Available styles: " + tvs.styles().join(", "));
console.log("\nUsage:");
console.log("  tvs.render(ir)           - Render Semantic IR");
console.log("  tvs.component(c)         - Render single component");
console.log("  tvs.card(header, [...])  - Quick card");
console.log("  tvs.kv([...])            - Quick KV");
console.log("  tvs.table([...], [...])  - Quick table");
console.log("  tvs.queue(ir)            - Queue for Daemon");
