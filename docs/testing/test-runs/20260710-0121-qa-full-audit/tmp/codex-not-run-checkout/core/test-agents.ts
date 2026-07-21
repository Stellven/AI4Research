/**
 * Solar Agent 全量测试
 *
 * 验证所有 13 个 Agent 的通信能力
 */

import {
  AGENTS,
  getBus,
  resetBus,
  createTaskMessage,
  createResultMessage,
  createHandoffMessage,
  createMessage,
  getAgentsForPhase,
  type AgentId,
  type AgentMessage,
} from "./agent";

// ==================== Test Utilities ====================

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

interface TestResult {
  name: string;
  passed: boolean;
  details?: string;
}

const results: TestResult[] = [];

function pass(name: string, details?: string) {
  results.push({ name, passed: true, details });
  console.log(`  ✅ ${name}${details ? ` - ${details}` : ""}`);
}

function fail(name: string, details?: string) {
  results.push({ name, passed: false, details });
  console.log(`  ❌ ${name}${details ? ` - ${details}` : ""}`);
}

// ==================== Test 1: Agent Registry ====================

async function testAgentRegistry(): Promise<void> {
  console.log("\n═══ 1. Agent Registry Test ═══\n");

  const agentIds = Object.keys(AGENTS);
  console.log(`  Found ${agentIds.length} agents:\n`);

  console.log("  ┌────────────┬────────┬─────────────────────────────────┬──────────────┐");
  console.log("  │ Agent      │ Emoji  │ Role                            │ Phases       │");
  console.log("  ├────────────┼────────┼─────────────────────────────────┼──────────────┤");

  for (const [id, info] of Object.entries(AGENTS)) {
    const role = info.role.slice(0, 30).padEnd(30);
    const phases = info.phase.join(",").padEnd(12);
    console.log(`  │ ${id.padEnd(10)} │ ${info.emoji.padEnd(6)} │ ${role} │ ${phases} │`);
  }

  console.log("  └────────────┴────────┴─────────────────────────────────┴──────────────┘");

  if (agentIds.length === 13) {
    pass("Agent count", "13 agents registered");
  } else {
    fail("Agent count", `Expected 13, got ${agentIds.length}`);
  }

  // Test phase mapping
  const p1Agents = getAgentsForPhase("P1");
  const p3Agents = getAgentsForPhase("P3");
  const p5Agents = getAgentsForPhase("P5");

  console.log(`\n  Phase Mapping:`);
  console.log(`    P1 (研究): ${p1Agents.join(", ")}`);
  console.log(`    P3 (实现): ${p3Agents.join(", ")}`);
  console.log(`    P5 (收尾): ${p5Agents.join(", ")}`);

  if (p1Agents.includes("researcher")) {
    pass("Phase P1 mapping", "researcher in P1");
  } else {
    fail("Phase P1 mapping");
  }
}

// ==================== Test 2: All Agents Subscribe ====================

async function testAllAgentsSubscribe(): Promise<void> {
  console.log("\n═══ 2. All Agents Subscribe Test ═══\n");

  resetBus();
  const bus = getBus({ enableLogging: false });

  const subscribed: string[] = [];
  const received: Map<string, AgentMessage[]> = new Map();

  // Subscribe all agents
  for (const agentId of Object.keys(AGENTS)) {
    received.set(agentId, []);

    bus.subscribe(agentId as AgentId, async (message) => {
      received.get(agentId)!.push(message);
    });

    subscribed.push(agentId);
  }

  // Also subscribe orchestrator (not in AGENTS but used for coordination)
  bus.subscribe("orchestrator", async () => {});

  console.log(`  Subscribed: ${subscribed.length} agents`);

  const stats = bus.getStats();
  if (stats.activeSubscriptions === 14) {
    // 13 agents + orchestrator
    pass("All agents subscribed", `${stats.activeSubscriptions} subscriptions`);
  } else {
    fail("Agent subscription", `Expected 14, got ${stats.activeSubscriptions}`);
  }

  bus.stop();
}

// ==================== Test 3: Point-to-Point Communication ====================

