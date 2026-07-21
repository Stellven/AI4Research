/**
 * Solar Metadata System - Manager API
 * 元数据管理器 - 资源注册、查询、统计、路由
 */

import { Database } from "bun:sqlite";
import { readFileSync, existsSync } from "fs";
import { join, dirname } from "path";

// ==================== Types ====================

export type ResourceType =
  | "agent"
  | "skill"
  | "hook"
  | "tool"
  | "model"
  | "mcp_server";
export type ResourceStatus =
  | "active"
  | "deprecated"
  | "disabled"
  | "experimental";
export type InvocationStatus = "success" | "failed" | "timeout" | "cancelled";
export type DependencyType = "requires" | "optional" | "conflicts" | "enhances";
export type Permission = "allow" | "deny" | "require_approval";
export type QuotaType = "tokens" | "cost" | "invocations" | "concurrent";
export type QuotaPeriod = "hourly" | "daily" | "weekly" | "monthly" | "total";
export type EvolutionType =
  | "parameter_tuning"
  | "model_switch"
  | "routing_update"
  | "quota_adjust";

export interface Resource {
  resource_id: string;
  resource_type: ResourceType;
  name: string;
  version: string;
  status: ResourceStatus;
  description?: string;
  config?: Record<string, any>;
  created_at: string;
  updated_at: string;
}

export interface Agent {
  agent_id: string;
  emoji?: string;
  role?: string;
  phases?: string[];
  tools?: string[];
  default_model: string;
  priority: number;
  max_concurrent: number;
  timeout_seconds: number;
  retry_policy?: { max_retries: number; backoff_ms: number };
}

export interface Skill {
  skill_id: string;
  user_invocable: boolean;
  command?: string;
  category?: string;
  linked_agent?: string;
  path?: string;
  args_schema?: Record<string, any>;
  examples?: string[];
}

export interface Model {
  model_id: string;
  provider: string;
  model_name: string;
  context_window?: number;
  max_output_tokens?: number;
  input_price_per_mtok?: number;
  output_price_per_mtok?: number;
  capabilities?: string[];
  rate_limit_rpm?: number;
  is_default: boolean;
}

export interface Invocation {
  resource_id: string;
  invocation_type: string;
  session_id?: string;
  task_id?: number;
  input_tokens?: number;
  output_tokens?: number;
  latency_ms?: number;
  status: InvocationStatus;
  error_message?: string;
  metadata?: Record<string, any>;
}

export interface RoutingRule {
  rule_name: string;
  priority: number;
  conditions: Record<string, any>;
  target: string;
  fallback?: string;
  enabled: boolean;
  description?: string;
}

export interface QuotaStatus {
  quota_name: string;
  resource_type?: string;
  resource_id?: string;
  quota_type: QuotaType;
  period: QuotaPeriod;
  limit_value: number;
  current_usage: number;
  usage_percent: number;
  status: "ok" | "warning" | "exceeded";
  remaining: number;
}

export interface ResourceHealth {
  resource_id: string;
  resource_type: ResourceType;
  name: string;
  status: ResourceStatus;
  health_status: "healthy" | "warning" | "critical" | "unused" | "disabled";
  invocations_24h: number;
  failure_rate_24h: number;
  avg_latency_24h: number;
}

export interface EvolutionCandidate {
  resource_id: string;
  resource_type: ResourceType;
  name: string;
  invocations_7d: number;
  success_rate: number;
  latency_variance: number;
  candidate_reason: string;
  suggested_evolution: { suggested_action: string };
}

// ==================== MetadataManager Class ====================

export class MetadataManager {
  private db: Database;
  private initialized = false;

  constructor(db: Database) {
    this.db = db;
  }

  /**
   * 初始化元数据系统 (创建表、视图、触发器、导入初始数据)
   */
  initialize(): void {
    if (this.initialized) return;

    const baseDir = dirname(import.meta.path);

    // 加载并执行 SQL 文件
    const sqlFiles = [
      "metadata-schema.sql",
      "metadata-views.sql",
      "metadata-triggers.sql",
      "metadata-seed.sql",
    ];

    for (const file of sqlFiles) {
      const path = join(baseDir, file);
      if (existsSync(path)) {
        const sql = readFileSync(path, "utf-8");
        this.db.exec(sql);
      }
    }

    this.initialized = true;
  }

