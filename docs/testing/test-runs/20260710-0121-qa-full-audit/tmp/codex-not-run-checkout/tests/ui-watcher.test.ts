/**
 * Solar UI Watcher Integration Test
 * 测试 LLM → Queue → Watcher → Render 流程
 */

import { UIWatcher } from "../core/daemon/ui-watcher";
import { queueUI, RenderResult } from "../core/engine/ui-engine";
import { existsSync, mkdirSync, rmSync, readdirSync, writeFileSync } from "fs";
import { join } from "path";

const queueDir = `${process.env.HOME}/.solar/ui/queue`;

// 确保队列目录存在
if (!existsSync(queueDir)) {
  mkdirSync(queueDir, { recursive: true });
}

// 清理队列
const cleanup = () => {
  if (existsSync(queueDir)) {
    const files = readdirSync(queueDir);
    for (const file of files) {
      rmSync(join(queueDir, file));
    }
  }
};

console.log("🎨 UI Watcher Integration Test\n");
console.log("─".repeat(60));

// ==================== Test 1: Direct Render ====================

console.log("\n📋 Test 1: Direct Render (without queue)\n");

const watcher = new UIWatcher(queueDir);

const result1 = await watcher.renderDirect({
  id: "direct-1",
  type: "box",
  data: {
    agent: "Tester",
    emoji: "🧪",
    task: "Verify UI Watcher",
    plan: ["Test direct render", "Test queue processing"],
  },
  style: { border: "round", width: 50 },
  timestamp: new Date().toISOString(),
});

console.log(result1.output);
console.log(`\n✅ Direct render: ${result1.width}x${result1.height} chars\n`);

// ==================== Test 2: Queue Processing ====================

console.log("─".repeat(60));
console.log("\n📋 Test 2: Queue Processing\n");

cleanup();

// 收集输出
const outputs: RenderResult[] = [];
watcher.onOutput((result) => {
  outputs.push(result);
  console.log(result.output);
  console.log();
});

// 启动 watcher
watcher.start();

// 写入测试指令到队列
const testCommands = [
  {
    id: "queue-test-1",
    type: "banner",
    data: {
      title: "☀️  S O L A R",
      version: "3.0.0",
    },
    timestamp: new Date().toISOString(),
  },
  {
    id: "queue-test-2",
    type: "card",
    data: {
      header: "📊 Test Stats",
      items: [
        { key: "Total", value: "18" },
        { key: "Passed", value: "18" },
        { key: "Coverage", value: "100%" },
      ],
    },
    style: { width: 26 },
    timestamp: new Date().toISOString(),
  },
  {
    id: "queue-test-3",
    type: "progress",
    data: {
      label: "Complete",
      value: 100,
      max: 100,
    },
    timestamp: new Date().toISOString(),
  },
];

// 写入队列文件
for (const cmd of testCommands) {
  const filepath = join(queueDir, `${cmd.id}.json`);
  writeFileSync(filepath, JSON.stringify(cmd, null, 2));
}

// 等待处理
await new Promise((resolve) => setTimeout(resolve, 500));

watcher.stop();

// 验证
const remainingFiles = existsSync(queueDir) ? readdirSync(queueDir) : [];
console.log("─".repeat(60));
console.log(`\n📊 Results:`);
console.log(`   Commands queued:   ${testCommands.length}`);
console.log(`   Outputs received:  ${outputs.length}`);
console.log(`   Files remaining:   ${remainingFiles.length}`);

if (outputs.length === testCommands.length && remainingFiles.length === 0) {
  console.log("\n✅ Queue processing test passed!\n");
} else {
  console.log("\n❌ Queue processing test failed!\n");
  process.exit(1);
}

// ==================== Test 3: LLM Interface ====================

console.log("─".repeat(60));
console.log("\n📋 Test 3: LLM Interface (queueUI function)\n");

cleanup();

// 模拟 LLM 调用
const id1 = queueUI({
  type: "alert",
  data: { type: "success", message: "All tests passed!" },
});

const id2 = queueUI({
  type: "cowsay",
  data: { text: "Hello from LLM!" },
  style: { cow: "solar" },
});

// 检查队列文件
const queuedFiles = readdirSync(queueDir);
console.log(`   Queued IDs: ${id1.slice(0, 8)}..., ${id2.slice(0, 8)}...`);
console.log(`   Files in queue: ${queuedFiles.length}`);

if (queuedFiles.length === 2) {
  console.log("\n✅ LLM interface test passed!\n");
} else {
  console.log("\n❌ LLM interface test failed!\n");
  process.exit(1);
}

// 清理
cleanup();

// ==================== Summary ====================

console.log("═".repeat(60));
console.log("\n🎉 All UI Watcher tests passed!\n");
console.log("Integration flow verified:");
console.log("  1. LLM calls queueUI() → JSON file created");
console.log("  2. UIWatcher detects file → Reads command");
console.log("  3. UIEngine renders → Output generated");
console.log("  4. Callback invoked → File deleted\n");
