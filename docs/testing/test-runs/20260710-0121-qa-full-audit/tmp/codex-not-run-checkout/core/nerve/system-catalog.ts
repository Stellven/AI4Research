/**
 * Solar System Catalog
 * 系统目录 - 高级接口用于资源自省、智能路由、成本优化
 */

import { Database } from "bun:sqlite";
import {
  MetadataManager,
  getMetadataManager,
  type Resource,
  type Agent,
  type Skill,
  type Model,
  type ResourceType,
  type ResourceStatus,
  type InvocationStatus,
  type QuotaStatus,
  type ResourceHealth,
  type EvolutionCandidate,
} from "./metadata-manager";

// ==================== Types ====================

export interface CatalogStats {
  totalResources: number;
  activeResources: number;
  resourcesByType: Record<ResourceType, number>;
  invocations24h: number;
  cost24h: number;
  healthySummary: { healthy: number; warning: number; critical: number };
}

export interface RoutingDecision {
  recommended: string;
  fallback?: string;
  reason: string;
  confidence: number;
}

export interface CostSummary {
  today: number;
  thisWeek: number;
  thisMonth: number;
  byModel: Array<{ model: string; cost: number; tokens: number }>;
  trend: "increasing" | "stable" | "decreasing";
}

export interface ContextRecommendation {
  skills: Array<{ id: string; name: string; confidence: number }>;
  agents: Array<{ id: string; name: string; confidence: number }>;
}

// ==================== SystemCatalog Class ====================

export class SystemCatalog {
  private manager: MetadataManager;
  private cache: Map<string, { data: any; expires: number }> = new Map();
  private readonly CACHE_TTL = 60000; // 1 分钟缓存

  constructor(db: Database) {
    this.manager = getMetadataManager(db);
  }

  // ==================== 资源自省 ====================

  /**
   * 获取系统统计概览
   */
  getStats(): CatalogStats {
    const cached = this.getFromCache<CatalogStats>("stats");
    if (cached) return cached;

    const resources = this.manager.listResources();
    const health = this.manager.getResourceHealth();

    const stats: CatalogStats = {
      totalResources: resources.length,
      activeResources: resources.filter((r) => r.status === "active").length,
      resourcesByType: {
        agent: resources.filter((r) => r.resource_type === "agent").length,
        skill: resources.filter((r) => r.resource_type === "skill").length,
        hook: resources.filter((r) => r.resource_type === "hook").length,
        tool: resources.filter((r) => r.resource_type === "tool").length,
        model: resources.filter((r) => r.resource_type === "model").length,
        mcp_server: resources.filter((r) => r.resource_type === "mcp_server")
          .length,
      },
      invocations24h: health.reduce((sum, h) => sum + h.invocations_24h, 0),
      cost24h: this.getTodayCost(),
      healthySummary: {
        healthy: health.filter((h) => h.health_status === "healthy").length,
        warning: health.filter((h) => h.health_status === "warning").length,
        critical: health.filter((h) => h.health_status === "critical").length,
      },
    };

    this.setCache("stats", stats);
    return stats;
  }

  /**
   * 查找资源
   */
  findResource(query: string): Resource[] {
    return this.manager.listResources({ name: query });
  }

  /**
   * 获取资源详情
   */
  getResourceDetails(resourceId: string): Resource | null {
    return this.manager.getResource(resourceId);
  }

  /**
   * 列出所有 Agents
   */
  listAgents(): (Resource & Agent)[] {
    return this.manager.listAgents("active");
  }

  /**
   * 列出所有用户可调用的 Skills
   */
  listSkills(): (Resource & Skill)[] {
    return this.manager.listUserInvocableSkills();
  }

  /**
   * 通过命令获取 Skill
   */
  getSkill(command: string): (Resource & Skill) | null {
    return this.manager.getSkillByCommand(command);
  }

  /**
   * 获取阶段的主要 Agent
   */
  getPrimaryAgent(phase: string): (Resource & Agent) | null {
    const agents = this.manager.getAgentsForPhase(phase);
    const primary = agents.find((a) => a.is_primary);
    return primary || agents[0] || null;
  }

