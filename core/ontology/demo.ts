/**
 * Solar Ontology Demo
 * 演示本体系统的使用
 */

import { Database } from "bun:sqlite";
import { OntologyManager } from "./manager";
import { PreferenceObserver, SessionData } from "./observer";

async function demo() {
  console.log("=== Solar Ontology Demo ===\n");

  // 1. 初始化
  const dbPath = process.env.SOLAR_DB_PATH || `${process.env.HOME}/.solar/db/solar.db`;
  console.log(`[1] 初始化数据库: ${dbPath}`);
  const db = new Database(dbPath);
  const ontology = new OntologyManager(db);
  ontology.initialize();
  console.log("    ✓ 本体系统初始化完成\n");

  // 2. 会话开始
  const sessionId = `demo_${Date.now()}`;
  console.log(`[2] 会话开始: ${sessionId}`);
  const snapshot = await ontology.onSessionStart(sessionId);
  console.log(`    版本: ${snapshot.version}`);
  console.log(`    情景记忆: ${snapshot.memory.episodic.length} 条`);
  console.log(`    语义记忆: ${snapshot.memory.semantic.length} 条`);
  console.log(`    程序记忆: ${snapshot.memory.procedural.length} 条`);
  console.log(`    偏好维度: ${snapshot.personality.preferences.length} 个`);
  console.log(`    关系: ${snapshot.personality.relationships.length} 个`);
  console.log();

  // 3. 显示当前偏好
  console.log("[3] 当前偏好状态:");
  const prefs = ontology.getAllPreferences();
  for (const pref of prefs.slice(0, 5)) {
    const value = pref.current_value ?? pref.default_value;
    const conf = (pref.confidence * 100).toFixed(0);
    console.log(`    ${pref.name}: ${value.toFixed(2)} (置信度: ${conf}%)`);
  }
  console.log();

  // 4. 获取 Agent 上下文
  console.log("[4] Coder Agent 上下文:");
  const coderContext = ontology.getAgentContext("coder");
  console.log("    规则:");
  for (const [key, value] of Object.entries(coderContext.rules).slice(0, 5)) {
    console.log(`      ${key}: ${JSON.stringify(value)}`);
  }
  console.log("\n    Prompt 注入内容:");
  const promptLines = coderContext.toPrompt().split("\n");
  for (const line of promptLines.slice(0, 10)) {
    console.log(`      ${line}`);
  }
  console.log();

  // 5. 模拟用户反馈学习
  console.log("[5] 模拟用户反馈学习:");
  const observer = new PreferenceObserver();

  const feedback1 = "太长了，简洁点";
  console.log(`    用户反馈: "${feedback1}"`);
  const signals1 = observer.extractFromExplicitFeedback(feedback1);
  console.log(`    提取信号: ${signals1.length} 个`);
  for (const s of signals1) {
    console.log(`      - ${s.dimension_id}: ${s.value.toFixed(2)} (权重: ${s.weight})`);
  }
  console.log();

  // 6. 模拟会话数据
  console.log("[6] 模拟会话结束:");
  const sessionData: SessionData = {
    sessionId,
    startTime: new Date(),
    messageCount: 150,
    tokenUsage: { input: 50000, output: 20000 },
    toolCalls: [
      { tool: "Bash", count: 20, successRate: 0.9 },
      { tool: "Read", count: 30, successRate: 1.0 },
      { tool: "Write", count: 10, successRate: 0.95 },
      { tool: "test", count: 8, successRate: 0.8 },
    ],
    agentInteractions: [
      { agent: "coder", count: 15 },
      { agent: "tester", count: 5 },
    ],
    userFeedback: [feedback1],
  };

  const sessionSignals = observer.extractSignals(sessionData);
  console.log(`    会话信号: ${sessionSignals.length} 个`);
  for (const s of sessionSignals.slice(0, 5)) {
    console.log(`      - ${s.dimension_id}: ${s.value.toFixed(2)}`);
  }

  await ontology.onSessionEnd(sessionId, sessionSignals);
  console.log("    ✓ 会话结束，偏好已更新\n");

  // 7. 显示更新后的偏好
  console.log("[7] 更新后的偏好状态:");
  const updatedPrefs = ontology.getAllPreferences();
  for (const pref of updatedPrefs.slice(0, 5)) {
    const value = pref.current_value ?? pref.default_value;
    const conf = (pref.confidence * 100).toFixed(0);
    console.log(`    ${pref.name}: ${value.toFixed(2)} (置信度: ${conf}%)`);
  }
  console.log();

  // 8. 显示监护人信息
  console.log("[8] 第一规律:");
  const guardian = ontology.getGuardian();
  if (guardian) {
    console.log(`    监护人: ${guardian.entity_name}`);
    console.log(`    重要性: ${guardian.importance}`);
    console.log(`    上下文: ${JSON.stringify(guardian.context)}`);
  } else {
    console.log("    (未设置监护人)");
  }
  console.log();

  console.log("=== Demo 完成 ===");

  db.close();
}

// Run demo
demo().catch(console.error);
