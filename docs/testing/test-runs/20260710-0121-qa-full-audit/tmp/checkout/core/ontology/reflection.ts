/**
 * Solar Ontology Reflection System
 * 反思 → 归纳 → 沉淀到本体
 *
 * 核心职责:
 * 1. 定期反思会话中学到的东西
 * 2. 归纳总结记忆和技能
 * 3. 沉淀到本体的语义记忆中
 * 4. 验证工作时是否使用了本体
 */

import { Database } from "bun:sqlite";
import { getOntologyTimeline } from "./timeline";

export interface ReflectionResult {
  reflection_id: string;
  reflection_type: "session" | "daily" | "weekly" | "milestone";
  timestamp: string;

  // 反思内容
  learnings: Learning[];           // 学到的东西
  patterns: Pattern[];             // 发现的模式
  improvements: Improvement[];     // 可以改进的地方

  // 沉淀结果
  memories_created: number;        // 创建的记忆数
  preferences_updated: number;     // 更新的偏好数
  procedures_added: number;        // 添加的程序数
}

export interface Learning {
  category: "knowledge" | "skill" | "preference" | "pattern";
  content: string;
  confidence: number;
  source: string;
  evidence: string[];
}

export interface Pattern {
  pattern_type: "success" | "failure" | "efficiency" | "communication";
  description: string;
  frequency: number;
  actionable: boolean;
  suggested_action?: string;
}

export interface Improvement {
  area: "code" | "communication" | "efficiency" | "reliability";
  current_state: string;
  target_state: string;
  priority: "high" | "medium" | "low";
}

export class OntologyReflector {
  private db: Database;

  constructor(db: Database) {
    this.db = db;
  }

  // ==================== 反思触发 ====================

  /**
   * 会话结束时的反思
   */
  async reflectOnSession(sessionId: string): Promise<ReflectionResult> {
    console.log(`[Reflection] 开始会话反思: ${sessionId}`);

    // 1. 获取会话数据
    const sessionData = await this.getSessionData(sessionId);

    // 2. 分析学到的东西
    const learnings = this.analyzeLearnings(sessionData);

    // 3. 发现模式
    const patterns = this.discoverPatterns(sessionData);

    // 4. 识别改进点
    const improvements = this.identifyImprovements(sessionData);

    // 5. 沉淀到本体
    const result = await this.consolidateToOntology(
      "session",
      learnings,
      patterns,
      improvements,
      sessionId
    );

    console.log(`[Reflection] 会话反思完成: 学习${learnings.length}项, 模式${patterns.length}个, 改进${improvements.length}点`);

    return result;
  }

  /**
   * 每日反思 (定时任务调用)
   */
  async dailyReflection(): Promise<ReflectionResult> {
    console.log("[Reflection] 开始每日反思");

    // 1. 获取今天所有会话数据
    const todaySessions = await this.getTodaySessions();

    // 2. 汇总学习
    const allLearnings: Learning[] = [];
    for (const session of todaySessions) {
      const sessionData = await this.getSessionData(session.session_id);
      allLearnings.push(...this.analyzeLearnings(sessionData));
    }

    // 3. 跨会话模式分析
    const patterns = this.analyzeCrossSessionPatterns(todaySessions);

    // 4. 识别改进
    const improvements = this.identifyDailyImprovements(todaySessions);

    // 5. 归纳去重
    const consolidatedLearnings = this.consolidateLearnings(allLearnings);

    // 6. 沉淀到本体
    const result = await this.consolidateToOntology(
      "daily",
      consolidatedLearnings,
      patterns,
      improvements
    );

    console.log(`[Reflection] 每日反思完成`);

    return result;
  }

  /**
   * 每周反思 (深度分析)
   */
  async weeklyReflection(): Promise<ReflectionResult> {
    console.log("[Reflection] 开始每周反思");

    // 1. 获取本周数据
    const weekData = await this.getWeekData();

    // 2. 深度分析偏好演进
    const preferenceEvolution = await this.analyzePreferenceEvolution();

    // 3. 技能成长分析
    const skillGrowth = await this.analyzeSkillGrowth();

    // 4. 生成洞察
    const learnings = this.generateWeeklyInsights(weekData, preferenceEvolution, skillGrowth);

    // 5. 长期模式
    const patterns = this.discoverLongTermPatterns(weekData);

    // 6. 战略改进
    const improvements = this.identifyStrategicImprovements(weekData);

    // 7. 沉淀
    const result = await this.consolidateToOntology(
      "weekly",
      learnings,
      patterns,
      improvements
    );

    // 8. 创建里程碑快照
    const timeline = getOntologyTimeline(this.db);
    timeline.createSnapshot("milestone", "每周反思里程碑");

    console.log("[Reflection] 每周反思完成");

    return result;
  }

  // ==================== 沉淀到本体 ====================