  // ==================== Resource CRUD ====================

  /**
   * 注册资源
   */
  registerResource(
    resource: Partial<Resource> & { resource_type: ResourceType; name: string },
  ): string {
    const resourceId =
      resource.resource_id ||
      `${resource.resource_type}:${resource.name}:${resource.version || "1.0"}`;

    this.db.run(
      `
      INSERT INTO sys_resources (resource_id, resource_type, name, version, status, description, config)
      VALUES (?, ?, ?, ?, ?, ?, ?)
      ON CONFLICT(resource_id) DO UPDATE SET
        status = excluded.status,
        description = excluded.description,
        config = excluded.config,
        updated_at = CURRENT_TIMESTAMP
    `,
      [
        resourceId,
        resource.resource_type,
        resource.name,
        resource.version || "1.0",
        resource.status || "active",
        resource.description || null,
        resource.config ? JSON.stringify(resource.config) : null,
      ],
    );

    return resourceId;
  }

  /**
   * 获取资源
   */
  getResource(resourceId: string): Resource | null {
    const row = this.db
      .query("SELECT * FROM sys_resources WHERE resource_id = ?")
      .get([resourceId]) as any;
    if (!row) return null;
    return {
      ...row,
      config: row.config ? JSON.parse(row.config) : undefined,
    };
  }

  /**
   * 列出资源
   */
  listResources(filter?: {
    type?: ResourceType;
    status?: ResourceStatus;
    name?: string;
  }): Resource[] {
    let sql = "SELECT * FROM sys_resources WHERE 1=1";
    const params: any[] = [];

    if (filter?.type) {
      sql += " AND resource_type = ?";
      params.push(filter.type);
    }
    if (filter?.status) {
      sql += " AND status = ?";
      params.push(filter.status);
    }
    if (filter?.name) {
      sql += " AND name LIKE ?";
      params.push(`%${filter.name}%`);
    }

    sql += " ORDER BY resource_type, name";

    return this.db
      .query(sql)
      .all(params)
      .map((row: any) => ({
        ...row,
        config: row.config ? JSON.parse(row.config) : undefined,
      })) as Resource[];
  }

  /**
   * 更新资源状态
   */
  updateResourceStatus(resourceId: string, status: ResourceStatus): void {
    this.db.run(
      "UPDATE sys_resources SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE resource_id = ?",
      [status, resourceId],
    );
  }

  // ==================== Agent Operations ====================

  /**
   * 注册 Agent
   */
  registerAgent(agent: Partial<Agent> & { agent_id: string }): void {
    this.db.run(
      `
      INSERT INTO sys_agents (agent_id, emoji, role, phases, tools, default_model, priority, max_concurrent, timeout_seconds, retry_policy)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
      ON CONFLICT(agent_id) DO UPDATE SET
        emoji = excluded.emoji,
        role = excluded.role,
        phases = excluded.phases,
        tools = excluded.tools,
        default_model = excluded.default_model,
        priority = excluded.priority,
        max_concurrent = excluded.max_concurrent,
        timeout_seconds = excluded.timeout_seconds,
        retry_policy = excluded.retry_policy
    `,
      [
        agent.agent_id,
        agent.emoji || null,
        agent.role || null,
        agent.phases ? JSON.stringify(agent.phases) : null,
        agent.tools ? JSON.stringify(agent.tools) : null,
        agent.default_model || "sonnet",
        agent.priority || 50,
        agent.max_concurrent || 1,
        agent.timeout_seconds || 300,
        agent.retry_policy ? JSON.stringify(agent.retry_policy) : null,
      ],
    );
  }

