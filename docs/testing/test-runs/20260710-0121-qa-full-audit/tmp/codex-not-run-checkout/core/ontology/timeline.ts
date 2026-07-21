/**
 * Solar Ontology Timeline Manager
 * 时间线记忆 - 记住演进过程，不只是当前状态
 */

import { Database } from "bun:sqlite";
import { PreferenceDimension } from "./types";

export interface OntologySnapshot {
  snapshot_id: string;
  version_number: number;
  snapshot_type: "auto" | "manual" | "milestone";
  preferences_state: PreferenceState[];
  relationships_state?: any[];
  agent_rules_state?: Record<string, any[]>;
  global_rules_state?: any[];
  trigger_reason: string;
  changes_summary?: string;
  session_id?: string;
  created_at: string;
  total_confidence: number;
  active_dimensions: number;
  learned_signals: number;
}

export interface PreferenceState {
  dimension_id: string;
  value: number;
  confidence: number;
  sample_count: number;
}

export interface PreferenceTimelineEntry {
  dimension_id: string;
  value_at_time: number;
  confidence_at_time: number;
  sample_count_at_time: number;
  delta?: number;
  signal_source?: string;
  signal_evidence?: string;
  recorded_at: string;
  session_id?: string;
}

export interface LearningEvent {
  event_id: string;
  event_type: string;
  details: any;
  affected_dimensions?: string[];
  affected_rules?: string[];
  source_type?: string;
  session_id?: string;
  occurred_at: string;
}

export class OntologyTimeline {
  private db: Database;

  constructor(db: Database) {
    this.db = db;
  }

  /**
   * 初始化时间线表
   */
  initialize(): void {
    const { readFileSync, existsSync } = require("fs");
    const { join, dirname } = require("path");

    const schemaPath = join(dirname(import.meta.path), "schema-v2.sql");
    if (existsSync(schemaPath)) {
      const sql = readFileSync(schemaPath, "utf-8");
      this.db.exec(sql);
    }
  }

  // ==================== 快照管理 ====================