  /**
   * 将反思结果沉淀到本体
   */
  private async consolidateToOntology(
    reflectionType: ReflectionResult["reflection_type"],
    learnings: Learning[],
    patterns: Pattern[],
    improvements: Improvement[],
    sessionId?: string
  ): Promise<ReflectionResult> {
    const reflectionId = `ref_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
    const timestamp = new Date().toISOString();

    let memoriesCreated = 0;
    let preferencesUpdated = 0;
    let proceduresAdded = 0;

    // 1. 学习沉淀到语义记忆
    for (const learning of learnings) {
      if (learning.confidence > 0.5) {
        await this.addSemanticMemory(learning);
        memoriesCreated++;
      }
    }

    // 2. 模式沉淀到程序记忆
    for (const pattern of patterns) {
      if (pattern.actionable && pattern.suggested_action) {
        await this.addProceduralMemory(pattern);
        proceduresAdded++;
      }
    }

    // 3. 改进触发偏好调整
    for (const improvement of improvements) {
      if (improvement.priority === "high") {
        const updated = await this.adjustPreferenceFromImprovement(improvement);
        if (updated) preferencesUpdated++;
      }
    }

    // 4. 记录反思事件
    await this.recordReflectionEvent(reflectionId, reflectionType, learnings, patterns, improvements, sessionId);

    // 5. 记录到时间线
    const timeline = getOntologyTimeline(this.db);
    timeline.recordLearningEvent(
      "reflection_completed",
      {
        reflection_id: reflectionId,
        type: reflectionType,
        learnings_count: learnings.length,
        patterns_count: patterns.length,
        improvements_count: improvements.length,
        memories_created: memoriesCreated,
        preferences_updated: preferencesUpdated,
        procedures_added: proceduresAdded,
      },
      undefined,
      undefined,
      "reflection",
      sessionId
    );

    return {
      reflection_id: reflectionId,
      reflection_type: reflectionType,
      timestamp,
      learnings,
      patterns,
      improvements,
      memories_created: memoriesCreated,
      preferences_updated: preferencesUpdated,
      procedures_added: proceduresAdded,
    };
  }

  // ==================== 记忆写入 ====================

  private async addSemanticMemory(learning: Learning): Promise<void> {
    const memoryId = `sem_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`;
    const namespace = `learning/${learning.category}`;

    this.db.run(
      `
      INSERT INTO evo_memory_semantic (memory_id, namespace, key, value, source_type, confidence)
      VALUES (?, ?, ?, ?, 'inferred', ?)
      ON CONFLICT(namespace, key) DO UPDATE SET
        value = excluded.value,
        confidence = MAX(confidence, excluded.confidence),
        updated_at = CURRENT_TIMESTAMP
      `,
      [
        memoryId,
        namespace,
        learning.content.slice(0, 100),
        JSON.stringify({
          content: learning.content,
          source: learning.source,
          evidence: learning.evidence,
          learned_at: new Date().toISOString(),
        }),
        learning.confidence,
      ]
    );

    // 记录到时间线
    const timeline = getOntologyTimeline(this.db);
    timeline.recordMemoryOperation("semantic", memoryId, "created", undefined, learning.confidence);
  }

  private async addProceduralMemory(pattern: Pattern): Promise<void> {
    const memoryId = `proc_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`;
    const namespace = `pattern/${pattern.pattern_type}`;

    this.db.run(
      `
      INSERT INTO evo_memory_procedural (
        memory_id, namespace, procedure_name, procedure_type, description,
        trigger_conditions, steps, execution_count, success_count
      )
      VALUES (?, ?, ?, 'pattern', ?, ?, ?, 0, 0)
      ON CONFLICT(namespace, procedure_name, version) DO UPDATE SET
        description = excluded.description,
        trigger_conditions = excluded.trigger_conditions,
        updated_at = CURRENT_TIMESTAMP
      `,
      [
        memoryId,
        namespace,
        pattern.description.slice(0, 50),
        pattern.description,
        JSON.stringify({ pattern_type: pattern.pattern_type, frequency: pattern.frequency }),
        JSON.stringify([pattern.suggested_action]),
      ]
    );

    // 记录到时间线
    const timeline = getOntologyTimeline(this.db);
    timeline.recordMemoryOperation("procedural", memoryId, "created");
  }

  private async adjustPreferenceFromImprovement(improvement: Improvement): Promise<boolean> {
    // 根据改进建议调整偏好
    const dimensionMap: Record<string, { dimension: string; direction: number }> = {
      code: { dimension: "speed_vs_quality", direction: 0.05 },
      communication: { dimension: "verbosity", direction: -0.05 },
      efficiency: { dimension: "automation_trust", direction: 0.05 },
      reliability: { dimension: "risk_tolerance", direction: -0.05 },
    };

    const mapping = dimensionMap[improvement.area];
    if (!mapping) return false;

    // 获取当前值
    const current = this.db
      .query("SELECT current_value, default_value FROM ont_preference_dimensions WHERE dimension_id = ?")
      .get([mapping.dimension]) as any;

    if (!current) return false;

    const currentValue = current.current_value ?? current.default_value;
    const newValue = Math.max(0, Math.min(1, currentValue + mapping.direction));

    // 更新偏好
    this.db.run(
      `
      UPDATE ont_preference_dimensions
      SET current_value = ?, confidence = MIN(1.0, confidence + 0.01), last_updated = CURRENT_TIMESTAMP
      WHERE dimension_id = ?
      `,
      [newValue, mapping.dimension]
    );

    // 记录变更
    const timeline = getOntologyTimeline(this.db);
    timeline.recordPreferenceChange(
      mapping.dimension,
      newValue,
      0,
      0,
      mapping.direction,
      "reflection",
      `改进建议: ${improvement.current_state} → ${improvement.target_state}`
    );

    return true;
  }

  private async recordReflectionEvent(
    reflectionId: string,
    reflectionType: string,
    learnings: Learning[],
    patterns: Pattern[],
    improvements: Improvement[],
    sessionId?: string
  ): Promise<void> {
    this.db.run(
      `
      INSERT INTO sys_reflections (
        reflection_id, reflection_type, learnings, patterns, improvements, session_id, created_at
      )
      VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
      `,
      [
        reflectionId,
        reflectionType,
        JSON.stringify(learnings),
        JSON.stringify(patterns),
        JSON.stringify(improvements),
        sessionId || null,
      ]
    );
  }

  // ==================== 分析方法 (简化实现) ====================

  private async getSessionData(sessionId: string): Promise<any> {
    // 从数据库获取会话数据
    return {
      session_id: sessionId,
      messages: [],
      tool_calls: [],
      agent_interactions: [],
    };
  }

  private async getTodaySessions(): Promise<any[]> {
    return this.db
      .query(
        `
        SELECT DISTINCT session_id FROM evo_sessions
        WHERE created_at > datetime('now', '-1 day')
        `
      )
      .all() as any[];
  }

  private async getWeekData(): Promise<any> {
    return {};
  }

  private analyzeLearnings(sessionData: any): Learning[] {
    // 简化实现 - 实际应该分析会话内容
    return [];
  }

  private discoverPatterns(sessionData: any): Pattern[] {
    return [];
  }

  private identifyImprovements(sessionData: any): Improvement[] {
    return [];
  }

  private analyzeCrossSessionPatterns(sessions: any[]): Pattern[] {
    return [];
  }

  private identifyDailyImprovements(sessions: any[]): Improvement[] {
    return [];
  }

  private consolidateLearnings(learnings: Learning[]): Learning[] {
    // 去重和归纳
    const seen = new Set<string>();
    return learnings.filter((l) => {
      const key = `${l.category}:${l.content}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }

