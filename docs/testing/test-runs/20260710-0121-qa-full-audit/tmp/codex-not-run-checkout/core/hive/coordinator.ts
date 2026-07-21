/**
 * HIVE Coordinator Election
 * 基于信誉和性能的 Coordinator 选举
 */

import type { HiveNode, NodeTier } from './types';

const TIER_SCORE: Record<NodeTier, number> = {
  cloud: 30,
  local: 20,
  edge: 10,
};

export interface CoordinatorCandidate {
  nodeId: string;
  name: string;
  score: number;
  breakdown: {
    reputation: number;    // 信誉分 (40%)
    uptime: number;        // 在线时长分 (30%)
    computing: number;     // 算力分 (20%)
    network: number;       // 网络分 (10%)
  };
}

export interface ElectionResult {
  coordinatorId: string;
  coordinatorName: string;
  score: number;
  totalCandidates: number;
  electedAt: Date;
}

/**
 * Coordinator 选举器
 */
export class CoordinatorElection {
  private currentCoordinator?: ElectionResult;
  private electionHistory: ElectionResult[] = [];

  /**
   * 执行选举
   * @param nodes 所有在线节点
   * @param networkStats 网络统计 (用于计算网络分)
   */
  elect(
    nodes: HiveNode[],
    networkStats?: Map<string, { latencyMs: number; packetLoss: number }>
  ): ElectionResult {
    console.log(`[Election] 开始选举 (候选节点: ${nodes.length})`);

    if (nodes.length === 0) {
      throw new Error('No nodes available for election');
    }

    // 计算每个节点的评分
    const candidates = nodes.map(node => this.calculateScore(node, networkStats));

    // 按评分排序
    candidates.sort((a, b) => b.score - a.score);

    // 显示评分详情
    console.log('[Election] 候选节点评分:');
    for (const c of candidates.slice(0, 5)) {
      console.log(
        `  ${c.name.padEnd(20)} Score: ${c.score.toFixed(1)} ` +
        `[信誉 ${c.breakdown.reputation.toFixed(1)} + ` +
        `在线 ${c.breakdown.uptime.toFixed(1)} + ` +
        `算力 ${c.breakdown.computing.toFixed(1)} + ` +
        `网络 ${c.breakdown.network.toFixed(1)}]`
      );
    }

    // 选出最高分
    const winner = candidates[0];

    const result: ElectionResult = {
      coordinatorId: winner.nodeId,
      coordinatorName: winner.name,
      score: winner.score,
      totalCandidates: candidates.length,
      electedAt: new Date(),
    };

    console.log(`[Election] ✓ 当选 Coordinator: ${winner.name} (评分: ${winner.score.toFixed(1)})`);

    this.currentCoordinator = result;
    this.electionHistory.push(result);

    return result;
  }

  /**
   * 检查是否需要重新选举
   * @param currentCoordinatorId 当前 Coordinator ID
   * @param nodes 所有在线节点
   * @returns 是否需要重新选举
   */
  shouldReelect(currentCoordinatorId: string, nodes: HiveNode[]): boolean {
    // 1. Coordinator 下线
    const coordinatorOnline = nodes.some(n => n.nodeId === currentCoordinatorId);
    if (!coordinatorOnline) {
      console.log('[Election] Coordinator 下线，触发重新选举');
      return true;
    }

    // 2. 有明显更优的节点出现 (分数差 >20)
    const current = nodes.find(n => n.nodeId === currentCoordinatorId);
    if (!current) return true;

    const currentScore = this.calculateScore(current, undefined).score;
    const allScores = nodes.map(n => this.calculateScore(n, undefined).score);
    const maxScore = Math.max(...allScores);

    if (maxScore - currentScore > 20) {
      console.log('[Election] 发现更优节点，触发重新选举');
      return true;
    }

    return false;
  }

  /**
   * 获取当前 Coordinator
   */
  getCurrentCoordinator(): ElectionResult | undefined {
    return this.currentCoordinator;
  }

  /**
   * 获取选举历史
   */
  getHistory(): ElectionResult[] {
    return [...this.electionHistory];
  }

  // ============================================================
  // 私有方法: 评分算法
  // ============================================================

  /**
   * 计算节点评分
   */
  private calculateScore(
    node: HiveNode,
    networkStats?: Map<string, { latencyMs: number; packetLoss: number }>
  ): CoordinatorCandidate {
    const reputation = this.calculateReputationScore(node);
    const uptime = this.calculateUptimeScore(node);
    const computing = this.calculateComputingScore(node);
    const network = this.calculateNetworkScore(node, networkStats);

    const score = reputation + uptime + computing + network;

    return {
      nodeId: node.nodeId,
      name: node.name,
      score,
      breakdown: {
        reputation,
        uptime,
        computing,
        network,
      },
    };
  }

