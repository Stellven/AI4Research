/**
 * Solar Ontology - Agent Integration
 * 确保 Agent 工作时使用本体
 */

import { Database } from "bun:sqlite";
import { getOntologyManager } from "./manager";
import { getOntologyUsageVerifier } from "./reflection";
import { getOntologyTimeline } from "./timeline";

export interface AgentOntologyContext {
  // 偏好
  preferences: {
    verbosity: number;
    speed_vs_quality: number;
    formality: number;
    detail_level: number;
    code_style: number;
    [key: string]: number;
  };

  // 相关记忆
  relevantMemories: {
    semantic: Array<{ key: string; value: any; confidence: number }>;
    procedural: Array<{ name: string; steps: string[]; success_rate: number }>;
  };

  // 用户关系
  relationships: Array<{
    entity: string;
    relation: string;
    strength: number;
  }>;

  // Agent 特定规则
  agentRules: Array<{
    rule_type: string;
    rule_value: any;
    priority: number;
  }>;
}

/**
 * 为 Agent 获取本体上下文
 */
export function getAgentOntologyContext(
  db: Database,
  agentId: string,
  taskContext?: string
): AgentOntologyContext {
  const manager = getOntologyManager(db);
  const verifier = getOntologyUsageVerifier(db);

  // 记录本体使用
  verifier.recordUsage(`agent:${agentId}:load_context`, true);

  // 获取偏好
  const prefRows = db
    .query(`
      SELECT dimension_id, COALESCE(current_value, default_value) as value
      FROM ont_preference_dimensions
    `)
    .all() as any[];

  const preferences: any = {};
  for (const row of prefRows) {
    preferences[row.dimension_id] = row.value;
  }

  // 获取相关语义记忆
  const semanticMemories = db
    .query(`
      SELECT key, value, confidence
      FROM evo_memory_semantic
      WHERE confidence > 0.3
      ORDER BY access_count DESC, confidence DESC
      LIMIT 10
    `)
    .all() as any[];

  // 获取相关程序记忆
  const proceduralMemories = db
    .query(`
      SELECT procedure_name as name, steps,
             CAST(success_count AS REAL) / NULLIF(execution_count, 0) as success_rate
      FROM evo_memory_procedural
      WHERE execution_count > 0
      ORDER BY success_count DESC
      LIMIT 5
    `)
    .all()
    .map((row: any) => ({
      name: row.name,
      steps: JSON.parse(row.steps || "[]"),
      success_rate: row.success_rate || 0,
    }));

  // 获取用户关系
  const relationships = db
    .query(`
      SELECT entity_name as entity, relationship_type as relation, importance as strength
      FROM ont_relationships
      WHERE importance > 0.3
      ORDER BY importance DESC
      LIMIT 10
    `)
    .all() as any[];

  // 获取 Agent 特定规则
  const agentRules = db
    .query(`
      SELECT rule_type, rule_key, rule_value
      FROM ont_agent_rules
      WHERE agent_id = ?
      ORDER BY generated_at DESC
    `)
    .all([agentId])
    .map((row: any) => ({
      rule_type: row.rule_type,
      rule_value: JSON.parse(row.rule_value),
      priority: 1, // Default priority
    }));

  return {
    preferences,
    relevantMemories: {
      semantic: semanticMemories.map((m: any) => {
        let parsedValue = m.value;
        try {
          parsedValue = JSON.parse(m.value);
        } catch {
          // Keep original value
        }
        return { key: m.key, value: parsedValue, confidence: m.confidence };
      }),
      procedural: proceduralMemories,
    },
    relationships,
    agentRules,
  };
}

/**
 * 根据本体偏好调整 Agent 行为
 */
export function applyOntologyPreferences(
  context: AgentOntologyContext
): {
  shouldBeVerbose: boolean;
  preferQuality: boolean;
  formalStyle: boolean;
  detailedExplanations: boolean;
} {
  const { preferences } = context;

  return {
    shouldBeVerbose: (preferences.verbosity ?? 0.5) > 0.6,
    preferQuality: (preferences.speed_vs_quality ?? 0.5) > 0.6,
    formalStyle: (preferences.formality ?? 0.5) > 0.6,
    detailedExplanations: (preferences.detail_level ?? 0.5) > 0.6,
  };
}

/**
 * 记录 Agent 任务完成，用于反馈学习
 */