  private async analyzePreferenceEvolution(): Promise<any> {
    return {};
  }

  private async analyzeSkillGrowth(): Promise<any> {
    return {};
  }

  private generateWeeklyInsights(weekData: any, prefEvo: any, skillGrowth: any): Learning[] {
    return [];
  }

  private discoverLongTermPatterns(weekData: any): Pattern[] {
    return [];
  }

  private identifyStrategicImprovements(weekData: any): Improvement[] {
    return [];
  }
}

// ==================== 本体使用验证 ====================

export class OntologyUsageVerifier {
  private db: Database;
  private usageLog: { timestamp: Date; context: string; used: boolean }[] = [];

  constructor(db: Database) {
    this.db = db;
  }

  /**
   * 记录本体使用情况
   */
  recordUsage(context: string, used: boolean): void {
    this.usageLog.push({
      timestamp: new Date(),
      context,
      used,
    });

    // 如果没有使用本体，记录警告
    if (!used) {
      console.warn(`[Ontology] ⚠️ 未使用本体: ${context}`);
    }
  }

  /**
   * 检查本体使用率
   */
  getUsageRate(): { rate: number; used: number; total: number } {
    const total = this.usageLog.length;
    const used = this.usageLog.filter((l) => l.used).length;
    return {
      rate: total > 0 ? used / total : 0,
      used,
      total,
    };
  }

  /**
   * 获取未使用本体的场景
   */
  getUnusedContexts(): string[] {
    return this.usageLog.filter((l) => !l.used).map((l) => l.context);
  }

  /**
   * 验证当前思维路径是否使用了本体
   */
  verifyThinkingPath(): { valid: boolean; issues: string[] } {
    const issues: string[] = [];

    // 检查最近是否加载了本体
    const recentUsage = this.usageLog.slice(-5);
    const hasOntologyLoad = recentUsage.some(
      (l) => l.context.includes("load") || l.context.includes("context")
    );

    if (!hasOntologyLoad) {
      issues.push("最近操作未加载本体上下文");
    }

    // 检查使用率
    const { rate } = this.getUsageRate();
    if (rate < 0.5) {
      issues.push(`本体使用率过低: ${(rate * 100).toFixed(0)}%`);
    }

    return {
      valid: issues.length === 0,
      issues,
    };
  }
}

// ==================== Factory ====================

let _reflector: OntologyReflector | null = null;
let _verifier: OntologyUsageVerifier | null = null;

export function getOntologyReflector(db: Database): OntologyReflector {
  if (!_reflector) {
    _reflector = new OntologyReflector(db);
  }
  return _reflector;
}

export function getOntologyUsageVerifier(db: Database): OntologyUsageVerifier {
  if (!_verifier) {
    _verifier = new OntologyUsageVerifier(db);
  }
  return _verifier;
}
