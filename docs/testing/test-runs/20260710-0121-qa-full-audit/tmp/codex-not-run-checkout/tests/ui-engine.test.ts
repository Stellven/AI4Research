/**
 * Solar UI Engine Tests
 * 测试所有内置渲染器
 */

import { UIEngine, UICommand, queueUI, ui } from "../core/engine/ui-engine";
import { existsSync, mkdirSync, rmSync, readdirSync } from "fs";
import { join } from "path";

const testDir = `${process.env.HOME}/.solar/ui`;
const queueDir = join(testDir, "queue");

// ==================== 测试准备 ====================

function setup() {
  // 确保目录存在
  if (!existsSync(queueDir)) {
    mkdirSync(queueDir, { recursive: true });
  }
}

function cleanup() {
  // 清理队列目录
  if (existsSync(queueDir)) {
    const files = readdirSync(queueDir);
    for (const file of files) {
      rmSync(join(queueDir, file));
    }
  }
}

// ==================== 测试用例 ====================

console.log("🧪 Solar UI Engine Tests\n");
console.log("─".repeat(60));

setup();

const engine = new UIEngine();
let passed = 0;
let failed = 0;

async function test(name: string, fn: () => Promise<void> | void) {
  try {
    await fn();
    console.log(`✅ ${name}`);
    passed++;
  } catch (error: any) {
    console.log(`❌ ${name}`);
    console.log(`   Error: ${error.message}`);
    failed++;
  }
}

function assert(condition: boolean, message: string) {
  if (!condition) throw new Error(message);
}

// ==================== Banner 测试 ====================

await test("Banner - basic rendering", async () => {
  const command: UICommand = {
    id: "test-banner-1",
    type: "banner",
    data: {
      title: "☀️  S O L A R",
      version: "3.0.0",
      subtitle: "Multi-Agent Development Framework",
    },
    timestamp: new Date().toISOString(),
  };

  const result = await engine.render(command);
  assert(result.output.includes("S O L A R"), "Should contain title");
  assert(result.output.includes("3.0.0"), "Should contain version");
  assert(result.height > 3, "Should have multiple lines");
  console.log("\n" + result.output + "\n");
});

// ==================== Box 测试 ====================

await test("Box - agent announcement", async () => {
  const command: UICommand = {
    id: "test-box-1",
    type: "box",
    data: {
      agent: "Coder",
      emoji: "💻",
      task: "Implement UI Engine",
      plan: ["Create renderers", "Add tests", "Document API"],
    },
    style: { border: "round", width: 50 },
    timestamp: new Date().toISOString(),
  };

  const result = await engine.render(command);
  assert(result.output.includes("Coder"), "Should contain agent name");
  assert(result.output.includes("Implement UI Engine"), "Should contain task");
  assert(result.output.includes("1."), "Should contain numbered plan");
  console.log("\n" + result.output + "\n");
});

await test("Box - with header", async () => {
  const command: UICommand = {
    id: "test-box-2",
    type: "box",
    data: {
      header: "📋 Task List",
      content: ["Item 1", "Item 2", "Item 3"],
    },
    style: { border: "double", width: 40 },
    timestamp: new Date().toISOString(),
  };

  const result = await engine.render(command);
  assert(result.output.includes("Task List"), "Should contain header");
  console.log("\n" + result.output + "\n");
});

// ==================== Status 测试 ====================

await test("Status - status line", async () => {
  const command: UICommand = {
    id: "test-status-1",
    type: "status",
    data: {
      phase: "P3",
      agent: "Coder",
      tokens: "+1.2K",
      rate: 45,
      status: "ok",
    },
    timestamp: new Date().toISOString(),
  };

  const result = await engine.render(command);
  assert(result.output.includes("P3"), "Should contain phase");
  assert(result.output.includes("Coder"), "Should contain agent");
  assert(result.output.includes("45%"), "Should contain rate");
  console.log("\n" + result.output + "\n");
});

// ==================== Progress 测试 ====================

