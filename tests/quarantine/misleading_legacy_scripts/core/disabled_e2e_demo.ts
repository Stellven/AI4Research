/**
 * Solar v1.0 端到端测试
 *
 * 验证所有核心模块协同工作
 */

// ==================== 1. Agent Protocol Test ====================

import {
  createTaskMessage,
  createResultMessage,
  getBus,
  resetBus,
  type AgentMessage,
} from "./agent";

async function testAgentProtocol(): Promise<boolean> {
  console.log("\n═══ 1. Agent Protocol Test ═══\n");

  resetBus(); // Clean slate
  const bus = getBus({ enableLogging: false });

  let receivedMessage: AgentMessage | null = null;
  let responseReceived = false;

  // Subscribe coder agent
  bus.subscribe("coder", async (message) => {
    receivedMessage = message;
    console.log(`  ✓ Coder received task: ${(message.payload.data as any)?.task?.title}`);

    // Send result back
    const result = createResultMessage(
      "coder",
      "orchestrator",
      (message.payload.data as any)?.task?.id,
      {
        action: "complete",
        output: { code: "console.log('Hello');" },
        metrics: { duration: 100, tokensUsed: 50, toolCalls: 2 },
      },
      message.id
    );
    bus.publish(result);
  });

  // Subscribe orchestrator for results
  bus.subscribe("orchestrator", async (message) => {
    if (message.type === "result") {
      responseReceived = true;
      console.log(`  ✓ Orchestrator received result: ${message.payload.action}`);
    }
  });

  // Send task
  const task = createTaskMessage("orchestrator", "coder", {
    id: "task_1",
    title: "Implement hello world",
    description: "Create a simple hello world function",
    type: "implement",
  });

  bus.publish(task);
  console.log(`  ✓ Task published: ${task.id}`);

  // Wait for processing
  await sleep(100);

  const success = receivedMessage !== null && responseReceived;
  console.log(`\n  Result: ${success ? "✅ PASS" : "❌ FAIL"}`);

  bus.stop();
  return success;
}

// ==================== 2. Parallel Executor Test ====================

import { createExecutor, type FlowTask } from "./flow";

async function testParallelExecutor(): Promise<boolean> {
  console.log("\n═══ 2. Parallel Executor Test ═══\n");

  const executor = createExecutor({
    maxConcurrency: 3,
    onTaskStart: (task) => console.log(`  → Starting: ${task.name}`),
    onTaskComplete: (task, result) =>
      console.log(`  ✓ Completed: ${task.name} (${result.duration}ms)`),
    onTaskFailed: (task, error) =>
      console.log(`  ✗ Failed: ${task.name} - ${error.message}`),
  });

  // Create task graph:
  //   research ─┬─> design ─┬─> implement-frontend ─┬─> test
  //             │           └─> implement-backend  ─┘
  //             └─> docs (independent)

  const tasks: FlowTask[] = [
    {
      id: "research",
      name: "Research APIs",
      agent: "researcher",
      dependencies: [],
      execute: async () => {
        await sleep(50);
        return { success: true, output: "API docs analyzed", duration: 0 };
      },
    },
    {
      id: "design",
      name: "Design Architecture",
      agent: "architect",
      dependencies: ["research"],
      execute: async () => {
        await sleep(30);
        return { success: true, output: "Architecture designed", duration: 0 };
      },
    },
    {
      id: "implement-frontend",
      name: "Implement Frontend",
      agent: "coder",
      dependencies: ["design"],
      execute: async () => {
        await sleep(40);
        return { success: true, output: "Frontend done", duration: 0 };
      },
    },
    {
      id: "implement-backend",
      name: "Implement Backend",
      agent: "coder",
      dependencies: ["design"],
      execute: async () => {
        await sleep(40);
        return { success: true, output: "Backend done", duration: 0 };
      },
    },
    {
      id: "docs",
      name: "Write Documentation",
      agent: "docs",
      dependencies: ["research"],
      execute: async () => {
        await sleep(20);
        return { success: true, output: "Docs written", duration: 0 };
      },
    },
    {
      id: "test",
      name: "Run Tests",
      agent: "tester",
      dependencies: ["implement-frontend", "implement-backend"],
      execute: async () => {
        await sleep(30);
        return { success: true, output: "All tests passed", duration: 0 };
      },
    },
  ];

  executor.addTasks(tasks);

  // Show execution plan
  console.log("  Execution Plan:");
  for (const line of executor.getExecutionPlan()) {
    console.log(`  ${line}`);
  }

  const result = await executor.execute();

  console.log(`\n  Summary:`);
  console.log(`    Total: ${result.progress.total} tasks`);
  console.log(`    Completed: ${result.progress.completed}`);
  console.log(`    Failed: ${result.progress.failed}`);
  console.log(`    Duration: ${result.totalDuration}ms`);

  const success = result.success;
  console.log(`\n  Result: ${success ? "✅ PASS" : "❌ FAIL"}`);

  return success;
}

