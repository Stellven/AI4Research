/**
 * HIVE Protocol - Node Management
 * 节点注册、发现、能力管理
 */

import { randomUUID } from 'crypto';
import type {
  HiveNode,
  NodeCapability,
  NodeTier,
  HiveConfig,
} from './types';
import { DEFAULT_HIVE_CONFIG } from './types';

// ============================================================
// 节点注册表
// ============================================================

export class NodeRegistry {
  private nodes: Map<string, HiveNode> = new Map();
  private config: HiveConfig;

  constructor(config: Partial<HiveConfig> = {}) {
    this.config = { ...DEFAULT_HIVE_CONFIG, ...config };
  }

  // 注册新节点
  register(params: {
    name: string;
    owner: string;
    tier: NodeTier;
    capabilities: NodeCapability[];
  }): HiveNode {
    if (this.nodes.size >= this.config.maxNodes) {
      throw new Error(`Network full: max ${this.config.maxNodes} nodes`);
    }

    const node: HiveNode = {
      nodeId: randomUUID(),
      name: params.name,
      owner: params.owner,
      tier: params.tier,
      capabilities: params.capabilities,
      status: 'online',
      credits: this.config.creditSettings.initialCredits,
      joinedAt: new Date(),
      lastHeartbeat: new Date(),
    };

    this.nodes.set(node.nodeId, node);
    return node;
  }

  // 注销节点
  unregister(nodeId: string): boolean {
    return this.nodes.delete(nodeId);
  }

  // 获取节点
  get(nodeId: string): HiveNode | undefined {
    return this.nodes.get(nodeId);
  }

  // 更新心跳
  heartbeat(nodeId: string, status: HiveNode['status']): void {
    const node = this.nodes.get(nodeId);
    if (node) {
      node.lastHeartbeat = new Date();
      node.status = status;
    }
  }

  // 获取所有在线节点
  getOnlineNodes(): HiveNode[] {
    return Array.from(this.nodes.values()).filter(n => n.status !== 'offline');
  }

  // 按能力查找节点
  findByCapability(agentId: string, minTier?: NodeTier): HiveNode[] {
    const tierOrder: Record<NodeTier, number> = { edge: 0, local: 1, cloud: 2 };
    const minTierLevel = minTier ? tierOrder[minTier] : 0;

    return this.getOnlineNodes().filter(node => {
      // 检查层级
      if (tierOrder[node.tier] < minTierLevel) {
        return false;
      }
      // 检查能力
      return node.capabilities.some(cap => cap.agentId === agentId);
    });
  }

  // 获取网络统计
  getStats(): {
    totalNodes: number;
    onlineNodes: number;
    byTier: Record<NodeTier, number>;
    totalCredits: number;
    capabilities: Record<string, number>;
  } {
    const nodes = Array.from(this.nodes.values());
    const online = nodes.filter(n => n.status !== 'offline');

    const byTier: Record<NodeTier, number> = { edge: 0, local: 0, cloud: 0 };
    const capabilities: Record<string, number> = {};

    for (const node of online) {
      byTier[node.tier]++;
      for (const cap of node.capabilities) {
        capabilities[cap.agentId] = (capabilities[cap.agentId] || 0) + 1;
      }
    }

    return {
      totalNodes: nodes.length,
      onlineNodes: online.length,
      byTier,
      totalCredits: nodes.reduce((sum, n) => sum + n.credits, 0),
      capabilities,
    };
  }

  // 清理超时节点
  cleanupStale(timeoutMs: number = 60000): string[] {
    const now = Date.now();
    const stale: string[] = [];

    for (const [nodeId, node] of this.nodes) {
      if (now - node.lastHeartbeat.getTime() > timeoutMs) {
        node.status = 'offline';
        stale.push(nodeId);
      }
    }

    return stale;
  }

  // 序列化
  toJSON(): HiveNode[] {
    return Array.from(this.nodes.values());
  }

  // 从JSON恢复
  static fromJSON(data: HiveNode[], config?: Partial<HiveConfig>): NodeRegistry {
    const registry = new NodeRegistry(config);
    for (const node of data) {
      registry.nodes.set(node.nodeId, {
        ...node,
        joinedAt: new Date(node.joinedAt),
        lastHeartbeat: new Date(node.lastHeartbeat),
      });
    }
    return registry;
  }
}

// ============================================================
// 能力匹配器
// ============================================================

export class CapabilityMatcher {
  constructor(private registry: NodeRegistry) {}

