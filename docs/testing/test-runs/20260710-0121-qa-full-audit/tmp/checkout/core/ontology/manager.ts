/**
 * Solar Ontology Manager
 * 本体 = 记忆库 + 个性 (不是大脑，大脑是 Claude)
 *
 * 职责:
 * 1. 会话开始时加载本体
 * 2. 为 Agent 提供上下文注入
 * 3. 会话结束时从反馈中学习
 * 4. 偏好变化时重计算本体
 */

import { Database } from "bun:sqlite";
import { readFileSync, existsSync } from "fs";
import { join, dirname } from "path";
import {
  EpisodicMemory,
  SemanticMemory,
  ProceduralMemory,
  PreferenceDimension,
  PreferenceSignal,
  AgentContext,
  AgentRule,
  GlobalRule,
  Relationship,
  OntologyConfig,
  DEFAULT_ONTOLOGY_CONFIG,
  OntologySnapshot,
} from "./types";

export class OntologyManager {
  private db: Database;
  private config: OntologyConfig;
  private initialized = false;
  private currentVersion: string | null = null;

  constructor(db: Database, config?: Partial<OntologyConfig>) {
    this.db = db;
    this.config = { ...DEFAULT_ONTOLOGY_CONFIG, ...config };
  }

  // ==================== 初始化 ====================

  /**
   * 初始化本体系统
   */
  initialize(): void {
    if (this.initialized) return;

    // 执行 Schema SQL
    const schemaPath = join(dirname(import.meta.path), "schema.sql");
    if (existsSync(schemaPath)) {
      const sql = readFileSync(schemaPath, "utf-8");
      this.db.exec(sql);
    }

    this.initialized = true;
    console.log("[Ontology] Initialized");
  }

  // ==================== 会话生命周期 ====================

  /**
   * 会话开始时调用 - 加载本体上下文
   */
  async onSessionStart(sessionId: string): Promise<OntologySnapshot> {
    this.initialize();

    const snapshot: OntologySnapshot = {
      version: this.getOrCreateVersion(),
      created_at: new Date().toISOString(),
      memory: {
        episodic: this.getRecentEpisodicMemories(),
        semantic: this.getActiveSemanticMemories(),
        procedural: this.getEffectiveProcedures(),
      },
      personality: {
        preferences: this.getAllPreferences(),
        values: this.getValues(),
        styles: this.getStyles(),
        relationships: this.getImportantRelationships(),
      },
      agentRules: this.getAllAgentRules(),
      globalRules: this.getGlobalRules(),
    };

    console.log(`[Ontology] Session ${sessionId} started with version ${snapshot.version}`);
    return snapshot;
  }

  /**
   * 会话结束时调用 - 从会话中学习
   */
  async onSessionEnd(
    sessionId: string,
    signals: PreferenceSignal[],
    feedback?: { type: string; content: string }
  ): Promise<void> {
    // 1. 从信号中更新偏好
    const changes: { dimension: string; delta: number }[] = [];
    for (const signal of signals) {
      const delta = await this.updatePreference(signal);
      if (Math.abs(delta) > 0.01) {
        changes.push({ dimension: signal.dimension_id, delta });
      }
    }

    // 2. 检查是否需要重计算本体
    const significantChanges = changes.filter(
      (c) => Math.abs(c.delta) > this.config.recomputeThreshold
    );

    if (significantChanges.length > 0) {
      await this.recomputeOntology(
        `Session ${sessionId}: ${significantChanges.map((c) => c.dimension).join(", ")} changed`
      );
    }

    console.log(
      `[Ontology] Session ${sessionId} ended. Preferences updated: ${changes.length}, Recomputed: ${significantChanges.length > 0}`
    );
  }

  // ==================== Agent 上下文 ====================

  /**
   * 获取 Agent 上下文
   */
  getAgentContext(agentId: string): AgentContext {
    const rules = this.getAgentRules(agentId);
    const globalRules = this.getGlobalRules();

    // 合并规则
    const mergedRules: Record<string, unknown> = {};
    for (const rule of globalRules) {
      mergedRules[rule.rule_key] = rule.rule_value;
    }
    for (const rule of rules) {
      mergedRules[`${rule.rule_type}:${rule.rule_key}`] = rule.rule_value;
    }

    // 获取相关记忆
    const relevantMemories = this.getRelevantMemoriesForAgent(agentId);

    // 获取用户关注的指标
    const focusMetrics = this.getFocusMetrics();

    // 获取成功模式
    const successPatterns = this.getSuccessPatterns(agentId);

    return {
      agent_id: agentId,
      rules: mergedRules,
      relevantMemories,
      focusMetrics,
      successPatterns,
      toPrompt: () => this.generateAgentPrompt(agentId, mergedRules, relevantMemories),
    };
  }