  /**
   * 获取 Agent
   */
  getAgent(agentId: string): (Resource & Agent) | null {
    const row = this.db
      .query(
        `
      SELECT r.*, a.emoji, a.role, a.phases, a.tools, a.default_model, a.priority, a.max_concurrent, a.timeout_seconds, a.retry_policy
      FROM sys_resources r
      JOIN sys_agents a ON r.resource_id = a.agent_id
      WHERE r.resource_id = ?
    `,
      )
      .get([agentId]) as any;

    if (!row) return null;

    return {
      ...row,
      config: row.config ? JSON.parse(row.config) : undefined,
      phases: row.phases ? JSON.parse(row.phases) : undefined,
      tools: row.tools ? JSON.parse(row.tools) : undefined,
      retry_policy: row.retry_policy ? JSON.parse(row.retry_policy) : undefined,
    };
  }

  /**
   * 列出所有 Agent
   */
  listAgents(status?: ResourceStatus): (Resource & Agent)[] {
    let sql = `
      SELECT r.*, a.emoji, a.role, a.phases, a.tools, a.default_model, a.priority, a.max_concurrent, a.timeout_seconds, a.retry_policy
      FROM sys_resources r
      JOIN sys_agents a ON r.resource_id = a.agent_id
      WHERE 1=1
    `;
    const params: any[] = [];

    if (status) {
      sql += " AND r.status = ?";
      params.push(status);
    }

    sql += " ORDER BY a.priority DESC, r.name";

    return this.db
      .query(sql)
      .all(params)
      .map((row: any) => ({
        ...row,
        config: row.config ? JSON.parse(row.config) : undefined,
        phases: row.phases ? JSON.parse(row.phases) : undefined,
        tools: row.tools ? JSON.parse(row.tools) : undefined,
        retry_policy: row.retry_policy
          ? JSON.parse(row.retry_policy)
          : undefined,
      })) as (Resource & Agent)[];
  }

  /**
   * 获取阶段的 Agent 列表
   */
  getAgentsForPhase(
    phase: string,
  ): (Resource & Agent & { is_primary: boolean })[] {
    const rows = this.db
      .query(
        `
      SELECT r.*, a.*, pa.is_primary, pa.priority as phase_priority
      FROM sys_phase_agents pa
      JOIN sys_agents a ON pa.agent_id = a.agent_id
      JOIN sys_resources r ON a.agent_id = r.resource_id
      WHERE pa.phase = ? AND r.status = 'active'
      ORDER BY pa.priority DESC
    `,
      )
      .all([phase]) as any[];

    return rows.map((row) => ({
      ...row,
      config: row.config ? JSON.parse(row.config) : undefined,
      phases: row.phases ? JSON.parse(row.phases) : undefined,
      tools: row.tools ? JSON.parse(row.tools) : undefined,
      retry_policy: row.retry_policy ? JSON.parse(row.retry_policy) : undefined,
    }));
  }

  // ==================== Skill Operations ====================

  /**
   * 注册 Skill
   */
  registerSkill(skill: Partial<Skill> & { skill_id: string }): void {
    this.db.run(
      `
      INSERT INTO sys_skills (skill_id, user_invocable, command, category, linked_agent, path, args_schema, examples)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?)
      ON CONFLICT(skill_id) DO UPDATE SET
        user_invocable = excluded.user_invocable,
        command = excluded.command,
        category = excluded.category,
        linked_agent = excluded.linked_agent,
        path = excluded.path,
        args_schema = excluded.args_schema,
        examples = excluded.examples
    `,
      [
        skill.skill_id,
        skill.user_invocable ? 1 : 0,
        skill.command || null,
        skill.category || null,
        skill.linked_agent || null,
        skill.path || null,
        skill.args_schema ? JSON.stringify(skill.args_schema) : null,
        skill.examples ? JSON.stringify(skill.examples) : null,
      ],
    );
  }

