#!/usr/bin/env bun
/**
 * 测试三级优先级系统
 */

import { MessageHandler } from "./message-handler";

const handler = new MessageHandler();
const testSender = "+8613800138000";

interface TestCase {
  name: string;
  message: string;
  expectedPriority: string;
}

const tests: TestCase[] = [
  // 高优先级测试
  { name: "高优先级-马上", message: "马上搜索 agent", expectedPriority: "high" },
  { name: "高优先级-立即", message: "立即查天气 北京", expectedPriority: "high" },
  { name: "高优先级-快点", message: "快点给我 backlog 列表", expectedPriority: "high" },
  { name: "高优先级-给我", message: "给我看看状态", expectedPriority: "high" },

  // 常设级测试
  {
    name: "常设级-定期",
    message: "定期看看 Moltbook 有没有新回复",
    expectedPriority: "scheduled",
  },
  {
    name: "常设级-定时",
    message: "定时检查知乎收藏",
    expectedPriority: "scheduled",
  },
  {
    name: "常设级-经常看看",
    message: "经常看看 HN 热门",
    expectedPriority: "scheduled",
  },

  // 临时级测试
  {
    name: "临时级-你看看",
    message: "你看看搜索 agent",
    expectedPriority: "temporary",
  },
  { name: "临时级-看看", message: "看看文件搜索 task", expectedPriority: "temporary" },
  { name: "临时级-分析下", message: "分析下天气情况", expectedPriority: "temporary" },
  {
    name: "临时级-帮我查",
    message: "帮我查一下 backlog",
    expectedPriority: "temporary",
  },
];

console.log("╭────────────────────────────────────────────────────╮");
console.log("│     Solar 消息监听器 - 三级优先级测试              │");
console.log("╰────────────────────────────────────────────────────╯\n");

let passed = 0;
let failed = 0;

for (const test of tests) {
  process.stdout.write(`${test.name.padEnd(25)} ... `);

  try {
    const result = await handler.processMessage(testSender, test.message);

    // 查询数据库获取实际优先级
    const db = (handler as any).db;
    const record = db
      .prepare(
        `
      SELECT priority, status, deferred_reason
      FROM bl_message_tasks
      WHERE content = ?
      ORDER BY created_at DESC
      LIMIT 1
    `,
      )
      .get(test.message) as any;

    if (record && record.priority === test.expectedPriority) {
      console.log(
        `✓ PASS (${record.priority}, ${record.status}${record.deferred_reason ? ", " + record.deferred_reason.substring(0, 30) + "..." : ""})`,
      );
      passed++;
    } else {
      console.log(`✗ FAIL (期望: ${test.expectedPriority}, 实际: ${record?.priority || "未知"})`);
      failed++;
    }
  } catch (error: any) {
    console.log(`✗ ERROR (${error.message})`);
    failed++;
  }
}

handler.close();

console.log("\n" + "─".repeat(56));
console.log(`结果: ${passed} 通过, ${failed} 失败 (总计 ${tests.length} 个测试)`);
console.log("─".repeat(56));

process.exit(failed > 0 ? 1 : 0);