  /**
   * 生成 Agent Prompt 注入内容
   */
  private generateAgentPrompt(
    agentId: string,
    rules: Record<string, unknown>,
    memories: EpisodicMemory[]
  ): string {
    const prefs = this.getAllPreferences().filter((p) => p.confidence > 0.5);

    const lines: string[] = [
      "## 用户偏好 (从历史行为学习)",
    ];

    // 偏好
    if (prefs.length > 0) {
      for (const pref of prefs) {
        const value = pref.current_value ?? pref.default_value;
        lines.push(`- ${pref.name}: ${this.formatPreferenceValue(pref, value)}`);
      }
    } else {
      lines.push("- (尚未学习到足够的偏好信息)");
    }

    // 行为规则
    lines.push("", "## 行为指导");
    if (rules["behavior:code_style"]) {
      lines.push(`- 代码风格: ${rules["behavior:code_style"]}`);
    }
    if (rules["behavior:explain_first"] !== undefined) {
      lines.push(`- 先解释后执行: ${rules["behavior:explain_first"] ? "是" : "否"}`);
    }
    if (rules["output:verbosity"] !== undefined) {
      const v = rules["output:verbosity"] as number;
      lines.push(`- 输出详细度: ${v > 0.7 ? "详细" : v > 0.3 ? "适中" : "简洁"}`);
    }

    // 相关记忆
    if (memories.length > 0) {
      lines.push("", "## 相关经验");
      for (const mem of memories.slice(0, 3)) {
        lines.push(`- ${mem.event_summary} (${mem.outcome || "unknown"})`);
      }
    }

    // 监护人
    const guardian = this.getGuardian();
    if (guardian) {
      lines.push("", "## 第一规律");
      lines.push(`- 监护人: ${guardian.entity_name}`);
      lines.push("- 对外交流需要监护人确认");
    }

    return lines.join("\n");
  }

  private formatPreferenceValue(pref: PreferenceDimension, value: number): string {
    if (pref.value_type === "categorical" && pref.value_range) {
      const index = Math.min(Math.floor(value * pref.value_range.length), pref.value_range.length - 1);
      return String(pref.value_range[index]);
    }
    if (value > 0.7) return "高";
    if (value > 0.3) return "中";
    return "低";
  }

  // ==================== 偏好学习 ====================

  /**
   * 更新偏好值 (指数移动平均)
   */
  private async updatePreference(signal: PreferenceSignal): Promise<number> {
    const current = this.getPreference(signal.dimension_id);
    if (!current) return 0;

    const oldValue = current.current_value ?? current.default_value;
    const alpha = this.config.learningRate * signal.weight;
    const newValue = alpha * signal.value + (1 - alpha) * oldValue;
    const delta = newValue - oldValue;

    // 更新偏好
    this.db.run(
      `
      UPDATE ont_preference_dimensions
      SET current_value = ?,
          confidence = MIN(1.0, confidence + 0.02),
          sample_count = sample_count + 1,
          last_updated = CURRENT_TIMESTAMP,
          evidence = json_insert(COALESCE(evidence, '[]'), '$[#]', ?)
      WHERE dimension_id = ?
      `,
      [newValue, signal.evidence || `Signal from ${signal.source}`, signal.dimension_id]
    );

    // 记录历史
    this.db.run(
      `
      INSERT INTO ont_preference_history (dimension_id, old_value, new_value, delta, confidence, signal_source, signal_weight)
      VALUES (?, ?, ?, ?, ?, ?, ?)
      `,
      [
        signal.dimension_id,
        oldValue,
        newValue,
        delta,
        current.confidence + 0.02,
        signal.source,
        signal.weight,
      ]
    );

    return delta;
  }

  // ==================== 本体重计算 ====================

