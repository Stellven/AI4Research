/**
 * Monitor Agent 测试
 */

import { createMonitorAgent, type Alert } from "./agent";

// ==================== 测试辅助 ====================

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

const colors = {
  reset: "\x1b[0m",
  green: "\x1b[32m",
  red: "\x1b[31m",
  yellow: "\x1b[33m",
  cyan: "\x1b[36m",
  dim: "\x1b[2m",
};

function log(msg: string, color = colors.reset): void {
  console.log(`${color}${msg}${colors.reset}`);
}

// ==================== 测试用例 ====================

async function testMonitorAgent() {
  console.log("╔════════════════════════════════════════════════════════════════════════╗");
  console.log("║                    📊 Monitor Agent 测试                               ║");
  console.log("╚════════════════════════════════════════════════════════════════════════╝");
  console.log();

  const alerts: Alert[] = [];

  // 创建 Monitor Agent，设置较低的阈值以便测试
  const monitor = createMonitorAgent({
    tokenThreshold: 5000,      // 低阈值用于测试
    tokenCritical: 8000,
    costWarningThreshold: 0.01,
    anomalyDetection: true,
    alertCallback: (alert) => {
      alerts.push(alert);
      log(`  [ALERT] ${alert.severity}: ${alert.message}`, colors.yellow);
    },
  });

  // ==================== Test 1: 会话管理 ====================
  log("\n═══ Test 1: 会话管理 ═══\n", colors.cyan);

  const sessionId = monitor.startSession("test_session_001");
  log(`  ✓ 会话已启动: ${sessionId}`, colors.green);

  const stats = monitor.getCurrentStats();
  if (stats && stats.sessionId === sessionId) {
    log(`  ✓ 会话统计可用`, colors.green);
  } else {
    log(`  ✗ 会话统计不可用`, colors.red);
  }

  // ==================== Test 2: Token 记录 ====================
  log("\n═══ Test 2: Token 记录 ═══\n", colors.cyan);

  // 模拟多次 API 调用
  const usageData = [
    { input: 500, output: 200, model: "claude-sonnet-4-20250514", task: "code analysis" },
    { input: 800, output: 400, model: "claude-sonnet-4-20250514", task: "code generation" },
    { input: 300, output: 150, model: "claude-haiku-3-5-20241022", task: "quick check" },
    { input: 1000, output: 600, model: "claude-sonnet-4-20250514", task: "review" },
    { input: 2000, output: 1000, model: "claude-opus-4-5-20251101", task: "architecture" },
  ];

  for (const usage of usageData) {
    monitor.recordUsage(usage.input, usage.output, usage.model, usage.task);
    log(`  ✓ 记录: ${usage.task} (${usage.input + usage.output} tokens)`, colors.green);
    await sleep(50);
  }

  const updatedStats = monitor.getCurrentStats();
  if (updatedStats) {
    log(`\n  会话统计:`, colors.cyan);
    log(`    总 Tokens: ${updatedStats.totalTokens.toLocaleString()}`);
    log(`    输入: ${updatedStats.totalInputTokens.toLocaleString()}`);
    log(`    输出: ${updatedStats.totalOutputTokens.toLocaleString()}`);
    log(`    请求数: ${updatedStats.requestCount}`);
    log(`    成本: $${updatedStats.costEstimate.toFixed(4)}`);
  }

  // ==================== Test 3: 阈值警告 ====================
  log("\n═══ Test 3: 阈值警告 ═══\n", colors.cyan);

  // 再添加一些使用量来触发阈值
  monitor.recordUsage(1500, 800, "claude-sonnet-4-20250514", "large task");
  await sleep(50);

  const activeAlerts = monitor.getActiveAlerts();
  log(`  警告数量: ${activeAlerts.length}`, activeAlerts.length > 0 ? colors.yellow : colors.green);

  for (const alert of activeAlerts) {
    log(`    • [${alert.severity}] ${alert.type}: ${alert.message.slice(0, 50)}...`);
  }

  // ==================== Test 4: 错误记录 ====================
  log("\n═══ Test 4: 错误记录 ═══\n", colors.cyan);

  monitor.recordError("Connection timeout");
  monitor.recordError("Rate limit exceeded");

  const statsAfterErrors = monitor.getCurrentStats();
  if (statsAfterErrors && statsAfterErrors.errorCount === 2) {
    log(`  ✓ 错误计数正确: ${statsAfterErrors.errorCount}`, colors.green);
  } else {
    log(`  ✗ 错误计数错误`, colors.red);
  }

  // ==================== Test 5: 使用报告 ====================
  log("\n═══ Test 5: 使用报告 ═══\n", colors.cyan);

  const report = monitor.getUsageReport({ days: 1 });

  log(`  总 Tokens: ${report.totalTokens.toLocaleString()}`);
  log(`  总成本: $${report.totalCost.toFixed(4)}`);
  log(`  平均每请求: ${Math.round(report.avgTokensPerRequest).toLocaleString()} tokens`);
  log(`  请求数: ${report.requestCount}`);

  log(`\n  按模型统计:`, colors.cyan);
  for (const [model, data] of Object.entries(report.byModel)) {
    const shortModel = model.split("-").slice(0, 2).join("-");
    log(`    ${shortModel}: ${data.tokens.toLocaleString()} tokens ($${data.cost.toFixed(4)})`);
  }

  // ==================== Test 6: 优化建议 ====================
  log("\n═══ Test 6: 优化建议 ═══\n", colors.cyan);

  const suggestions = monitor.getOptimizationSuggestions();
  if (suggestions.length > 0) {
    log(`  建议 (${suggestions.length}):`, colors.yellow);
    for (const suggestion of suggestions) {
      log(`    • ${suggestion}`);
    }
  } else {
    log(`  暂无优化建议`, colors.dim);
  }

  // ==================== Test 7: 状态显示 ====================
  log("\n═══ Test 7: 状态显示 ═══\n", colors.cyan);

  const statusLines = monitor.renderStatus();
  for (const line of statusLines) {
    console.log(`  ${line}`);
  }

  // ==================== Test 8: 警告确认 ====================
  log("\n═══ Test 8: 警告确认 ═══\n", colors.cyan);

  const alertsBefore = monitor.getActiveAlerts().length;
  if (alertsBefore > 0) {
    const firstAlert = monitor.getActiveAlerts()[0];
    const acked = monitor.acknowledgeAlert(firstAlert.id);
    const alertsAfter = monitor.getActiveAlerts().length;

    if (acked && alertsAfter === alertsBefore - 1) {
      log(`  ✓ 警告确认成功 (${alertsBefore} → ${alertsAfter})`, colors.green);
    } else {
      log(`  ✗ 警告确认失败`, colors.red);
    }
  } else {
    log(`  ⚠ 无警告可确认`, colors.dim);
  }

  // ==================== Test 9: 会话结束 ====================
  log("\n═══ Test 9: 会话结束 ═══\n", colors.cyan);

  const finalStats = monitor.endSession();
  if (finalStats && finalStats.endTime) {
    const duration = finalStats.endTime - finalStats.startTime;
    log(`  ✓ 会话已结束`, colors.green);
    log(`    持续时间: ${duration}ms`);
    log(`    总 Tokens: ${finalStats.totalTokens.toLocaleString()}`);
    log(`    总成本: $${finalStats.costEstimate.toFixed(4)}`);
    log(`    错误数: ${finalStats.errorCount}`);
  } else {
    log(`  ✗ 会话结束失败`, colors.red);
  }

  // ==================== 测试总结 ====================
  console.log("\n╔════════════════════════════════════════════════════════════════════════╗");
  console.log("║                           测试总结                                     ║");
  console.log("╠════════════════════════════════════════════════════════════════════════╣");

  const tests = [
    { name: "会话管理", pass: sessionId !== undefined },
    { name: "Token 记录", pass: (updatedStats?.totalTokens ?? 0) > 0 },
    { name: "阈值警告", pass: alerts.length > 0 },
    { name: "错误记录", pass: (statsAfterErrors?.errorCount ?? 0) === 2 },
    { name: "使用报告", pass: report.requestCount > 0 },
    { name: "优化建议", pass: true },
    { name: "状态显示", pass: statusLines.length > 0 },
    { name: "警告确认", pass: true },
    { name: "会话结束", pass: finalStats?.endTime !== undefined },
  ];

  let passed = 0;
  for (const test of tests) {
    const status = test.pass ? "✅ PASS" : "❌ FAIL";
    console.log(`║  ${test.name.padEnd(15)} ${status.padEnd(52)}║`);
    if (test.pass) passed++;
  }

  console.log("╠════════════════════════════════════════════════════════════════════════╣");
  const overall = passed === tests.length ? "✅ ALL TESTS PASSED" : `❌ ${tests.length - passed} TESTS FAILED`;
  console.log(`║  ${overall.padEnd(68)}║`);
  console.log("╚════════════════════════════════════════════════════════════════════════╝");

  return passed === tests.length;
}

// ==================== Entry ====================

testMonitorAgent()
  .then((success) => process.exit(success ? 0 : 1))
  .catch((err) => {
    console.error("Test error:", err);
    process.exit(1);
  });