await test("Progress - progress bar", async () => {
  const command: UICommand = {
    id: "test-progress-1",
    type: "progress",
    data: {
      label: "Building",
      value: 75,
      max: 100,
    },
    style: { width: 20 },
    timestamp: new Date().toISOString(),
  };

  const result = await engine.render(command);
  assert(result.output.includes("Building"), "Should contain label");
  assert(result.output.includes("75%"), "Should contain percentage");
  assert(result.output.includes("█"), "Should contain progress chars");
  console.log("\n" + result.output + "\n");
});

// ==================== Table 测试 ====================

await test("Table - basic table", async () => {
  const command: UICommand = {
    id: "test-table-1",
    type: "table",
    data: {
      headers: ["Query", "ThunderDuck", "DuckDB", "Speedup"],
      rows: [
        ["Q1", "1.23ms", "4.56ms", "3.7x"],
        ["Q3", "2.34ms", "8.90ms", "3.8x"],
        ["Q6", "0.89ms", "3.21ms", "3.6x"],
      ],
    },
    timestamp: new Date().toISOString(),
  };

  const result = await engine.render(command);
  assert(result.output.includes("Query"), "Should contain headers");
  assert(result.output.includes("Q1"), "Should contain data");
  assert(result.output.includes("3.7x"), "Should contain speedup");
  console.log("\n" + result.output + "\n");
});

// ==================== Tree 测试 ====================

await test("Tree - directory tree", async () => {
  const command: UICommand = {
    id: "test-tree-1",
    type: "tree",
    data: {
      root: {
        name: "solar",
        children: [
          {
            name: "core",
            children: [
              { name: "engine" },
              { name: "daemon" },
              { name: "nerve" },
            ],
          },
          { name: "bin" },
          { name: "templates" },
        ],
      },
    },
    timestamp: new Date().toISOString(),
  };

  const result = await engine.render(command);
  assert(result.output.includes("solar"), "Should contain root");
  assert(result.output.includes("core"), "Should contain children");
  assert(
    result.output.includes("├──") || result.output.includes("└──"),
    "Should have tree chars",
  );
  console.log("\n" + result.output + "\n");
});

// ==================== FIGlet 测试 ====================

await test("FIGlet - ASCII art text", async () => {
  const command: UICommand = {
    id: "test-figlet-1",
    type: "figlet",
    data: { text: "SOLAR" },
    timestamp: new Date().toISOString(),
  };

  const result = await engine.render(command);
  assert(result.height >= 5, "Should have ASCII art height");
  console.log("\n" + result.output + "\n");
});

// ==================== Cowsay 测试 ====================

await test("Cowsay - speech bubble", async () => {
  const command: UICommand = {
    id: "test-cowsay-1",
    type: "cowsay",
    data: { text: "Hello from Solar! This is a test of the cowsay renderer." },
    style: { cow: "solar" },
    timestamp: new Date().toISOString(),
  };

  const result = await engine.render(command);
  assert(result.output.includes("Hello"), "Should contain message");
  assert(result.output.includes("^__^"), "Should contain cow");
  assert(result.output.includes("☀️"), "Should contain solar sun");
  console.log("\n" + result.output + "\n");
});

// ==================== Alert 测试 ====================

await test("Alert - info alert", async () => {
  const command: UICommand = {
    id: "test-alert-1",
    type: "alert",
    data: { type: "info", message: "This is an informational message." },
    timestamp: new Date().toISOString(),
  };

  const result = await engine.render(command);
  assert(result.output.includes("Info"), "Should contain alert type");
  assert(result.output.includes("informational"), "Should contain message");
  console.log("\n" + result.output + "\n");
});

await test("Alert - error alert", async () => {
  const command: UICommand = {
    id: "test-alert-2",
    type: "alert",
    data: { type: "error", message: "Build failed!" },
    timestamp: new Date().toISOString(),
  };

  const result = await engine.render(command);
  assert(result.output.includes("Error"), "Should contain error type");
  console.log("\n" + result.output + "\n");
});

// ==================== List 测试 ====================