  // ==================== 智能路由 ====================

  /**
   * 选择最优模型
   */
  selectModel(context?: {
    complexity?: string;
    costSensitive?: boolean;
  }): RoutingDecision {
    // 检查配额状态
    const quotaStatus = this.manager.getQuotaStatus();
    const costQuota = quotaStatus.find((q) => q.quota_type === "cost");

    // 如果成本配额超限或警告，使用经济模型
    if (costQuota && costQuota.status !== "ok") {
      return {
        recommended: "model:haiku:1.0",
        fallback: "model:sonnet:1.0",
        reason: `Cost quota ${costQuota.status}: ${costQuota.usage_percent}% used`,
        confidence: 0.95,
      };
    }

    // 如果明确要求节省成本
    if (context?.costSensitive) {
      return {
        recommended: "model:haiku:1.0",
        reason: "Cost-sensitive mode enabled",
        confidence: 0.9,
      };
    }

    // 如果是高复杂度任务
    if (context?.complexity === "high") {
      return {
        recommended: "model:opus:1.0",
        fallback: "model:sonnet:1.0",
        reason: "High complexity task requires advanced reasoning",
        confidence: 0.85,
      };
    }

    // 默认使用 Sonnet
    const defaultModel = this.manager.getDefaultModel();
    return {
      recommended: defaultModel?.model_id || "model:sonnet:1.0",
      reason: "Default model selection",
      confidence: 0.7,
    };
  }

  /**
   * 选择最优 Agent
   */
  selectAgent(context: {
    phase?: string;
    intent?: string;
    filePattern?: string;
  }): RoutingDecision {
    // 如果有阶段，获取该阶段的主要 Agent
    if (context.phase) {
      const primary = this.getPrimaryAgent(context.phase);
      if (primary) {
        return {
          recommended: primary.resource_id,
          reason: `Primary agent for phase ${context.phase}`,
          confidence: 0.9,
        };
      }
    }

    // 尝试使用路由规则
    const recommended = this.manager.getRecommendedAgent(context);
    if (recommended) {
      return {
        recommended,
        reason: "Matched routing rule",
        confidence: 0.8,
      };
    }

    // 默认使用 Coder
    return {
      recommended: "agent:coder:1.0",
      reason: "Default agent",
      confidence: 0.5,
    };
  }

  /**
   * 获取上下文推荐
   */
  getContextRecommendations(context: {
    filePath?: string;
    keywords?: string[];
    directory?: string;
  }): ContextRecommendation {
    const recommendations: ContextRecommendation = {
      skills: [],
      agents: [],
    };

    // 从上下文模式表中匹配
    const patterns = this.manager.raw<any>(`
      SELECT * FROM sys_context_patterns
      WHERE pattern_type IN ('file_extension', 'directory', 'keyword')
      ORDER BY confidence DESC
    `);

    for (const pattern of patterns) {
      let matched = false;

      if (pattern.pattern_type === "file_extension" && context.filePath) {
        const ext = "*." + context.filePath.split(".").pop();
        matched = pattern.pattern_value === ext;
      } else if (pattern.pattern_type === "directory" && context.directory) {
        matched = context.directory.includes(
          pattern.pattern_value.replace("/*", ""),
        );
      } else if (pattern.pattern_type === "keyword" && context.keywords) {
        matched = context.keywords.some((k) =>
          k.toLowerCase().includes(pattern.pattern_value.toLowerCase()),
        );
      }

      if (matched) {
        const resources = JSON.parse(pattern.recommended_resources);
        for (const r of resources) {
          const resource = this.manager.getResource(r.id);
          if (resource && resource.status === "active") {
            if (r.type === "skill") {
              recommendations.skills.push({
                id: r.id,
                name: resource.name,
                confidence: pattern.confidence,
              });
            } else if (r.type === "agent") {
              recommendations.agents.push({
                id: r.id,
                name: resource.name,
                confidence: pattern.confidence,
              });
            }
          }
        }
      }
    }

    // 去重并按置信度排序
    recommendations.skills = this.dedupeAndSort(recommendations.skills);
    recommendations.agents = this.dedupeAndSort(recommendations.agents);

    return recommendations;
  }