  /**
   * 通过命令获取 Skill
   */
  getSkillByCommand(command: string): (Resource & Skill) | null {
    const row = this.db
      .query(
        `
      SELECT r.*, s.user_invocable, s.command, s.category, s.linked_agent, s.path, s.args_schema, s.examples
      FROM sys_resources r
      JOIN sys_skills s ON r.resource_id = s.skill_id
      WHERE s.command = ? AND r.status = 'active'
    `,
      )
      .get([command]) as any;

    if (!row) return null;

    return {
      ...row,
      user_invocable: !!row.user_invocable,
      config: row.config ? JSON.parse(row.config) : undefined,
      args_schema: row.args_schema ? JSON.parse(row.args_schema) : undefined,
      examples: row.examples ? JSON.parse(row.examples) : undefined,
    };
  }

  /**
   * 列出用户可调用的 Skills
   */
  listUserInvocableSkills(): (Resource & Skill)[] {
    const rows = this.db
      .query(
        `
      SELECT r.*, s.user_invocable, s.command, s.category, s.linked_agent, s.path
      FROM sys_resources r
      JOIN sys_skills s ON r.resource_id = s.skill_id
      WHERE s.user_invocable = 1 AND r.status = 'active'
      ORDER BY s.category, s.command
    `,
      )
      .all() as any[];

    return rows.map((row) => ({
      ...row,
      user_invocable: !!row.user_invocable,
      config: row.config ? JSON.parse(row.config) : undefined,
    }));
  }

  // ==================== Model Operations ====================

  /**
   * 获取默认模型
   */
  getDefaultModel(): (Resource & Model) | null {
    const row = this.db
      .query(
        `
      SELECT r.*, m.*
      FROM sys_resources r
      JOIN sys_models m ON r.resource_id = m.model_id
      WHERE m.is_default = 1 AND r.status = 'active'
      LIMIT 1
    `,
      )
      .get() as any;

    if (!row) return null;

    return {
      ...row,
      is_default: !!row.is_default,
      capabilities: row.capabilities ? JSON.parse(row.capabilities) : undefined,
    };
  }

  /**
   * 获取推荐模型 (基于配额状态)
   */
  getRecommendedModel(): { model_id: string; reason: string } | null {
    const row = this.db.query("SELECT * FROM v_recommended_model").get() as any;
    return row || null;
  }

  // ==================== Invocation Recording ====================

  /**
   * 记录调用
   */
  recordInvocation(invocation: Invocation): number {
    const result = this.db.run(
      `
      INSERT INTO sys_invocations (resource_id, invocation_type, session_id, task_id, input_tokens, output_tokens, latency_ms, status, error_message, metadata)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `,
      [
        invocation.resource_id,
        invocation.invocation_type,
        invocation.session_id || null,
        invocation.task_id || null,
        invocation.input_tokens || 0,
        invocation.output_tokens || 0,
        invocation.latency_ms || null,
        invocation.status,
        invocation.error_message || null,
        invocation.metadata ? JSON.stringify(invocation.metadata) : null,
      ],
    );
    return Number(result.lastInsertRowid);
  }

  // ==================== Statistics Queries ====================

  /**
   * 获取资源健康状态
   */
  getResourceHealth(): ResourceHealth[] {
    return this.db
      .query("SELECT * FROM v_resource_health")
      .all() as ResourceHealth[];
  }

  /**
   * 获取配额状态
   */
  getQuotaStatus(): QuotaStatus[] {
    return this.db.query("SELECT * FROM v_quota_status").all() as QuotaStatus[];
  }

  /**
   * 获取自演进候选
   */
  getEvolutionCandidates(): EvolutionCandidate[] {
    const rows = this.db
      .query("SELECT * FROM v_evolution_candidates")
      .all() as any[];
    return rows.map((row) => ({
      ...row,
      suggested_evolution: row.suggested_evolution
        ? JSON.parse(row.suggested_evolution)
        : undefined,
    }));
  }

  /**
   * 获取低效资源
   */
  getUnderutilizedResources(): Resource[] {
    return this.db
      .query("SELECT * FROM v_underutilized_resources")
      .all() as Resource[];
  }

  /**
   * 获取高成本资源
   */
  getHighCostResources(): any[] {
    return this.db.query("SELECT * FROM v_high_cost_resources").all();
  }