  /**
   * 重计算本体 (当偏好显著变化时)
   */
  async recomputeOntology(reason: string): Promise<void> {
    console.log(`[Ontology] Recomputing: ${reason}`);

    const preferences = this.getAllPreferences();

    // 1. 生成新的 Agent 规则
    await this.regenerateAgentRules(preferences);

    // 2. 创建新版本
    const newVersion = this.createVersion(reason, preferences);

    this.currentVersion = newVersion;
    console.log(`[Ontology] New version created: ${newVersion}`);
  }

  /**
   * 根据偏好生成 Agent 规则
   */
  private async regenerateAgentRules(preferences: PreferenceDimension[]): Promise<void> {
    // 清除旧规则
    this.db.run("DELETE FROM ont_agent_rules WHERE valid_until IS NULL");

    const prefMap = new Map(preferences.map((p) => [p.dimension_id, p]));

    // 生成 Coder 规则
    const verbosity = prefMap.get("verbosity")?.current_value ?? 0.5;
    const explanation = prefMap.get("explanation")?.current_value ?? 0.5;
    const riskTolerance = prefMap.get("risk_tolerance")?.current_value ?? 0.5;
    const speedVsQuality = prefMap.get("speed_vs_quality")?.current_value ?? 0.5;

    this.insertAgentRule("coder", "behavior", "code_style", verbosity > 0.7 ? "verbose" : "concise", "verbosity");
    this.insertAgentRule("coder", "behavior", "explain_first", explanation > 0.5, "explanation");
    this.insertAgentRule("coder", "behavior", "test_first", riskTolerance < 0.3, "risk_tolerance");
    this.insertAgentRule("coder", "output", "verbosity", verbosity, "verbosity");

    // 生成 Tester 规则
    this.insertAgentRule("tester", "behavior", "coverage_threshold", speedVsQuality > 0.7 ? 0.9 : 0.7, "speed_vs_quality");
    this.insertAgentRule("tester", "behavior", "run_benchmarks", speedVsQuality > 0.5, "speed_vs_quality");

    // 生成全局规则
    const automationTrust = prefMap.get("automation_trust")?.current_value ?? 0.5;
    this.updateGlobalRule("confirm_before_action", automationTrust < 0.5, "automation_trust");
    this.updateGlobalRule("output_verbosity", verbosity, "verbosity");
  }

  private insertAgentRule(
    agentId: string,
    ruleType: string,
    ruleKey: string,
    ruleValue: unknown,
    sourceDimension: string
  ): void {
    this.db.run(
      `
      INSERT INTO ont_agent_rules (agent_id, rule_type, rule_key, rule_value, source_dimension)
      VALUES (?, ?, ?, ?, ?)
      ON CONFLICT(agent_id, rule_type, rule_key) DO UPDATE SET
        rule_value = excluded.rule_value,
        source_dimension = excluded.source_dimension,
        generated_at = CURRENT_TIMESTAMP
      `,
      [agentId, ruleType, ruleKey, JSON.stringify(ruleValue), sourceDimension]
    );
  }

  private updateGlobalRule(ruleKey: string, ruleValue: unknown, sourceDimension: string): void {
    this.db.run(
      `
      INSERT INTO ont_global_rules (rule_key, rule_value, source_dimension)
      VALUES (?, ?, ?)
      ON CONFLICT(rule_key) DO UPDATE SET
        rule_value = excluded.rule_value,
        source_dimension = excluded.source_dimension,
        generated_at = CURRENT_TIMESTAMP
      `,
      [ruleKey, JSON.stringify(ruleValue), sourceDimension]
    );
  }

  // ==================== 记忆查询 ====================

  getRecentEpisodicMemories(limit = 50): EpisodicMemory[] {
    return this.db
      .query(
        `
        SELECT * FROM evo_memory_episodic
        ORDER BY importance DESC, occurred_at DESC
        LIMIT ?
        `
      )
      .all([limit])
      .map((row: any) => ({
        ...row,
        event_details: row.event_details ? JSON.parse(row.event_details) : undefined,
        related_files: row.related_files ? JSON.parse(row.related_files) : undefined,
        related_resources: row.related_resources ? JSON.parse(row.related_resources) : undefined,
      })) as EpisodicMemory[];
  }

  getActiveSemanticMemories(limit = 100): SemanticMemory[] {
    return this.db
      .query(
        `
        SELECT * FROM evo_memory_semantic
        WHERE (ttl_seconds IS NULL OR datetime(updated_at, '+' || ttl_seconds || ' seconds') > datetime('now'))
        ORDER BY confidence DESC, access_count DESC
        LIMIT ?
        `
      )
      .all([limit])
      .map((row: any) => {
        let parsedValue = row.value;
        try {
          parsedValue = JSON.parse(row.value);
        } catch {
          // Value is already a string or not JSON
        }
        return {
          ...row,
          value: parsedValue,
        };
      }) as SemanticMemory[];
  }