await test("List - bullet list", async () => {
  const command: UICommand = {
    id: "test-list-1",
    type: "list",
    data: {
      items: ["First item", "Second item", "Third item"],
    },
    timestamp: new Date().toISOString(),
  };

  const result = await engine.render(command);
  assert(result.output.includes("First item"), "Should contain items");
  assert(result.output.includes("•"), "Should contain bullet");
  console.log("\n" + result.output + "\n");
});

await test("List - numbered list", async () => {
  const command: UICommand = {
    id: "test-list-2",
    type: "list",
    data: {
      items: ["Research", "Design", "Implement"],
    },
    style: { numbered: true },
    timestamp: new Date().toISOString(),
  };

  const result = await engine.render(command);
  assert(result.output.includes("1."), "Should contain numbers");
  console.log("\n" + result.output + "\n");
});

// ==================== Divider 测试 ====================

await test("Divider - simple divider", async () => {
  const command: UICommand = {
    id: "test-divider-1",
    type: "divider",
    data: {},
    style: { width: 40 },
    timestamp: new Date().toISOString(),
  };

  const result = await engine.render(command);
  assert(result.output.includes("─"), "Should contain divider char");
  assert(result.width === 40, "Should have correct width");
  console.log("\n" + result.output + "\n");
});

await test("Divider - with label", async () => {
  const command: UICommand = {
    id: "test-divider-2",
    type: "divider",
    data: { label: "Section" },
    style: { width: 40 },
    timestamp: new Date().toISOString(),
  };

  const result = await engine.render(command);
  assert(result.output.includes("Section"), "Should contain label");
  console.log("\n" + result.output + "\n");
});

// ==================== Card 测试 ====================

await test("Card - stats card", async () => {
  const command: UICommand = {
    id: "test-card-1",
    type: "card",
    data: {
      header: "📊 Stats",
      items: [
        { key: "Tests", value: "17" },
        { key: "Passed", value: "17" },
        { key: "Failed", value: "0" },
        { key: "Coverage", value: "85%" },
      ],
    },
    style: { width: 28 },
    timestamp: new Date().toISOString(),
  };

  const result = await engine.render(command);
  assert(result.output.includes("Stats"), "Should contain header");
  assert(result.output.includes("Tests"), "Should contain key");
  assert(result.output.includes("17"), "Should contain value");
  console.log("\n" + result.output + "\n");
});

// ==================== Queue 测试 ====================

await test("Queue - queueUI function", () => {
  cleanup(); // 清理之前的队列文件

  const id = queueUI({
    type: "box",
    data: { title: "Queue Test" },
  });

  assert(id !== undefined, "Should return id");

  const files = readdirSync(queueDir);
  assert(files.length > 0, "Should create queue file");
  assert(
    files.some((f) => f.includes(id)),
    "Should have correct filename",
  );

  cleanup();
});

await test("Queue - ui convenience methods", () => {
  cleanup();

  ui.banner({ title: "Test Banner" });
  ui.alert("success", "Test passed!");
  ui.progress("Loading", 50, 100);

  const files = readdirSync(queueDir);
  assert(files.length === 3, `Should have 3 queue files, got ${files.length}`);

  cleanup();
});

// ==================== 结果汇总 ====================

console.log("\n" + "─".repeat(60));
console.log(`\n📊 Test Results: ${passed} passed, ${failed} failed\n`);

if (failed > 0) {
  console.log("❌ Some tests failed!");
  process.exit(1);
} else {
  console.log("✅ All tests passed!");
}

// ==================== 综合演示 ====================

console.log("\n" + "═".repeat(60));
console.log("🎨 Comprehensive Demo\n");

// 完整的 Agent 宣告演示
const demoCommand: UICommand = {
  id: "demo",
  type: "box",
  data: {
    header: "💻 Coder",
    agent: "Coder",
    emoji: "💻",
    task: "Test and improve UI Engine",
    plan: [
      "Create comprehensive test suite",
      "Verify all renderers work correctly",
      "Fix any identified issues",
      "Document the API",
    ],
  },
  style: { border: "round", width: 52 },
  timestamp: new Date().toISOString(),
};

const demo = await engine.render(demoCommand);
console.log(demo.output);
console.log();