  /**
   * 获取阶段瓶颈
   */
  getPhaseBottlenecks(): any[] {
    return this.db.query("SELECT * FROM v_phase_bottlenecks").all();
  }

  // ==================== Routing ====================

  /**
   * 获取推荐的 Agent (基于条件)
   */
  getRecommendedAgent(conditions: Record<string, any>): string | null {
    const rules = this.db
      .query(
        `
      SELECT * FROM sys_routing_agent
      WHERE enabled = 1
      ORDER BY priority DESC
    `,
      )
      .all() as any[];

    for (const rule of rules) {
      const ruleConditions = JSON.parse(rule.conditions);
      if (this.matchConditions(ruleConditions, conditions)) {
        return rule.target_agent;
      }
    }

    return null;
  }

  /**
   * 获取推荐的 Tool (基于条件)
   */
  getRecommendedTool(conditions: Record<string, any>): string | null {
    const rules = this.db
      .query(
        `
      SELECT * FROM sys_routing_tool
      WHERE enabled = 1
      ORDER BY priority DESC
    `,
      )
      .all() as any[];

    for (const rule of rules) {
      const ruleConditions = JSON.parse(rule.conditions);
      if (this.matchConditions(ruleConditions, conditions)) {
        return rule.target_tool;
      }
    }

    return null;
  }

  /**
   * 简单条件匹配
   */
  private matchConditions(
    ruleConditions: Record<string, any>,
    inputConditions: Record<string, any>,
  ): boolean {
    for (const [key, value] of Object.entries(ruleConditions)) {
      if (!(key in inputConditions)) return false;

      const inputValue = inputConditions[key];

      if (Array.isArray(value)) {
        if (!value.includes(inputValue)) return false;
      } else if (typeof value === "object") {
        // 递归匹配
        if (!this.matchConditions(value, inputValue)) return false;
      } else if (value !== inputValue) {
        return false;
      }
    }
    return true;
  }

  // ==================== Dependencies ====================

  /**
   * 获取资源依赖
   */
  getDependencies(
    resourceId: string,
    type?: DependencyType,
  ): { resource_id: string; dependency_type: DependencyType }[] {
    let sql = `
      SELECT to_resource as resource_id, dependency_type
      FROM sys_dependencies
      WHERE from_resource = ?
    `;
    const params: any[] = [resourceId];

    if (type) {
      sql += " AND dependency_type = ?";
      params.push(type);
    }

    return this.db.query(sql).all(params) as any[];
  }

  /**
   * 获取依赖此资源的资源
   */
  getDependents(
    resourceId: string,
    type?: DependencyType,
  ): { resource_id: string; dependency_type: DependencyType }[] {
    let sql = `
      SELECT from_resource as resource_id, dependency_type
      FROM sys_dependencies
      WHERE to_resource = ?
    `;
    const params: any[] = [resourceId];

    if (type) {
      sql += " AND dependency_type = ?";
      params.push(type);
    }

    return this.db.query(sql).all(params) as any[];
  }

  // ==================== Preferences ====================

  /**
   * 记录偏好
   */
  recordPreference(
    type: string,
    key: string,
    value: any,
    context?: Record<string, any>,
  ): void {
    this.db.run(
      `
      INSERT INTO sys_preferences (preference_type, preference_key, preference_value, context, usage_count, last_used_at)
      VALUES (?, ?, ?, ?, 1, CURRENT_TIMESTAMP)
      ON CONFLICT(preference_type, preference_key, context) DO UPDATE SET
        preference_value = excluded.preference_value,
        usage_count = usage_count + 1,
        confidence = MIN(1.0, confidence + 0.05),
        last_used_at = CURRENT_TIMESTAMP
    `,
      [
        type,
        key,
        JSON.stringify(value),
        context ? JSON.stringify(context) : null,
      ],
    );
  }