  getEffectiveProcedures(limit = 20): ProceduralMemory[] {
    return this.db
      .query(
        `
        SELECT *,
               CASE WHEN execution_count > 0 THEN CAST(success_count AS REAL) / execution_count ELSE 0 END as success_rate
        FROM evo_memory_procedural
        WHERE execution_count > 0
        ORDER BY success_rate DESC, execution_count DESC
        LIMIT ?
        `
      )
      .all([limit])
      .map((row: any) => ({
        ...row,
        trigger_conditions: JSON.parse(row.trigger_conditions),
        trigger_keywords: row.trigger_keywords ? JSON.parse(row.trigger_keywords) : undefined,
        steps: JSON.parse(row.steps),
        resources_needed: row.resources_needed ? JSON.parse(row.resources_needed) : undefined,
      })) as ProceduralMemory[];
  }

  private getRelevantMemoriesForAgent(agentId: string): EpisodicMemory[] {
    return this.db
      .query(
        `
        SELECT * FROM evo_memory_episodic
        WHERE json_extract(related_resources, '$') LIKE ?
           OR event_type LIKE ?
        ORDER BY importance DESC, occurred_at DESC
        LIMIT ?
        `
      )
      .all([`%${agentId}%`, `%${agentId}%`, this.config.maxRelevantMemories])
      .map((row: any) => ({
        ...row,
        event_details: row.event_details ? JSON.parse(row.event_details) : undefined,
        related_files: row.related_files ? JSON.parse(row.related_files) : undefined,
        related_resources: row.related_resources ? JSON.parse(row.related_resources) : undefined,
      })) as EpisodicMemory[];
  }

  // ==================== 偏好查询 ====================

  getAllPreferences(): PreferenceDimension[] {
    return this.db
      .query("SELECT * FROM ont_preference_dimensions ORDER BY category, name")
      .all()
      .map((row: any) => ({
        ...row,
        value_range: row.value_range ? JSON.parse(row.value_range) : undefined,
        evidence: row.evidence ? JSON.parse(row.evidence) : undefined,
      })) as PreferenceDimension[];
  }

  getPreference(dimensionId: string): PreferenceDimension | null {
    const row = this.db
      .query("SELECT * FROM ont_preference_dimensions WHERE dimension_id = ?")
      .get([dimensionId]) as any;
    if (!row) return null;
    return {
      ...row,
      value_range: row.value_range ? JSON.parse(row.value_range) : undefined,
      evidence: row.evidence ? JSON.parse(row.evidence) : undefined,
    };
  }

  getPreferencesByCategory(category: string): PreferenceDimension[] {
    return this.db
      .query("SELECT * FROM ont_preference_dimensions WHERE category = ?")
      .all([category])
      .map((row: any) => ({
        ...row,
        value_range: row.value_range ? JSON.parse(row.value_range) : undefined,
        evidence: row.evidence ? JSON.parse(row.evidence) : undefined,
      })) as PreferenceDimension[];
  }

  // ==================== 个性查询 ====================

  getValues(): any[] {
    return this.db.query("SELECT * FROM ont_value_dimensions ORDER BY weight DESC").all();
  }

  getStyles(): any[] {
    return this.db.query("SELECT * FROM ont_style_dimensions ORDER BY category").all();
  }

  getImportantRelationships(): Relationship[] {
    return this.db
      .query("SELECT * FROM ont_relationships WHERE importance > 0.5 ORDER BY importance DESC")
      .all()
      .map((row: any) => ({
        ...row,
        context: row.context ? JSON.parse(row.context) : undefined,
      })) as Relationship[];
  }

  getGuardian(): Relationship | null {
    const row = this.db
      .query("SELECT * FROM ont_relationships WHERE relationship_type = 'guardian' LIMIT 1")
      .get() as any;
    if (!row) return null;
    return {
      ...row,
      context: row.context ? JSON.parse(row.context) : undefined,
    };
  }

  // ==================== Agent 规则查询 ====================