  // ==================== 成本优化 ====================

  /**
   * 获取成本摘要
   */
  getCostSummary(): CostSummary {
    const cached = this.getFromCache<CostSummary>("costSummary");
    if (cached) return cached;

    const modelCosts = this.manager.getModelCosts();
    const dailyStats = this.manager.raw<any>(`
      SELECT date, SUM(total_cost_usd) as cost
      FROM sys_stats_daily
      WHERE date >= date('now', '-30 days')
      GROUP BY date
      ORDER BY date DESC
    `);

    const today = dailyStats[0]?.cost || 0;
    const thisWeek = dailyStats.slice(0, 7).reduce((sum, d) => sum + d.cost, 0);
    const thisMonth = dailyStats.reduce((sum, d) => sum + d.cost, 0);

    // 计算趋势
    const recentAvg =
      dailyStats.slice(0, 7).reduce((sum, d) => sum + d.cost, 0) / 7;
    const olderAvg =
      dailyStats.slice(7, 14).reduce((sum, d) => sum + d.cost, 0) / 7;
    let trend: "increasing" | "stable" | "decreasing" = "stable";
    if (recentAvg > olderAvg * 1.1) trend = "increasing";
    if (recentAvg < olderAvg * 0.9) trend = "decreasing";

    const summary: CostSummary = {
      today,
      thisWeek,
      thisMonth,
      byModel: modelCosts.map((m) => ({
        model: m.model_name,
        cost: m.total_cost_7d || 0,
        tokens: m.total_tokens_7d || 0,
      })),
      trend,
    };

    this.setCache("costSummary", summary);
    return summary;
  }

  /**
   * 获取今日成本
   */
  getTodayCost(): number {
    const row = this.manager.raw<any>(`
      SELECT SUM(total_cost_usd) as cost
      FROM sys_stats_daily
      WHERE date = date('now')
    `)[0];
    return row?.cost || 0;
  }

  /**
   * 检查是否应该切换到经济模式
   */
  shouldUseEconomyMode(): boolean {
    const quotaStatus = this.manager.getQuotaStatus();
    return quotaStatus.some(
      (q) => q.quota_type === "cost" && q.status !== "ok",
    );
  }

  // ==================== 性能追踪 ====================

  /**
   * 获取资源健康报告
   */
  getHealthReport(): {
    healthy: ResourceHealth[];
    warning: ResourceHealth[];
    critical: ResourceHealth[];
    unused: ResourceHealth[];
  } {
    const health = this.manager.getResourceHealth();
    return {
      healthy: health.filter((h) => h.health_status === "healthy"),
      warning: health.filter((h) => h.health_status === "warning"),
      critical: health.filter((h) => h.health_status === "critical"),
      unused: health.filter((h) => h.health_status === "unused"),
    };
  }

  /**
   * 获取性能瓶颈
   */
  getBottlenecks(): any[] {
    return this.manager.getPhaseBottlenecks();
  }

  /**
   * 记录调用
   */
  recordInvocation(
    resourceId: string,
    status: InvocationStatus,
    options?: {
      sessionId?: string;
      taskId?: number;
      inputTokens?: number;
      outputTokens?: number;
      latencyMs?: number;
      error?: string;
      metadata?: Record<string, any>;
    },
  ): void {
    this.manager.recordInvocation({
      resource_id: resourceId,
      invocation_type: "api_call",
      session_id: options?.sessionId,
      task_id: options?.taskId,
      input_tokens: options?.inputTokens,
      output_tokens: options?.outputTokens,
      latency_ms: options?.latencyMs,
      status,
      error_message: options?.error,
      metadata: options?.metadata,
    });

    // 清除缓存
    this.clearCache();
  }

  // ==================== 自我演进 ====================

  /**
   * 获取演进候选
   */
  getEvolutionCandidates(): EvolutionCandidate[] {
    return this.manager.getEvolutionCandidates();
  }

  /**
   * 获取低效资源
   */
  getUnderutilizedResources(): Resource[] {
    return this.manager.getUnderutilizedResources();
  }