  // 为任务查找最佳节点
  findBestNodes(params: {
    requiredAgents: string[];
    minTier: NodeTier;
    maxLatencyMs?: number;
    minSuccessRate?: number;
    limit?: number;
  }): Array<{ node: HiveNode; score: number; matchedCapabilities: NodeCapability[] }> {
    const candidates: Array<{
      node: HiveNode;
      score: number;
      matchedCapabilities: NodeCapability[];
    }> = [];

    for (const node of this.registry.getOnlineNodes()) {
      // 检查是否有所有需要的能力
      const matchedCapabilities = node.capabilities.filter(cap =>
        params.requiredAgents.includes(cap.agentId)
      );

      if (matchedCapabilities.length !== params.requiredAgents.length) {
        continue;
      }

      // 检查延迟要求
      if (params.maxLatencyMs) {
        const maxLatency = Math.max(...matchedCapabilities.map(c => c.avgLatencyMs));
        if (maxLatency > params.maxLatencyMs) {
          continue;
        }
      }

      // 检查成功率要求
      if (params.minSuccessRate) {
        const minSuccess = Math.min(...matchedCapabilities.map(c => c.successRate));
        if (minSuccess < params.minSuccessRate) {
          continue;
        }
      }

      // 计算评分
      const score = this.calculateScore(node, matchedCapabilities);
      candidates.push({ node, score, matchedCapabilities });
    }

    // 按评分排序
    candidates.sort((a, b) => b.score - a.score);

    return params.limit ? candidates.slice(0, params.limit) : candidates;
  }

  private calculateScore(node: HiveNode, capabilities: NodeCapability[]): number {
    // 评分因子
    const avgSuccessRate = capabilities.reduce((sum, c) => sum + c.successRate, 0) / capabilities.length;
    const avgLatency = capabilities.reduce((sum, c) => sum + c.avgLatencyMs, 0) / capabilities.length;
    const avgCost = capabilities.reduce((sum, c) => sum + c.creditsPerTask, 0) / capabilities.length;

    // 归一化评分 (0-100)
    const successScore = avgSuccessRate * 40;                    // 40分 - 成功率
    const latencyScore = Math.max(0, 30 - avgLatency / 100);     // 30分 - 延迟
    const costScore = Math.max(0, 20 - avgCost / 5);             // 20分 - 成本
    const creditScore = Math.min(10, node.credits / 100);         // 10分 - 信用

    return successScore + latencyScore + costScore + creditScore;
  }
}

// ============================================================
// 预定义节点能力 (Solar Agent 映射)
// ============================================================

export const SOLAR_AGENT_CAPABILITIES: Record<string, Omit<NodeCapability, 'avgLatencyMs' | 'successRate'>> = {
  // 云端 Agent (需要 Opus)
  researcher: { agentId: 'researcher', agentName: 'Researcher', tier: 'cloud', maxConcurrent: 2, creditsPerTask: 15 },
  architect: { agentId: 'architect', agentName: 'Architect', tier: 'cloud', maxConcurrent: 2, creditsPerTask: 18 },
  reporter: { agentId: 'reporter', agentName: 'Reporter', tier: 'cloud', maxConcurrent: 3, creditsPerTask: 12 },
  benchmarkReporter: { agentId: 'benchmarkReporter', agentName: 'BenchmarkReporter', tier: 'cloud', maxConcurrent: 2, creditsPerTask: 10 },
  pm: { agentId: 'pm', agentName: 'PM', tier: 'cloud', maxConcurrent: 3, creditsPerTask: 8 },

  // 本地 Agent (可用 Sonnet)
  coder: { agentId: 'coder', agentName: 'Coder', tier: 'local', maxConcurrent: 5, creditsPerTask: 8 },
  tester: { agentId: 'tester', agentName: 'Tester', tier: 'local', maxConcurrent: 5, creditsPerTask: 6 },
  reviewer: { agentId: 'reviewer', agentName: 'Reviewer', tier: 'local', maxConcurrent: 5, creditsPerTask: 5 },
  docs: { agentId: 'docs', agentName: 'Docs', tier: 'local', maxConcurrent: 5, creditsPerTask: 4 },
  ops: { agentId: 'ops', agentName: 'Ops', tier: 'local', maxConcurrent: 3, creditsPerTask: 3 },
  guard: { agentId: 'guard', agentName: 'Guard', tier: 'local', maxConcurrent: 5, creditsPerTask: 3 },
  explore: { agentId: 'explore', agentName: 'Explore', tier: 'local', maxConcurrent: 10, creditsPerTask: 4 },
  plan: { agentId: 'plan', agentName: 'Plan', tier: 'local', maxConcurrent: 3, creditsPerTask: 6 },

  // 边缘 Agent (可用 Haiku)
  secretary: { agentId: 'secretary', agentName: 'Secretary', tier: 'edge', maxConcurrent: 10, creditsPerTask: 2 },
  sm: { agentId: 'sm', agentName: 'SkillMarket', tier: 'edge', maxConcurrent: 5, creditsPerTask: 2 },
};

// 创建节点能力列表
export function createNodeCapabilities(
  agentIds: string[],
  performanceData?: Record<string, { avgLatencyMs: number; successRate: number }>
): NodeCapability[] {
  return agentIds
    .filter(id => SOLAR_AGENT_CAPABILITIES[id])
    .map(id => {
      const base = SOLAR_AGENT_CAPABILITIES[id];
      const perf = performanceData?.[id] || { avgLatencyMs: 1000, successRate: 0.9 };
      return {
        ...base,
        avgLatencyMs: perf.avgLatencyMs,
        successRate: perf.successRate,
      };
    });
}