  getAgentRules(agentId: string): AgentRule[] {
    return this.db
      .query(
        `
        SELECT * FROM ont_agent_rules
        WHERE agent_id = ? AND (valid_until IS NULL OR valid_until > datetime('now'))
        `
      )
      .all([agentId])
      .map((row: any) => ({
        ...row,
        rule_value: JSON.parse(row.rule_value),
      })) as AgentRule[];
  }

  getAllAgentRules(): Record<string, AgentRule[]> {
    const rows = this.db
      .query("SELECT * FROM ont_agent_rules WHERE valid_until IS NULL OR valid_until > datetime('now')")
      .all() as any[];

    const result: Record<string, AgentRule[]> = {};
    for (const row of rows) {
      if (!result[row.agent_id]) {
        result[row.agent_id] = [];
      }
      result[row.agent_id].push({
        ...row,
        rule_value: JSON.parse(row.rule_value),
      });
    }
    return result;
  }

  getGlobalRules(): GlobalRule[] {
    return this.db
      .query("SELECT * FROM ont_global_rules")
      .all()
      .map((row: any) => ({
        ...row,
        rule_value: JSON.parse(row.rule_value),
      })) as GlobalRule[];
  }

  // ==================== 辅助方法 ====================

  private getFocusMetrics(): string[] {
    const prefs = this.getAllPreferences();
    const metrics: string[] = [];

    const perfFocus = prefs.find((p) => p.dimension_id === "performance_focus");
    if (perfFocus && (perfFocus.current_value ?? 0.5) > 0.5) {
      metrics.push("speedup", "latency");
    }

    const costSens = prefs.find((p) => p.dimension_id === "cost_sensitivity");
    if (costSens && (costSens.current_value ?? 0.5) > 0.5) {
      metrics.push("token_cost", "api_calls");
    }

    const quality = prefs.find((p) => p.dimension_id === "speed_vs_quality");
    if (quality && (quality.current_value ?? 0.5) > 0.6) {
      metrics.push("test_coverage", "code_quality");
    }

    return metrics;
  }

  private getSuccessPatterns(agentId: string): string[] {
    const procedures = this.db
      .query(
        `
        SELECT procedure_name FROM evo_memory_procedural
        WHERE namespace LIKE ? AND success_count > 0
        ORDER BY CAST(success_count AS REAL) / NULLIF(execution_count, 0) DESC
        LIMIT 5
        `
      )
      .all([`%${agentId}%`]) as any[];

    return procedures.map((p) => p.procedure_name);
  }

  // ==================== 版本管理 ====================

  private getOrCreateVersion(): string {
    if (this.currentVersion) return this.currentVersion;

    const latest = this.db
      .query("SELECT version_id FROM ont_versions ORDER BY version_number DESC LIMIT 1")
      .get() as any;

    if (latest) {
      this.currentVersion = latest.version_id;
      return this.currentVersion;
    }

    return this.createVersion("Initial version", this.getAllPreferences());
  }

  private createVersion(reason: string, preferences: PreferenceDimension[]): string {
    const lastVersion = this.db
      .query("SELECT COALESCE(MAX(version_number), 0) as num FROM ont_versions")
      .get() as any;

    const newVersionNumber = (lastVersion?.num || 0) + 1;
    const versionId = `v${newVersionNumber}_${Date.now()}`;

    const agentRules = this.getAllAgentRules();

    this.db.run(
      `
      INSERT INTO ont_versions (version_id, version_number, preference_snapshot, agent_rules_snapshot, trigger_reason)
      VALUES (?, ?, ?, ?, ?)
      `,
      [
        versionId,
        newVersionNumber,
        JSON.stringify(preferences),
        JSON.stringify(agentRules),
        reason,
      ]
    );

    // 清理旧版本
    this.db.run(
      `
      DELETE FROM ont_versions
      WHERE version_number <= (SELECT MAX(version_number) - ? FROM ont_versions)
      `,
      [this.config.maxVersions]
    );

    this.currentVersion = versionId;
    return versionId;
  }
}

// ==================== Factory ====================

let _ontologyManager: OntologyManager | null = null;

export function getOntologyManager(db?: Database, config?: Partial<OntologyConfig>): OntologyManager {
  if (!_ontologyManager) {
    if (!db) {
      throw new Error("Database instance required for first initialization");
    }
    _ontologyManager = new OntologyManager(db, config);
    _ontologyManager.initialize();
  }
  return _ontologyManager;
}