async function testPointToPoint(): Promise<void> {
  console.log("\n═══ 3. Point-to-Point Communication Test ═══\n");

  resetBus();
  const bus = getBus({ enableLogging: false });

  const received: Map<string, number> = new Map();

  // Subscribe all agents
  for (const agentId of Object.keys(AGENTS)) {
    received.set(agentId, 0);
    bus.subscribe(agentId as AgentId, async () => {
      received.set(agentId, (received.get(agentId) ?? 0) + 1);
    });
  }

  // Test orchestrator → each agent
  console.log("  Testing orchestrator → each agent:");
  let successCount = 0;

  for (const agentId of Object.keys(AGENTS)) {
    const task = createTaskMessage("orchestrator", agentId as AgentId, {
      id: `task_${agentId}`,
      title: `Test task for ${agentId}`,
      description: "Testing communication",
      type: "implement",
    });

    bus.publish(task);
  }

  // Wait longer for all messages to be processed (bus processes at 10ms intervals)
  await sleep(300);

  for (const [agentId, count] of received) {
    if (count === 1) {
      successCount++;
      console.log(`    ${AGENTS[agentId].emoji} ${agentId}: ✓ received`);
    } else {
      console.log(`    ${AGENTS[agentId].emoji} ${agentId}: ✗ count=${count}`);
    }
  }

  if (successCount === 13) {
    pass("Point-to-point", "All 13 agents received messages");
  } else {
    fail("Point-to-point", `${successCount}/13 agents received`);
  }

  bus.stop();
}

// ==================== Test 4: Broadcast Communication ====================

async function testBroadcast(): Promise<void> {
  console.log("\n═══ 4. Broadcast Communication Test ═══\n");

  resetBus();
  const bus = getBus({ enableLogging: false });

  const received: Set<string> = new Set();

  // Subscribe all agents
  for (const agentId of Object.keys(AGENTS)) {
    bus.subscribe(agentId as AgentId, async () => {
      received.add(agentId);
    });
  }

  // Broadcast from orchestrator
  const broadcast = createMessage(
    "event",
    "orchestrator",
    "broadcast",
    { action: "phase-change", data: { from: "P2", to: "P3" } },
    { priority: "high" }
  );

  bus.publish(broadcast);
  await sleep(100);

  console.log(`  Broadcast received by: ${received.size} agents`);

  if (received.size === 13) {
    pass("Broadcast", "All 13 agents received broadcast");
  } else {
    fail("Broadcast", `${received.size}/13 received`);
  }

  bus.stop();
}

// ==================== Test 5: Agent Handoff ====================

async function testAgentHandoff(): Promise<void> {
  console.log("\n═══ 5. Agent Handoff Test ═══\n");

  resetBus();
  const bus = getBus({ enableLogging: false });

  let handoffReceived = false;
  let handoffAccepted = false;

  // Architect receives handoff request
  bus.subscribe("architect", async (message) => {
    if (message.type === "handoff") {
      handoffReceived = true;
      console.log(`  ${AGENTS.architect.emoji} Architect: Received handoff request`);

      // Accept handoff
      const accept = createHandoffMessage("architect", "researcher", {
        action: "accept",
        reason: "Ready to proceed with design",
        context: {
          currentState: { phase: "P2" },
          completedSteps: ["Research complete"],
          pendingSteps: ["Create design doc"],
        },
      });

      bus.publish(accept);
    }
  });

  // Researcher receives acceptance
  bus.subscribe("researcher", async (message) => {
    if (message.type === "handoff" && (message.payload.data as any)?.action === "accept") {
      handoffAccepted = true;
      console.log(`  ${AGENTS.researcher.emoji} Researcher: Handoff accepted`);
    }
  });

  // Researcher initiates handoff
  const handoff = createHandoffMessage("researcher", "architect", {
    action: "request",
    reason: "Research phase complete",
    context: {
      currentState: { findings: ["API supports REST", "Rate limit: 100/min"] },
      completedSteps: ["Analyzed API docs", "Tested endpoints"],
      pendingSteps: [],
      resources: [{ id: "report", type: "report", content: "..." }],
    },
    recommendations: ["Consider caching", "Use batch API"],
  });

  console.log(`  ${AGENTS.researcher.emoji} Researcher: Initiating handoff to Architect`);
  bus.publish(handoff);

  await sleep(100);

  if (handoffReceived && handoffAccepted) {
    pass("Agent handoff", "Researcher → Architect handoff complete");
  } else {
    fail("Agent handoff", `received=${handoffReceived}, accepted=${handoffAccepted}`);
  }

  bus.stop();
}