  /**
   * 获取偏好
   */
  getPreference(type: string, key: string): any | null {
    const row = this.db
      .query(
        `
      SELECT preference_value, confidence
      FROM sys_preferences
      WHERE preference_type = ? AND preference_key = ?
      ORDER BY confidence DESC, usage_count DESC
      LIMIT 1
    `,
      )
      .get([type, key]) as any;

    if (!row) return null;
    return JSON.parse(row.preference_value);
  }

  // ==================== Evolution ====================

  /**
   * 记录演进
   */
  recordEvolution(
    resourceId: string,
    evolutionType: EvolutionType,
    beforeState: any,
    afterState: any,
    triggerReason: string,
  ): number {
    const result = this.db.run(
      `
      INSERT INTO sys_evolution_log (resource_id, evolution_type, before_state, after_state, trigger_reason)
      VALUES (?, ?, ?, ?, ?)
    `,
      [
        resourceId,
        evolutionType,
        JSON.stringify(beforeState),
        JSON.stringify(afterState),
        triggerReason,
      ],
    );
    return Number(result.lastInsertRowid);
  }

  /**
   * 回滚演进
   */
  rollbackEvolution(evolutionId: number): void {
    this.db.run(
      `
      UPDATE sys_evolution_log
      SET status = 'rolled_back', rollback_at = CURRENT_TIMESTAMP
      WHERE id = ?
    `,
      [evolutionId],
    );
  }

  // ==================== Access Control ====================

  /**
   * 检查访问权限
   */
  checkAccess(
    subjectType: string,
    subjectId: string,
    objectType: string,
    objectId: string,
  ): Permission {
    const row = this.db
      .query(
        `
      SELECT permission FROM sys_access_control
      WHERE subject_type = ? AND subject_id = ? AND object_type = ? AND object_id = ?
    `,
      )
      .get([subjectType, subjectId, objectType, objectId]) as any;

    return row?.permission || "allow";
  }

  // ==================== Rate Limiting ====================

  /**
   * 检查速率限制
   */
  checkRateLimit(resourceId: string): { allowed: boolean; remaining: number } {
    const row = this.db
      .query(
        `
      SELECT rl.*,
             CASE
               WHEN window_start IS NULL THEN max_requests
               WHEN datetime(window_start, '+' || window_seconds || ' seconds') < datetime('now') THEN max_requests
               ELSE max_requests - current_count
             END as remaining
      FROM sys_rate_limits rl
      WHERE resource_id = ? AND enabled = 1
    `,
      )
      .get([resourceId]) as any;

    if (!row) {
      return { allowed: true, remaining: -1 }; // 无限制
    }

    const allowed = row.remaining > 0;
    return { allowed, remaining: row.remaining };
  }

  // ==================== Utility ====================

  /**
   * 获取资源概览
   */
  getResourceOverview(): any[] {
    return this.db.query("SELECT * FROM v_resource_overview").all();
  }

  /**
   * 获取 Agent 性能
   */
  getAgentPerformance(): any[] {
    return this.db.query("SELECT * FROM v_agent_performance").all();
  }

  /**
   * 获取 Skill 排行
   */
  getSkillRanking(): any[] {
    return this.db.query("SELECT * FROM v_skill_ranking").all();
  }

  /**
   * 获取模型成本
   */
  getModelCosts(): any[] {
    return this.db.query("SELECT * FROM v_model_costs").all();
  }

  /**
   * 获取最近演进
   */
  getRecentEvolutions(limit: number = 10): any[] {
    return this.db
      .query("SELECT * FROM v_recent_evolutions LIMIT ?")
      .all([limit]);
  }

  /**
   * 执行原始 SQL
   */
  raw<T = any>(sql: string, params?: any[]): T[] {
    return this.db.query(sql).all(params || []) as T[];
  }
}

// ==================== Factory ====================

let _metadataManager: MetadataManager | null = null;

export function getMetadataManager(db?: Database): MetadataManager {
  if (!_metadataManager) {
    if (!db) {
      throw new Error("Database instance required for first initialization");
    }
    _metadataManager = new MetadataManager(db);
    _metadataManager.initialize();
  }
  return _metadataManager;
}