  /**
   * 获取高成本资源
   */
  getHighCostResources(): any[] {
    return this.manager.getHighCostResources();
  }

  /**
   * 应用演进
   */
  applyEvolution(
    resourceId: string,
    changes: Record<string, any>,
    reason: string,
  ): number {
    const resource = this.manager.getResource(resourceId);
    if (!resource) {
      throw new Error(`Resource not found: ${resourceId}`);
    }

    const beforeState = resource.config || {};
    const afterState = { ...beforeState, ...changes };

    // 更新资源配置
    this.manager.registerResource({
      ...resource,
      config: afterState,
    });

    // 记录演进
    return this.manager.recordEvolution(
      resourceId,
      "parameter_tuning",
      beforeState,
      afterState,
      reason,
    );
  }

  // ==================== 偏好学习 ====================

  /**
   * 记录用户偏好
   */
  recordPreference(
    type: string,
    key: string,
    value: any,
    context?: Record<string, any>,
  ): void {
    this.manager.recordPreference(type, key, value, context);
  }

  /**
   * 获取用户偏好
   */
  getPreference(type: string, key: string): any {
    return this.manager.getPreference(type, key);
  }

  // ==================== 访问控制 ====================

  /**
   * 检查 Agent 是否可以使用 Tool
   */
  canAgentUseTool(agentId: string, toolId: string): boolean {
    const permission = this.manager.checkAccess(
      "agent",
      agentId,
      "tool",
      toolId,
    );
    return permission === "allow";
  }

  /**
   * 检查速率限制
   */
  checkRateLimit(resourceId: string): { allowed: boolean; remaining: number } {
    return this.manager.checkRateLimit(resourceId);
  }

  // ==================== 依赖管理 ====================

  /**
   * 获取资源依赖树
   */
  getDependencyTree(resourceId: string): any {
    const visited = new Set<string>();
    return this.buildDependencyTree(resourceId, visited);
  }

  private buildDependencyTree(
    resourceId: string,
    visited: Set<string>,
    depth = 0,
  ): any {
    if (visited.has(resourceId) || depth > 10) {
      return { id: resourceId, circular: true };
    }

    visited.add(resourceId);
    const resource = this.manager.getResource(resourceId);
    const deps = this.manager.getDependencies(resourceId);

    return {
      id: resourceId,
      name: resource?.name,
      type: resource?.resource_type,
      status: resource?.status,
      dependencies: deps.map((d) =>
        this.buildDependencyTree(d.resource_id, visited, depth + 1),
      ),
    };
  }

  // ==================== 缓存管理 ====================

  private getFromCache<T>(key: string): T | null {
    const cached = this.cache.get(key);
    if (cached && cached.expires > Date.now()) {
      return cached.data as T;
    }
    return null;
  }

  private setCache(key: string, data: any): void {
    this.cache.set(key, {
      data,
      expires: Date.now() + this.CACHE_TTL,
    });
  }

  private clearCache(): void {
    this.cache.clear();
  }

  // ==================== 工具方法 ====================

  private dedupeAndSort<T extends { id: string; confidence: number }>(
    items: T[],
  ): T[] {
    const seen = new Set<string>();
    return items
      .filter((item) => {
        if (seen.has(item.id)) return false;
        seen.add(item.id);
        return true;
      })
      .sort((a, b) => b.confidence - a.confidence);
  }

  /**
   * 获取底层 MetadataManager (用于高级操作)
   */
  getManager(): MetadataManager {
    return this.manager;
  }
}

// ==================== Factory ====================

let _catalog: SystemCatalog | null = null;

export function getSystemCatalog(db?: Database): SystemCatalog {
  if (!_catalog) {
    if (!db) {
      throw new Error("Database instance required for first initialization");
    }
    _catalog = new SystemCatalog(db);
  }
  return _catalog;
}

// ==================== 便捷导出 ====================

export {
  type Resource,
  type Agent,
  type Skill,
  type Model,
  type ResourceType,
  type ResourceStatus,
  type InvocationStatus,
  type QuotaStatus,
  type ResourceHealth,
  type EvolutionCandidate,
};