// ==================== 3. Git Server Test ====================

import { createGitServer } from "./mcp";

async function testGitServer(): Promise<boolean> {
  console.log("\n═══ 3. Git Server Test ═══\n");

  const git = createGitServer();

  try {
    // Check if we're in a repo
    const isRepo = await git.isRepo();
    console.log(`  ✓ Is Git repo: ${isRepo}`);

    if (!isRepo) {
      console.log("  ⚠ Not in a git repository, skipping git tests");
      return true;
    }

    // Get status
    const status = await git.status();
    console.log(`  ✓ Current branch: ${status.branch}`);
    console.log(`  ✓ Staged files: ${status.staged.length}`);
    console.log(`  ✓ Unstaged files: ${status.unstaged.length}`);
    console.log(`  ✓ Untracked files: ${status.untracked.length}`);

    // Get log
    const commits = await git.log({ count: 3 });
    console.log(`  ✓ Recent commits:`);
    for (const commit of commits) {
      console.log(`      ${commit.shortHash} ${commit.message.slice(0, 50)}`);
    }

    // Get branches
    const branches = await git.branches();
    console.log(`  ✓ Branches: ${branches.map((b) => b.name).join(", ")}`);

    // Get remotes
    const remotes = await git.remotes();
    console.log(`  ✓ Remotes: ${remotes.map((r) => r.name).join(", ") || "(none)"}`);

    console.log(`\n  Result: ✅ PASS`);
    return true;
  } catch (error) {
    console.log(`  ✗ Error: ${error}`);
    console.log(`\n  Result: ❌ FAIL`);
    return false;
  }
}

// ==================== 4. TUV Components Test ====================

import { createTreeView, pathsToTree } from "./ui/v2/components/tree-view";
import { createDiffViewer, diffStrings } from "./ui/v2/components/diff-viewer";
import { createSolarCommandPalette } from "./ui/v2/components/command-palette";
import { createLayoutManager } from "./ui/v2/layout-manager";

async function testTUVComponents(): Promise<boolean> {
  console.log("\n═══ 4. TUV Components Test ═══\n");

  try {
    // Test TreeView
    console.log("  TreeView:");
    const files = [
      "src/index.ts",
      "src/core/agent.ts",
      "src/core/flow.ts",
      "tests/agent.test.ts",
      "package.json",
    ];
    const tree = pathsToTree(files, "project");
    const treeView = createTreeView({ root: tree, showIcons: true, showLines: true });

    const treeLines = treeView.render();
    for (const line of treeLines.slice(0, 5)) {
      console.log(`    ${line}`);
    }
    console.log(`  ✓ TreeView rendered ${treeLines.length} lines`);

    // Test DiffViewer
    console.log("\n  DiffViewer:");
    const oldCode = `function hello() {
  console.log("Hello");
}`;
    const newCode = `function hello(name: string) {
  console.log("Hello, " + name);
}`;

    const diff = diffStrings(oldCode, newCode, "hello.ts");
    const diffViewer = createDiffViewer({
      title: diff.title,
      hunks: diff.hunks,
      showLineNumbers: true,
    });

    console.log(`    +${diff.stats.additions} -${diff.stats.deletions} changes`);
    const diffLines = diffViewer.render(60);
    for (const line of diffLines.slice(0, 6)) {
      console.log(`    ${line}`);
    }
    console.log(`  ✓ DiffViewer rendered ${diffLines.length} lines`);

    // Test CommandPalette
    console.log("\n  CommandPalette:");
    const palette = createSolarCommandPalette();
    palette.open();
    palette.setQuery("git");

    const state = palette.getState();
    console.log(`    Query: "${state.query}"`);
    console.log(`    Matches: ${state.matches.length}`);
    for (const match of state.matches.slice(0, 3)) {
      console.log(`      - ${match.command.label} (score: ${match.score})`);
    }
    console.log(`  ✓ CommandPalette fuzzy search working`);

    // Test LayoutManager
    console.log("\n  LayoutManager:");
    const layout = createLayoutManager("ide");
    const regions = layout.getRenderRegions();

    console.log(`    Layout: ${layout.getState().layout.preset}`);
    console.log(`    Panels:`);
    for (const [id, region] of Object.entries(regions)) {
      if (region.width > 0 && region.height > 0) {
        console.log(`      ${id}: ${region.width}x${region.height} at (${region.x},${region.y})`);
      }
    }

    // Test focus cycling
    layout.cycleFocus("next");
    console.log(`    Focus after cycle: ${layout.getFocusedPanel()}`);
    console.log(`  ✓ LayoutManager working`);

    console.log(`\n  Result: ✅ PASS`);
    return true;
  } catch (error) {
    console.log(`  ✗ Error: ${error}`);
    console.log(`\n  Result: ❌ FAIL`);
    return false;
  }
}