  /**
   * 信誉分 (40%)
   * 基于:
   * - 成功率 (主要)
   * - 积分余额 (次要)
   */
  private calculateReputationScore(node: HiveNode): number {
    // 根据能力的平均成功率
    const avgSuccessRate = node.capabilities.length > 0
      ? node.capabilities.reduce((sum, c) => sum + c.successRate, 0) / node.capabilities.length
      : 0.5;

    // 积分归一化 (假设 1000 积分为满分)
    const creditScore = Math.min(node.credits / 1000, 1);

    // 信誉分 = 成功率 80% + 积分 20%
    return (avgSuccessRate * 0.8 + creditScore * 0.2) * 40;
  }

  /**
   * 在线时长分 (30%)
   * 优先选择在线时间长的稳定节点
   */
  private calculateUptimeScore(node: HiveNode): number {
    const now = Date.now();
    const joinedMs = now - node.joinedAt.getTime();
    const uptimeHours = joinedMs / (1000 * 60 * 60);

    // 假设 24 小时为满分
    const uptimeRatio = Math.min(uptimeHours / 24, 1);

    // 最近心跳时间 (越新越好)
    const lastHeartbeatMs = now - node.lastHeartbeat.getTime();
    const freshnessRatio = Math.max(0, 1 - lastHeartbeatMs / (5 * 60 * 1000)); // 5分钟内满分

    return (uptimeRatio * 0.7 + freshnessRatio * 0.3) * 30;
  }

  /**
   * 算力分 (20%)
   * 基于:
   * - 节点层级 (cloud > local > edge)
   * - 能力数量
   * - 并发能力
   */
  private calculateComputingScore(node: HiveNode): number {
    // 层级分
    const tierScore = TIER_SCORE[node.tier] || 0;

    // 能力数量归一化 (假设 10 个能力为满分)
    const capabilityCount = Math.min(node.capabilities.length / 10, 1) * 30;

    // 并发能力 (总并发数)
    const totalConcurrent = node.capabilities.reduce((sum, c) => sum + c.maxConcurrent, 0);
    const concurrentScore = Math.min(totalConcurrent / 50, 1) * 30;

    // 算力分 = 层级 40% + 能力数 30% + 并发 30%
    return (tierScore + capabilityCount + concurrentScore) / 100 * 20;
  }

  /**
   * 网络分 (10%)
   * 基于延迟和丢包率
   */
  private calculateNetworkScore(
    node: HiveNode,
    networkStats?: Map<string, { latencyMs: number; packetLoss: number }>
  ): number {
    if (!networkStats || !networkStats.has(node.nodeId)) {
      return 5; // 默认给 50% 分数
    }

    const stats = networkStats.get(node.nodeId)!;

    // 延迟分 (假设 50ms 为满分)
    const latencyScore = Math.max(0, 1 - stats.latencyMs / 50);

    // 丢包分 (0% 丢包满分)
    const packetLossScore = Math.max(0, 1 - stats.packetLoss);

    return (latencyScore * 0.6 + packetLossScore * 0.4) * 10;
  }
}

/**
 * 主备切换管理器
 */
export class FailoverManager {
  private coordinator?: ElectionResult;
  private backup?: ElectionResult;
  private election: CoordinatorElection;

  constructor(election: CoordinatorElection) {
    this.election = election;
  }

  /**
   * 设置 Coordinator 和 Backup
   */
  setLeadership(coordinator: ElectionResult, backup?: ElectionResult): void {
    this.coordinator = coordinator;
    this.backup = backup;
    console.log(`[Failover] Coordinator: ${coordinator.coordinatorName}`);
    if (backup) {
      console.log(`[Failover] Backup: ${backup.coordinatorName}`);
    }
  }

  /**
   * 处理 Coordinator 失效
   */
  handleCoordinatorFailure(nodes: HiveNode[]): ElectionResult {
    console.log('[Failover] Coordinator 失效，切换到 Backup...');

    if (this.backup) {
      // 如果有 Backup，直接提升
      const backupNode = nodes.find(n => n.nodeId === this.backup!.coordinatorId);
      if (backupNode) {
        console.log(`[Failover] ✓ Backup 提升为 Coordinator: ${this.backup.coordinatorName}`);
        this.coordinator = this.backup;
        this.backup = undefined;
        return this.coordinator;
      }
    }

    // 否则重新选举
    console.log('[Failover] 无可用 Backup，重新选举...');
    const result = this.election.elect(nodes);
    this.coordinator = result;
    return result;
  }

  /**
   * 获取当前 Coordinator
   */
  getCoordinator(): ElectionResult | undefined {
    return this.coordinator;
  }

  /**
   * 获取 Backup
   */
  getBackup(): ElectionResult | undefined {
    return this.backup;
  }
}