// ==================== Test 6: Multi-Agent Chain ====================

async function testMultiAgentChain(): Promise<void> {
  console.log("\n═══ 6. Multi-Agent Chain Test ═══\n");

  resetBus();
  const bus = getBus({ enableLogging: false });

  const chain: string[] = [];

  // Setup chain: orchestrator → researcher → architect → coder → tester → reviewer
  bus.subscribe("researcher", async (message) => {
    if (message.type === "task") {
      chain.push("researcher");
      console.log(`  ${AGENTS.researcher.emoji} Researcher: Processing...`);

      await sleep(20);

      // Forward to architect
      const task = createTaskMessage("researcher", "architect", {
        id: "design",
        title: "Design based on research",
        description: "Research complete",
        type: "design",
      });
      bus.publish(task);
    }
  });

  bus.subscribe("architect", async (message) => {
    if (message.type === "task") {
      chain.push("architect");
      console.log(`  ${AGENTS.architect.emoji} Architect: Designing...`);

      await sleep(20);

      // Forward to coder
      const task = createTaskMessage("architect", "coder", {
        id: "implement",
        title: "Implement design",
        description: "Design complete",
        type: "implement",
      });
      bus.publish(task);
    }
  });

  bus.subscribe("coder", async (message) => {
    if (message.type === "task") {
      chain.push("coder");
      console.log(`  ${AGENTS.coder.emoji} Coder: Implementing...`);

      await sleep(20);

      // Forward to tester
      const task = createTaskMessage("coder", "tester", {
        id: "test",
        title: "Test implementation",
        description: "Implementation complete",
        type: "test",
      });
      bus.publish(task);
    }
  });

  bus.subscribe("tester", async (message) => {
    if (message.type === "task") {
      chain.push("tester");
      console.log(`  ${AGENTS.tester.emoji} Tester: Testing...`);

      await sleep(20);

      // Forward to reviewer
      const task = createTaskMessage("tester", "reviewer", {
        id: "review",
        title: "Review code",
        description: "Tests passed",
        type: "review",
      });
      bus.publish(task);
    }
  });

  bus.subscribe("reviewer", async (message) => {
    if (message.type === "task") {
      chain.push("reviewer");
      console.log(`  ${AGENTS.reviewer.emoji} Reviewer: Reviewing...`);

      // Send result back to orchestrator
      const result = createResultMessage("reviewer", "orchestrator", "review", {
        action: "complete",
        output: { approved: true },
      }, message.correlationId ?? message.id);
      bus.publish(result);
    }
  });

  let finalResult = false;
  bus.subscribe("orchestrator", async (message) => {
    if (message.type === "result") {
      finalResult = true;
      console.log(`  🎯 Orchestrator: Chain complete!`);
    }
  });

  // Start the chain
  console.log(`  🎯 Orchestrator: Starting chain...`);
  const task = createTaskMessage("orchestrator", "researcher", {
    id: "research",
    title: "Research new feature",
    description: "Start the chain",
    type: "research",
  });
  bus.publish(task);

  // Wait for chain to complete
  await sleep(300);

  console.log(`\n  Chain execution: ${chain.join(" → ")}`);

  const expectedChain = ["researcher", "architect", "coder", "tester", "reviewer"];
  const chainMatch = JSON.stringify(chain) === JSON.stringify(expectedChain);

  if (chainMatch && finalResult) {
    pass("Multi-agent chain", "5-agent chain executed successfully");
  } else {
    fail("Multi-agent chain", `chainMatch=${chainMatch}, finalResult=${finalResult}`);
  }

  bus.stop();
}

// ==================== Test 7: Parallel Agent Execution ====================