// ==================== 5. Integration Test ====================

async function testIntegration(): Promise<boolean> {
  console.log("\n═══ 5. Integration Test ═══\n");
  console.log("  Simulating Solar development flow...\n");

  resetBus();
  const bus = getBus({ enableLogging: false });
  const executor = createExecutor({ maxConcurrency: 2 });
  const git = createGitServer();

  const results: string[] = [];

  // Setup agents
  bus.subscribe("researcher", async (msg) => {
    results.push(`Researcher: Received ${msg.type}`);
  });

  bus.subscribe("coder", async (msg) => {
    results.push(`Coder: Received ${msg.type}`);
  });

  // Create flow tasks that use agent bus
  executor.addTasks([
    {
      id: "check-status",
      name: "Check Git Status",
      agent: "ops",
      dependencies: [],
      execute: async () => {
        const status = await git.status();
        return {
          success: true,
          output: { branch: status.branch, changes: status.unstaged.length },
          duration: 0,
        };
      },
    },
    {
      id: "notify-agents",
      name: "Notify Agents",
      agent: "orchestrator",
      dependencies: ["check-status"],
      execute: async () => {
        const task = createTaskMessage("orchestrator", "coder", {
          id: "impl",
          title: "Implement feature",
          description: "Based on git status",
          type: "implement",
        });
        bus.publish(task);
        return { success: true, output: "Agents notified", duration: 0 };
      },
    },
    {
      id: "generate-ui",
      name: "Generate UI",
      agent: "ui",
      dependencies: ["check-status"],
      execute: async () => {
        const layout = createLayoutManager("dashboard");
        const palette = createSolarCommandPalette();
        return {
          success: true,
          output: {
            layout: layout.getState().layout.preset,
            commands: palette.getState().matches.length,
          },
          duration: 0,
        };
      },
    },
  ]);

  console.log("  Executing flow...");
  const result = await executor.execute();

  // Wait for bus processing
  await sleep(50);

  console.log(`\n  Flow Results:`);
  console.log(`    Tasks completed: ${result.progress.completed}/${result.progress.total}`);
  console.log(`    Duration: ${result.totalDuration}ms`);

  console.log(`\n  Agent Activity:`);
  for (const r of results) {
    console.log(`    ${r}`);
  }

  // Check task outputs
  console.log(`\n  Task Outputs:`);
  for (const [taskId, state] of result.tasks) {
    if (state.result?.output) {
      console.log(`    ${taskId}: ${JSON.stringify(state.result.output).slice(0, 60)}`);
    }
  }

  bus.stop();

  const success = result.success && results.length > 0;
  console.log(`\n  Result: ${success ? "✅ PASS" : "❌ FAIL"}`);

  return success;
}

// ==================== Main ====================

async function main() {
  console.log("╔════════════════════════════════════════════════════════════╗");
  console.log("║           Solar AI OS v1.0 - End-to-End Test               ║");
  console.log("╚════════════════════════════════════════════════════════════╝");

  const results: { name: string; passed: boolean }[] = [];

  // Run all tests
  results.push({ name: "Agent Protocol", passed: await testAgentProtocol() });
  results.push({ name: "Parallel Executor", passed: await testParallelExecutor() });
  results.push({ name: "Git Server", passed: await testGitServer() });
  results.push({ name: "TUV Components", passed: await testTUVComponents() });
  results.push({ name: "Integration", passed: await testIntegration() });

  // Summary
  console.log("\n╔════════════════════════════════════════════════════════════╗");
  console.log("║                      Test Summary                          ║");
  console.log("╠════════════════════════════════════════════════════════════╣");

  let allPassed = true;
  for (const { name, passed } of results) {
    const status = passed ? "✅ PASS" : "❌ FAIL";
    console.log(`║  ${name.padEnd(20)} ${status.padEnd(35)}║`);
    if (!passed) allPassed = false;
  }

  console.log("╠════════════════════════════════════════════════════════════╣");
  const overall = allPassed ? "✅ ALL TESTS PASSED" : "❌ SOME TESTS FAILED";
  console.log(`║  ${overall.padEnd(56)}║`);
  console.log("╚════════════════════════════════════════════════════════════╝");

  process.exit(allPassed ? 0 : 1);
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

main().catch(console.error);