export function recordAgentTaskCompletion(
  db: Database,
  agentId: string,
  taskDescription: string,
  success: boolean,
  feedback?: string
): void {
  const timeline = getOntologyTimeline(db);
  const verifier = getOntologyUsageVerifier(db);

  // 记录使用
  verifier.recordUsage(`agent:${agentId}:task_complete`, true);

  // 记录学习事件
  timeline.recordLearningEvent(
    "agent_task_completed",
    {
      agent_id: agentId,
      task: taskDescription,
      success,
      feedback,
    },
    undefined,
    undefined,
    "agent"
  );

  // 如果有反馈，可能调整偏好
  if (feedback) {
    const manager = getOntologyManager(db);

    // 简单的反馈信号处理
    if (feedback.includes("太长") || feedback.includes("简洁")) {
      manager.updatePreference("verbosity", -0.05, "explicit", feedback);
    }
    if (feedback.includes("太短") || feedback.includes("详细")) {
      manager.updatePreference("verbosity", 0.05, "explicit", feedback);
    }
    if (feedback.includes("快") || feedback.includes("效率")) {
      manager.updatePreference("speed_vs_quality", -0.05, "explicit", feedback);
    }
    if (feedback.includes("质量") || feedback.includes("仔细")) {
      manager.updatePreference("speed_vs_quality", 0.05, "explicit", feedback);
    }
  }
}

/**
 * 生成本体引导的 Agent 提示
 */
export function generateOntologyGuidedPrompt(
  context: AgentOntologyContext,
  agentId: string
): string {
  const behavior = applyOntologyPreferences(context);
  const lines: string[] = [];

  lines.push("【本体指导】");

  // 偏好指导
  if (behavior.shouldBeVerbose) {
    lines.push("- 用户偏好详细解释，请提供充分说明");
  } else {
    lines.push("- 用户偏好简洁输出，请言简意赅");
  }

  if (behavior.preferQuality) {
    lines.push("- 用户重视质量，请仔细检查");
  } else {
    lines.push("- 用户重视效率，请快速完成");
  }

  if (behavior.formalStyle) {
    lines.push("- 用户偏好正式风格");
  }

  // 相关规则
  if (context.agentRules.length > 0) {
    lines.push("\n【Agent 规则】");
    for (const rule of context.agentRules.slice(0, 3)) {
      lines.push(`- ${rule.rule_type}: ${JSON.stringify(rule.rule_value)}`);
    }
  }

  // 相关记忆
  if (context.relevantMemories.semantic.length > 0) {
    lines.push("\n【相关知识】");
    for (const mem of context.relevantMemories.semantic.slice(0, 3)) {
      lines.push(`- ${mem.key}`);
    }
  }

  return lines.join("\n");
}

/**
 * 验证 Agent 是否正确使用本体
 */
export function verifyAgentOntologyUsage(
  db: Database,
  agentId: string
): { valid: boolean; issues: string[] } {
  const verifier = getOntologyUsageVerifier(db);
  const baseResult = verifier.verifyThinkingPath();

  const issues = [...baseResult.issues];

  // 检查 Agent 特定的使用情况
  const usageRate = verifier.getUsageRate();
  if (usageRate.rate < 0.5) {
    issues.push(`Agent ${agentId} 本体使用率过低: ${(usageRate.rate * 100).toFixed(0)}%`);
  }

  return {
    valid: issues.length === 0,
    issues,
  };
}

// ==================== 导出便捷函数 ====================

let _db: Database | null = null;

function getDb(): Database {
  if (!_db) {
    _db = new Database(process.env.SOLAR_DB_PATH || `${process.env.HOME}/.solar/db/solar.db`);
  }
  return _db;
}

/**
 * 快速获取 Agent 上下文 (便捷函数)
 */
export function quickGetContext(agentId: string): AgentOntologyContext {
  return getAgentOntologyContext(getDb(), agentId);
}

/**
 * 快速记录任务完成 (便捷函数)
 */
export function quickRecordTask(
  agentId: string,
  task: string,
  success: boolean,
  feedback?: string
): void {
  recordAgentTaskCompletion(getDb(), agentId, task, success, feedback);
}

// ==================== CLI 测试 ====================

if (import.meta.main) {
  const db = new Database(process.env.SOLAR_DB_PATH || `${process.env.HOME}/.solar/db/solar.db`);

  const agentId = process.argv[2] || "coder";
  console.log(`\n获取 Agent "${agentId}" 的本体上下文...\n`);

  const context = getAgentOntologyContext(db, agentId);

  console.log("偏好:");
  console.table(
    Object.entries(context.preferences).map(([k, v]) => ({
      dimension: k,
      value: v.toFixed(2),
    }))
  );

  console.log("\n行为调整:");
  console.table(applyOntologyPreferences(context));

  console.log("\n生成的指导提示:");
  console.log(generateOntologyGuidedPrompt(context, agentId));

  console.log("\n验证本体使用:");
  console.table(verifyAgentOntologyUsage(db, agentId));

  db.close();
}