async function testParallelAgents(): Promise<void> {
  console.log("\n═══ 7. Parallel Agent Execution Test ═══\n");

  resetBus();
  const bus = getBus({ enableLogging: false });

  const completed: Set<string> = new Set();
  const startTime = Date.now();

  // Setup parallel agents: guard, docs, secretary (all can run in P5)
  const parallelAgents = ["guard", "docs", "secretary", "reporter"];

  for (const agentId of parallelAgents) {
    bus.subscribe(agentId as AgentId, async (message) => {
      if (message.type === "task") {
        console.log(`  ${AGENTS[agentId].emoji} ${agentId}: Started`);
        await sleep(50); // Simulate work
        completed.add(agentId);
        console.log(`  ${AGENTS[agentId].emoji} ${agentId}: Completed`);
      }
    });
  }

  // Send tasks to all parallel agents at once
  console.log("  Sending tasks to 4 agents in parallel...\n");

  for (const agentId of parallelAgents) {
    const task = createTaskMessage("orchestrator", agentId as AgentId, {
      id: `parallel_${agentId}`,
      title: `Parallel task for ${agentId}`,
      description: "Run in parallel",
      type: "analyze",
    });
    bus.publish(task);
  }

  await sleep(150);

  const duration = Date.now() - startTime;

  console.log(`\n  Completed: ${completed.size}/${parallelAgents.length} in ${duration}ms`);

  // If truly parallel, should complete in ~50-100ms, not 200ms (4 * 50ms)
  if (completed.size === 4 && duration < 200) {
    pass("Parallel execution", `4 agents completed in ${duration}ms`);
  } else {
    fail("Parallel execution", `completed=${completed.size}, duration=${duration}ms`);
  }

  bus.stop();
}

// ==================== Test 8: Error Handling ====================

async function testErrorHandling(): Promise<void> {
  console.log("\n═══ 8. Error Handling Test ═══\n");

  resetBus();
  const bus = getBus({
    enableLogging: false,
    onError: (error, message) => {
      console.log(`  ⚠ Bus error handler: ${error.message}`);
    },
  });

  let errorReceived = false;

  bus.subscribe("orchestrator", async (message) => {
    if (message.type === "error") {
      errorReceived = true;
      console.log(`  🎯 Orchestrator: Received error from ${message.from}`);
    }
  });

  bus.subscribe("coder", async (message) => {
    if (message.type === "task") {
      console.log(`  ${AGENTS.coder.emoji} Coder: Task failed, sending error`);

      const error = createMessage(
        "error",
        "coder",
        "orchestrator",
        {
          action: "error",
          error: {
            code: "COMPILE_ERROR",
            message: "Syntax error on line 42",
            details: { file: "index.ts", line: 42 },
            recoverable: true,
          },
        },
        { priority: "high", correlationId: message.id }
      );

      bus.publish(error);
    }
  });

  // Send task that will fail
  const task = createTaskMessage("orchestrator", "coder", {
    id: "failing_task",
    title: "Task that will fail",
    description: "Testing error handling",
    type: "implement",
  });
  bus.publish(task);

  await sleep(100);

  if (errorReceived) {
    pass("Error handling", "Error properly propagated to orchestrator");
  } else {
    fail("Error handling", "Error not received");
  }

  bus.stop();
}

// ==================== Main ====================

async function main() {
  console.log("╔════════════════════════════════════════════════════════════╗");
  console.log("║          Solar Agent System - Full Test Suite              ║");
  console.log("╚════════════════════════════════════════════════════════════╝");

  await testAgentRegistry();
  await testAllAgentsSubscribe();
  await testPointToPoint();
  await testBroadcast();
  await testAgentHandoff();
  await testMultiAgentChain();
  await testParallelAgents();
  await testErrorHandling();

  // Summary
  console.log("\n╔════════════════════════════════════════════════════════════╗");
  console.log("║                      Test Summary                          ║");
  console.log("╠════════════════════════════════════════════════════════════╣");

  const passed = results.filter((r) => r.passed).length;
  const failed = results.filter((r) => !r.passed).length;

  for (const r of results) {
    const status = r.passed ? "✅" : "❌";
    const details = r.details ? ` (${r.details})` : "";
    console.log(`║  ${status} ${(r.name + details).padEnd(54)}║`);
  }

  console.log("╠════════════════════════════════════════════════════════════╣");
  console.log(`║  Passed: ${passed}/${results.length}  Failed: ${failed}/${results.length}`.padEnd(60) + "║");
  console.log("╚════════════════════════════════════════════════════════════╝");

  if (failed > 0) {
    console.log("\n❌ Some tests failed!");
    process.exit(1);
  } else {
    console.log("\n✅ All agent tests passed!");
    process.exit(0);
  }
}

main().catch(console.error);
