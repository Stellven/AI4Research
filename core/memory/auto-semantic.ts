#!/usr/bin/env bun
/**
 * Solar 语义记忆自动填充
 *
 * 功能:
 * 1. 检测对话中的重要内容
 * 2. 自动提取为结构化知识
 * 3. 写入 evo_memory_semantic
 *
 * 触发条件:
 * - 用户说"记住"/"重要"/"保存"
 * - 检测到设计决策关键词
 * - 检测到架构讨论关键词
 * - 检测到问题解决方案
 */

import { Database } from "bun:sqlite";
import { readFileSync } from "fs";
import { homedir } from "os";

const DB_PATH = process.env.SOLAR_DB_PATH || `${homedir()}/.solar/db/solar.db`;

interface SemanticMemory {
  namespace: string;
  key: string;
  value: any;
  source_type: "inferred" | "explicit" | "imported";
  confidence: number;
}

// 关键词检测规则
const TRIGGER_KEYWORDS = {
  design_decision: [
    "我们决定", "选择了", "采用", "设计为", "架构是",
    "decided", "chosen", "design", "architecture"
  ],
  problem_solution: [
    "问题是", "解决方案", "原因是", "修复方法",
    "problem", "solution", "root cause", "fix"
  ],
  learning: [
    "学到了", "发现", "教训", "经验",
    "learned", "discovered", "lesson", "experience"
  ],
  important: [
    "重要", "关键", "核心", "必须",
    "important", "critical", "key", "must"
  ],
  remember: [
    "记住", "别忘了", "注意",
    "remember", "don't forget", "note"
  ]
};

// 检测对话内容的重要性
function detectImportance(text: string): {
  isImportant: boolean;
  category: string | null;
  confidence: number;
} {
  const lowerText = text.toLowerCase();

  // 用户显式要求
  if (TRIGGER_KEYWORDS.remember.some(kw => lowerText.includes(kw))) {
    return { isImportant: true, category: "explicit", confidence: 1.0 };
  }

  // 设计决策
  if (TRIGGER_KEYWORDS.design_decision.some(kw => lowerText.includes(kw))) {
    return { isImportant: true, category: "design", confidence: 0.9 };
  }

  // 问题解决
  if (TRIGGER_KEYWORDS.problem_solution.some(kw => lowerText.includes(kw))) {
    return { isImportant: true, category: "solution", confidence: 0.85 };
  }

  // 学习经验
  if (TRIGGER_KEYWORDS.learning.some(kw => lowerText.includes(kw))) {
    return { isImportant: true, category: "learning", confidence: 0.8 };
  }

  // 重要标记
  if (TRIGGER_KEYWORDS.important.some(kw => lowerText.includes(kw))) {
    return { isImportant: true, category: "important", confidence: 0.75 };
  }

  return { isImportant: false, category: null, confidence: 0 };
}

// 提取结构化知识
function extractKnowledge(text: string, category: string): SemanticMemory | null {
  const timestamp = new Date().toISOString();

  switch (category) {
    case "design":
      return {
        namespace: "solar_knowledge/design",
        key: `design_${Date.now()}`,
        value: {
          summary: text.substring(0, 200),
          full_text: text,
          category: "design_decision",
          timestamp
        },
        source_type: "inferred",
        confidence: 0.9
      };

    case "solution":
      return {
        namespace: "solar_knowledge/solutions",
        key: `solution_${Date.now()}`,
        value: {
          summary: text.substring(0, 200),
          full_text: text,
          category: "problem_solution",
          timestamp
        },
        source_type: "inferred",
        confidence: 0.85
      };

    case "learning":
      return {
        namespace: "solar_learnings",
        key: `learning_${Date.now()}`,
        value: {
          insight: text.substring(0, 200),
          context: text,
          timestamp
        },
        source_type: "inferred",
        confidence: 0.8
      };

    case "explicit":
      return {
        namespace: "solar_knowledge/explicit",
        key: `explicit_${Date.now()}`,
        value: {
          content: text,
          timestamp
        },
        source_type: "explicit",
        confidence: 1.0
      };

    default:
      return {
        namespace: "solar_knowledge/general",
        key: `general_${Date.now()}`,
        value: {
          content: text,
          timestamp
        },
        source_type: "inferred",
        confidence: 0.75
      };
  }
}

// 保存到数据库
function saveToSemanticMemory(memory: SemanticMemory): void {
  const db = new Database(DB_PATH);

  try {
    const stmt = db.prepare(`
      INSERT INTO evo_memory_semantic (
        memory_id,
        namespace,
        key,
        value,
        source_type,
        confidence,
        created_at
      ) VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
    `);

    stmt.run(
      `${memory.namespace}:${memory.key}`,
      memory.namespace,
      memory.key,
      JSON.stringify(memory.value),
      memory.source_type,
      memory.confidence
    );

    console.log(`[Auto-Semantic] ✓ 保存记忆: ${memory.namespace}/${memory.key}`);
  } catch (error) {
    console.error("[Auto-Semantic] ✗ 保存失败:", error);
  } finally {
    db.close();
  }
}

// 主函数 - 处理用户消息
function processMessage(text: string): void {
  const detection = detectImportance(text);

  if (detection.isImportant && detection.category) {
    console.log(`[Auto-Semantic] 检测到重要内容 (${detection.category}, confidence: ${detection.confidence})`);

    const knowledge = extractKnowledge(text, detection.category);
    if (knowledge) {
      saveToSemanticMemory(knowledge);
    }
  }
}

// CLI 接口
if (import.meta.main) {
  const args = process.argv.slice(2);

  if (args.length === 0) {
    console.log(`
Usage: bun auto-semantic.ts <command> [args]

Commands:
  process <text>        处理并保存文本
  check <text>          检查文本是否重要 (不保存)
  stats                 显示语义记忆统计

Examples:
  bun auto-semantic.ts process "我们决定使用分布式架构"
  bun auto-semantic.ts check "这是一个普通消息"
  bun auto-semantic.ts stats
`);
    process.exit(0);
  }

  const command = args[0];

  switch (command) {
    case "process":
      const text = args.slice(1).join(" ");
      processMessage(text);
      break;

    case "check":
      const checkText = args.slice(1).join(" ");
      const result = detectImportance(checkText);
      console.log(JSON.stringify(result, null, 2));
      break;

    case "stats":
      const db = new Database(DB_PATH);
      const stats = db.query(`
        SELECT
          namespace,
          COUNT(*) as count,
          AVG(confidence) as avg_confidence
        FROM evo_memory_semantic
        GROUP BY namespace
        ORDER BY count DESC
      `).all();
      console.table(stats);
      db.close();
      break;

    default:
      console.error(`Unknown command: ${command}`);
      process.exit(1);
  }
}

export { processMessage, detectImportance, extractKnowledge, saveToSemanticMemory };