  /**
   * 创建完整快照
   */
  createSnapshot(
    snapshotType: "auto" | "manual" | "milestone",
    triggerReason: string,
    sessionId?: string
  ): string {
    const snapshotId = `snap_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;

    // 获取当前状态
    const preferences = this.getCurrentPreferencesState();
    const relationships = this.getCurrentRelationshipsState();
    const agentRules = this.getCurrentAgentRulesState();
    const globalRules = this.getCurrentGlobalRulesState();

    // 计算指标
    const totalConfidence = preferences.reduce((sum, p) => sum + p.confidence, 0);
    const activeDimensions = preferences.filter((p) => p.confidence > 0).length;
    const learnedSignals = preferences.reduce((sum, p) => sum + p.sample_count, 0);

    // 获取下一个版本号
    const lastVersion = this.db
      .query("SELECT COALESCE(MAX(version_number), 0) as v FROM ont_snapshots")
      .get() as any;
    const versionNumber = (lastVersion?.v || 0) + 1;

    // 生成变更摘要
    const changesSummary = this.generateChangesSummary(versionNumber, preferences);

    this.db.run(
      `
      INSERT INTO ont_snapshots (
        snapshot_id, version_number, snapshot_type,
        preferences_state, relationships_state, agent_rules_state, global_rules_state,
        trigger_reason, changes_summary, session_id,
        total_confidence, active_dimensions, learned_signals
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
      `,
      [
        snapshotId,
        versionNumber,
        snapshotType,
        JSON.stringify(preferences),
        JSON.stringify(relationships),
        JSON.stringify(agentRules),
        JSON.stringify(globalRules),
        triggerReason,
        changesSummary,
        sessionId || null,
        totalConfidence,
        activeDimensions,
        learnedSignals,
      ]
    );

    // 记录学习事件
    this.recordLearningEvent("snapshot_created", {
      snapshot_id: snapshotId,
      version_number: versionNumber,
      type: snapshotType,
      reason: triggerReason,
    });

    return snapshotId;
  }

  /**
   * 获取特定版本的快照
   */
  getSnapshot(versionNumber: number): OntologySnapshot | null {
    const row = this.db
      .query("SELECT * FROM ont_snapshots WHERE version_number = ?")
      .get([versionNumber]) as any;

    if (!row) return null;

    return {
      ...row,
      preferences_state: JSON.parse(row.preferences_state),
      relationships_state: row.relationships_state ? JSON.parse(row.relationships_state) : undefined,
      agent_rules_state: row.agent_rules_state ? JSON.parse(row.agent_rules_state) : undefined,
      global_rules_state: row.global_rules_state ? JSON.parse(row.global_rules_state) : undefined,
    };
  }

  /**
   * 获取最新快照
   */
  getLatestSnapshot(): OntologySnapshot | null {
    const row = this.db
      .query("SELECT * FROM ont_snapshots ORDER BY version_number DESC LIMIT 1")
      .get() as any;

    if (!row) return null;

    return {
      ...row,
      preferences_state: JSON.parse(row.preferences_state),
      relationships_state: row.relationships_state ? JSON.parse(row.relationships_state) : undefined,
      agent_rules_state: row.agent_rules_state ? JSON.parse(row.agent_rules_state) : undefined,
      global_rules_state: row.global_rules_state ? JSON.parse(row.global_rules_state) : undefined,
    };
  }

  /**
   * 获取版本历史
   */
  getVersionHistory(limit = 10): OntologySnapshot[] {
    const rows = this.db
      .query("SELECT * FROM ont_snapshots ORDER BY version_number DESC LIMIT ?")
      .all([limit]) as any[];

    return rows.map((row) => ({
      ...row,
      preferences_state: JSON.parse(row.preferences_state),
      relationships_state: row.relationships_state ? JSON.parse(row.relationships_state) : undefined,
      agent_rules_state: row.agent_rules_state ? JSON.parse(row.agent_rules_state) : undefined,
      global_rules_state: row.global_rules_state ? JSON.parse(row.global_rules_state) : undefined,
    }));
  }

  /**
   * 回滚到指定版本
   */
  rollbackToVersion(versionNumber: number, reason: string): boolean {
    const snapshot = this.getSnapshot(versionNumber);
    if (!snapshot) return false;

    // 恢复偏好状态
    for (const pref of snapshot.preferences_state) {
      this.db.run(
        `
        UPDATE ont_preference_dimensions
        SET current_value = ?, confidence = ?, sample_count = ?, last_updated = CURRENT_TIMESTAMP
        WHERE dimension_id = ?
        `,
        [pref.value, pref.confidence, pref.sample_count, pref.dimension_id]
      );
    }

    // 创建回滚快照
    this.createSnapshot("manual", `回滚到 v${versionNumber}: ${reason}`);

    // 记录学习事件
    this.recordLearningEvent("rollback", {
      target_version: versionNumber,
      reason,
    });

    return true;
  }

  // ==================== 时间线记录 ====================

  /**
   * 记录偏好变更到时间线
   */
  recordPreferenceChange(
    dimensionId: string,
    newValue: number,
    newConfidence: number,
    sampleCount: number,
    delta: number,
    signalSource: string,
    signalEvidence?: string,
    sessionId?: string
  ): void {
    this.db.run(
      `
      INSERT INTO ont_preference_timeline (
        dimension_id, value_at_time, confidence_at_time, sample_count_at_time,
        delta, signal_source, signal_evidence, session_id
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
      `,
      [
        dimensionId,
        newValue,
        newConfidence,
        sampleCount,
        delta,
        signalSource,
        signalEvidence || null,
        sessionId || null,
      ]
    );
  }

  /**
   * 记录记忆操作到时间线
   */
  recordMemoryOperation(
    memoryType: "episodic" | "semantic" | "procedural",
    memoryId: string,
    operation: "created" | "updated" | "recalled" | "decayed" | "archived",
    importance?: number,
    confidence?: number,
    sessionId?: string,
    context?: string
  ): void {
    this.db.run(
      `
      INSERT INTO ont_memory_timeline (
        memory_type, memory_id, operation,
        importance_at_time, confidence_at_time, session_id, context
      ) VALUES (?, ?, ?, ?, ?, ?, ?)
      `,
      [memoryType, memoryId, operation, importance, confidence, sessionId, context]
    );
  }

  /**
   * 记录学习事件
   */
  recordLearningEvent(
    eventType: string,
    details: any,
    affectedDimensions?: string[],
    affectedRules?: string[],
    sourceType?: string,
    sessionId?: string
  ): string {
    const eventId = `evt_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;

    this.db.run(
      `
      INSERT INTO ont_learning_events (
        event_id, event_type, details,
        affected_dimensions, affected_rules, source_type, session_id
      ) VALUES (?, ?, ?, ?, ?, ?, ?)
      `,
      [
        eventId,
        eventType,
        JSON.stringify(details),
        affectedDimensions ? JSON.stringify(affectedDimensions) : null,
        affectedRules ? JSON.stringify(affectedRules) : null,
        sourceType,
        sessionId,
      ]
    );

    return eventId;
  }

  // ==================== 时间查询 ====================

  /**
   * 获取特定时间点的偏好状态
   */
  getPreferencesAtTime(timestamp: Date): PreferenceState[] {
    const rows = this.db
      .query(
        `
        SELECT dimension_id, value_at_time as value, confidence_at_time as confidence, sample_count_at_time as sample_count
        FROM ont_preference_timeline
        WHERE id IN (
          SELECT MAX(id)
          FROM ont_preference_timeline
          WHERE recorded_at <= ?
          GROUP BY dimension_id
        )
        `
      )
      .all([timestamp.toISOString()]) as any[];

    return rows;
  }

  /**
   * 获取偏好在时间范围内的演进
   */
  getPreferenceEvolution(
    dimensionId: string,
    startTime: Date,
    endTime: Date
  ): PreferenceTimelineEntry[] {
    const rows = this.db
      .query(
        `
        SELECT * FROM ont_preference_timeline
        WHERE dimension_id = ?
          AND recorded_at BETWEEN ? AND ?
        ORDER BY recorded_at ASC
        `
      )
      .all([dimensionId, startTime.toISOString(), endTime.toISOString()]) as any[];

    return rows;
  }

  /**
   * 获取最近 N 天的偏好趋势
   */
  getPreferenceTrend(dimensionId: string, days = 7): {
    date: string;
    avg_value: number;
    updates: number;
  }[] {
    const rows = this.db
      .query(
        `
        SELECT
          date(recorded_at) as date,
          AVG(value_at_time) as avg_value,
          COUNT(*) as updates
        FROM ont_preference_timeline
        WHERE dimension_id = ?
          AND recorded_at > datetime('now', '-' || ? || ' days')
        GROUP BY date(recorded_at)
        ORDER BY date ASC
        `
      )
      .all([dimensionId, days]) as any[];

    return rows;
  }

  /**
   * 比较两个时间点的偏好差异
   */
  comparePreferencesOverTime(
    time1: Date,
    time2: Date
  ): { dimension_id: string; value_at_time1: number; value_at_time2: number; change: number }[] {
    const state1 = this.getPreferencesAtTime(time1);
    const state2 = this.getPreferencesAtTime(time2);

    const map1 = new Map(state1.map((p) => [p.dimension_id, p.value]));
    const map2 = new Map(state2.map((p) => [p.dimension_id, p.value]));

    const result: any[] = [];
    for (const [dimId, value2] of map2) {
      const value1 = map1.get(dimId) ?? 0.5;
      result.push({
        dimension_id: dimId,
        value_at_time1: value1,
        value_at_time2: value2,
        change: value2 - value1,
      });
    }

    return result.sort((a, b) => Math.abs(b.change) - Math.abs(a.change));
  }

  /**
   * 获取最近的学习事件
   */
  getRecentLearningEvents(limit = 20): LearningEvent[] {
    const rows = this.db
      .query(
        `
        SELECT * FROM ont_learning_events
        ORDER BY occurred_at DESC
        LIMIT ?
        `
      )
      .all([limit]) as any[];

    return rows.map((row) => ({
      ...row,
      details: JSON.parse(row.details),
      affected_dimensions: row.affected_dimensions ? JSON.parse(row.affected_dimensions) : undefined,
      affected_rules: row.affected_rules ? JSON.parse(row.affected_rules) : undefined,
    }));
  }

  // ==================== 私有方法 ====================

  private getCurrentPreferencesState(): PreferenceState[] {
    return this.db
      .query(
        `
        SELECT dimension_id, COALESCE(current_value, default_value) as value, confidence, sample_count
        FROM ont_preference_dimensions
        `
      )
      .all() as any[];
  }

  private getCurrentRelationshipsState(): any[] {
    return this.db
      .query("SELECT * FROM ont_relationships")
      .all()
      .map((row: any) => ({
        ...row,
        context: row.context ? JSON.parse(row.context) : undefined,
      }));
  }

  private getCurrentAgentRulesState(): Record<string, any[]> {
    const rows = this.db.query("SELECT * FROM ont_agent_rules").all() as any[];
    const result: Record<string, any[]> = {};
    for (const row of rows) {
      if (!result[row.agent_id]) result[row.agent_id] = [];
      result[row.agent_id].push({
        ...row,
        rule_value: JSON.parse(row.rule_value),
      });
    }
    return result;
  }

  private getCurrentGlobalRulesState(): any[] {
    return this.db
      .query("SELECT * FROM ont_global_rules")
      .all()
      .map((row: any) => ({
        ...row,
        rule_value: JSON.parse(row.rule_value),
      }));
  }

  private generateChangesSummary(newVersion: number, currentPrefs: PreferenceState[]): string {
    if (newVersion <= 1) return "初始版本";

    const prevSnapshot = this.getSnapshot(newVersion - 1);
    if (!prevSnapshot) return "无法比较";

    const prevPrefs = new Map(prevSnapshot.preferences_state.map((p) => [p.dimension_id, p.value]));
    const changes: string[] = [];

    for (const pref of currentPrefs) {
      const prevValue = prevPrefs.get(pref.dimension_id) ?? 0.5;
      const delta = pref.value - prevValue;
      if (Math.abs(delta) > 0.05) {
        const direction = delta > 0 ? "↑" : "↓";
        changes.push(`${pref.dimension_id} ${direction}${Math.abs(delta).toFixed(2)}`);
      }
    }

    return changes.length > 0 ? changes.join(", ") : "微调";
  }
}

// ==================== Factory ====================

let _timeline: OntologyTimeline | null = null;

export function getOntologyTimeline(db: Database): OntologyTimeline {
  if (!_timeline) {
    _timeline = new OntologyTimeline(db);
    _timeline.initialize();
  }
  return _timeline;
}
