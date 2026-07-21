/**
 * HIVE Protocol - Main Entry
 * Heterogeneous Intelligent Virtual Ecosystem
 *
 * 命名者：李卓远 (继承人)
 * 核心原则：不传参数、不传权重、只传任务
 */

import { randomUUID } from 'crypto';
import { NodeRegistry, CapabilityMatcher, createNodeCapabilities, SOLAR_AGENT_CAPABILITIES } from './node';
import { TaskScheduler, QuickScheduler } from './scheduler';
import { CreditLedger, IncentiveStrategy } from './credits';
import { MessageFactory, serializeMessage, deserializeMessage, validateMessage, createTask } from './protocol';
import type {
  HiveConfig,
  HiveNode,
  HiveTask,
  NodeTier,
  TaskResult,
  HiveMessage,
} from './types';
import { DEFAULT_HIVE_CONFIG } from './types';

// Re-export all types
export * from './types';
export * from './node';
export * from './scheduler';
export * from './credits';
export * from './protocol';

// ============================================================
// HIVE Network - 主控类
// ============================================================

export class HiveNetwork {
  public readonly networkId: string;
  public readonly config: HiveConfig;

  public readonly registry: NodeRegistry;
  public readonly ledger: CreditLedger;
  public readonly incentive: IncentiveStrategy;

  private schedulers: Map<string, TaskScheduler> = new Map();
  private messageFactories: Map<string, MessageFactory> = new Map();

  constructor(config: Partial<HiveConfig> = {}) {
    this.config = { ...DEFAULT_HIVE_CONFIG, ...config };
    this.networkId = this.config.networkId;

    this.registry = new NodeRegistry(this.config);
    this.ledger = new CreditLedger(this.config);
    this.incentive = new IncentiveStrategy(this.config.creditSettings);
  }

  // ============================================================
  // 节点管理
  // ============================================================

  // 加入网络
  joinNetwork(params: {
    name: string;
    owner: string;
    tier: NodeTier;
    agentIds: string[];
    performanceData?: Record<string, { avgLatencyMs: number; successRate: number }>;
  }): HiveNode {
    const capabilities = createNodeCapabilities(params.agentIds, params.performanceData);

    const node = this.registry.register({
      name: params.name,
      owner: params.owner,
      tier: params.tier,
      capabilities,
    });

    // 创建积分账户
    this.ledger.createAccount(node.nodeId);

    // 创建消息工厂和调度器
    const factory = new MessageFactory(node.nodeId);
    this.messageFactories.set(node.nodeId, factory);

    const scheduler = new TaskScheduler(this.registry, factory, this.config);
    this.setupSchedulerCallbacks(scheduler, node.nodeId);
    this.schedulers.set(node.nodeId, scheduler);

    return node;
  }

  // 离开网络
  leaveNetwork(nodeId: string): boolean {
    this.schedulers.delete(nodeId);
    this.messageFactories.delete(nodeId);
    return this.registry.unregister(nodeId);
  }

  // 心跳
  heartbeat(nodeId: string, status: 'online' | 'offline' | 'busy'): void {
    this.registry.heartbeat(nodeId, status);
  }

  // ============================================================
  // 任务提交
  // ============================================================

  // 提交任务
  submitTask(
    fromNodeId: string,
    params: {
      title: string;
      description: string;
      requiredAgents: string[];
      minTier?: NodeTier;
      priority?: 'low' | 'normal' | 'high' | 'urgent';
    }
  ): { task: HiveTask; offerMessage: HiveMessage } | null {
    const scheduler = this.schedulers.get(fromNodeId);
    if (!scheduler) {
      return null;
    }

    return scheduler.submitTask(params);
  }

  // 快速提交（自动分配）
  quickSubmit(
    fromNodeId: string,
    title: string,
    description: string,
    requiredAgents: string[]
  ): { task: HiveTask; assignedTo?: string } | null {
    const scheduler = this.schedulers.get(fromNodeId);
    if (!scheduler) {
      return null;
    }

    const { task, offerMessage } = scheduler.submitTask({
      title,
      description,
      requiredAgents,
    });

    const { winnerId } = scheduler.resolveBidding(task.taskId);

    return {
      task: scheduler.getTask(task.taskId)!,
      assignedTo: winnerId,
    };
  }

  // 报告结果
  reportResult(nodeId: string, taskId: string, result: TaskResult): void {
    // 查找拥有该任务的调度器
    for (const [, scheduler] of this.schedulers) {
      const task = scheduler.getTask(taskId);
      if (task) {
        scheduler.receiveResult(taskId, result);
        break;
      }
    }
  }

  // ============================================================
  // 调度器回调
  // ============================================================

  private setupSchedulerCallbacks(scheduler: TaskScheduler, nodeId: string): void {
    scheduler.onTaskAssigned = (task, assignedNodeId) => {
      console.log(`[HIVE] Task ${task.taskId} assigned to ${assignedNodeId}`);
    };

    scheduler.onTaskCompleted = (task, result) => {
      const assignedTo = task.assignedTo;
      if (!assignedTo) return;

      if (result.success) {
        // 奖励执行者
        const reward = this.incentive.calculateTaskReward({
          baseDifficulty: task.priority === 'urgent' ? 8 : task.priority === 'high' ? 6 : 4,
          completionTimeMs: task.completedAt!.getTime() - task.createdAt.getTime(),
          expectedTimeMs: 30000,
          successRate: 0.9,
        });
        this.ledger.rewardForTask(assignedTo, reward, task.taskId);
        console.log(`[HIVE] Task ${task.taskId} completed. Rewarded ${reward} credits to ${assignedTo}`);
      } else {
        // 惩罚执行者
        const penalty = this.incentive.calculatePenalty({
          baseReward: this.config.creditSettings.taskBaseReward,
          failureReason: 'error',
        });
        this.ledger.penalty(assignedTo, penalty, task.taskId);
        console.log(`[HIVE] Task ${task.taskId} failed. Penalized ${penalty} credits from ${assignedTo}`);
      }
    };
  }

  // ============================================================
  // 统计
  // ============================================================

  getNetworkStats(): {
    network: { id: string; name: string };
    nodes: ReturnType<NodeRegistry['getStats']>;
    credits: ReturnType<CreditLedger['getStats']>;
    tasks: ReturnType<TaskScheduler['getStats']>;
  } {
    // 合并所有调度器的统计
    const taskStats = {
      total: 0,
      byStatus: {
        pending: 0, bidding: 0, assigned: 0, running: 0,
        completed: 0, failed: 0, verified: 0
      } as Record<string, number>,
      avgCompletionTimeMs: 0,
      successRate: 0,
    };

    for (const [, scheduler] of this.schedulers) {
      const stats = scheduler.getStats();
      taskStats.total += stats.total;
      for (const [status, count] of Object.entries(stats.byStatus)) {
        taskStats.byStatus[status] = (taskStats.byStatus[status] || 0) + count;
      }
    }

    return {
      network: {
        id: this.networkId,
        name: this.config.name,
      },
      nodes: this.registry.getStats(),
      credits: this.ledger.getStats(),
      tasks: taskStats as ReturnType<TaskScheduler['getStats']>,
    };
  }

  // ============================================================
  // 序列化
  // ============================================================

  toJSON(): object {
    return {
      networkId: this.networkId,
      config: this.config,
      nodes: this.registry.toJSON(),
      credits: this.ledger.toJSON(),
    };
  }

  static fromJSON(data: {
    networkId: string;
    config: HiveConfig;
    nodes: HiveNode[];
    credits: ReturnType<CreditLedger['toJSON']>;
  }): HiveNetwork {
    const network = new HiveNetwork(data.config);

    // 恢复节点
    for (const node of data.nodes) {
      network.registry['nodes'].set(node.nodeId, {
        ...node,
        joinedAt: new Date(node.joinedAt),
        lastHeartbeat: new Date(node.lastHeartbeat),
      });

      // 创建消息工厂和调度器
      const factory = new MessageFactory(node.nodeId);
      network.messageFactories.set(node.nodeId, factory);

      const scheduler = new TaskScheduler(network.registry, factory, network.config);
      network.setupSchedulerCallbacks(scheduler, node.nodeId);
      network.schedulers.set(node.nodeId, scheduler);
    }

    // 恢复积分账本
    const restoredLedger = CreditLedger.fromJSON(data.credits, network.config);
    (network as any).ledger = restoredLedger;

    return network;
  }
}

// ============================================================
// CLI 入口
// ============================================================

async function main() {
  const args = process.argv.slice(2);
  const command = args[0];

  switch (command) {
    case 'demo':
      await runDemo();
      break;
    case 'stats':
      console.log('HIVE Network Stats - requires running network');
      break;
    default:
      console.log(`
HIVE Protocol - Heterogeneous Intelligent Virtual Ecosystem
命名者: 李卓远 (继承人)

Usage:
  bun run index.ts demo      Run demo
  bun run index.ts stats     Show network stats

核心原则:
  ✗ 不传参数
  ✗ 不传权重
  ✓ 只传任务
      `);
  }
}

async function runDemo() {
  console.log('═══════════════════════════════════════════════════════════════');
  console.log('         HIVE Protocol Demo');
  console.log('         Heterogeneous Intelligent Virtual Ecosystem');
  console.log('═══════════════════════════════════════════════════════════════\n');

  // 创建网络
  const hive = new HiveNetwork({
    networkId: 'demo-hive',
    name: 'Demo Community',
    maxNodes: 10,
  });

  // 添加节点
  console.log('1. Joining nodes to network...\n');

  const node1 = hive.joinNetwork({
    name: 'Mac-001',
    owner: 'Alice',
    tier: 'local',
    agentIds: ['coder', 'tester', 'reviewer', 'docs'],
    performanceData: {
      coder: { avgLatencyMs: 800, successRate: 0.92 },
      tester: { avgLatencyMs: 600, successRate: 0.95 },
      reviewer: { avgLatencyMs: 500, successRate: 0.90 },
      docs: { avgLatencyMs: 400, successRate: 0.98 },
    },
  });
  console.log(`   [+] ${node1.name} joined (${node1.tier}) - Credits: ${node1.credits}`);

  const node2 = hive.joinNetwork({
    name: 'Mac-002',
    owner: 'Bob',
    tier: 'local',
    agentIds: ['coder', 'ops', 'guard'],
    performanceData: {
      coder: { avgLatencyMs: 900, successRate: 0.88 },
      ops: { avgLatencyMs: 300, successRate: 0.96 },
      guard: { avgLatencyMs: 200, successRate: 0.99 },
    },
  });
  console.log(`   [+] ${node2.name} joined (${node2.tier}) - Credits: ${node2.credits}`);

  const node3 = hive.joinNetwork({
    name: 'Cloud-001',
    owner: 'System',
    tier: 'cloud',
    agentIds: ['researcher', 'architect', 'reporter'],
    performanceData: {
      researcher: { avgLatencyMs: 2000, successRate: 0.85 },
      architect: { avgLatencyMs: 2500, successRate: 0.82 },
      reporter: { avgLatencyMs: 1500, successRate: 0.90 },
    },
  });
  console.log(`   [+] ${node3.name} joined (${node3.tier}) - Credits: ${node3.credits}`);

  // 提交任务
  console.log('\n2. Submitting tasks...\n');

  const result1 = hive.quickSubmit(
    node1.nodeId,
    '代码审查',
    '审查 feature/hive-protocol 分支的代码变更，检查代码质量和潜在问题',
    ['reviewer']
  );
  console.log(`   [TASK] "${result1?.task.title}" -> ${result1?.assignedTo || 'unassigned'}`);

  const result2 = hive.quickSubmit(
    node2.nodeId,
    '技术调研',
    '研究 WebRTC 用于节点间 P2P 通信的可行性',
    ['researcher']
  );
  console.log(`   [TASK] "${result2?.task.title}" -> ${result2?.assignedTo || 'unassigned'}`);

  // 模拟任务完成
  console.log('\n3. Completing tasks...\n');

  if (result1?.task && result1.assignedTo) {
    hive.reportResult(result1.assignedTo, result1.task.taskId, {
      success: true,
      output: '代码审查完成，发现 3 个小问题，已提交评论',
      metrics: { tokensUsed: 5000, latencyMs: 450, cost: 0.05 },
    });
    console.log(`   [DONE] "${result1.task.title}" - Success`);
  }

  if (result2?.task && result2.assignedTo) {
    hive.reportResult(result2.assignedTo, result2.task.taskId, {
      success: true,
      output: 'WebRTC 可行性分析完成，建议使用 simple-peer 库',
      metrics: { tokensUsed: 15000, latencyMs: 1800, cost: 0.60 },
    });
    console.log(`   [DONE] "${result2.task.title}" - Success`);
  }

  // 显示统计
  console.log('\n4. Network Stats\n');
  const stats = hive.getNetworkStats();

  console.log(`   Network: ${stats.network.name} (${stats.network.id})`);
  console.log(`   Nodes: ${stats.nodes.onlineNodes}/${stats.nodes.totalNodes} online`);
  console.log(`   Credits: ${stats.credits.totalCreditsInCirculation} total, ${stats.credits.avgBalance.toFixed(1)} avg`);
  console.log(`   Tasks: ${stats.tasks.total} total`);

  // 显示排行榜
  console.log('\n5. Credit Leaderboard\n');
  const leaderboard = hive.ledger.getLeaderboard(5);
  for (let i = 0; i < leaderboard.length; i++) {
    const entry = leaderboard[i];
    const node = hive.registry.get(entry.nodeId);
    console.log(`   ${i + 1}. ${node?.name || entry.nodeId}: ${entry.balance} credits (earned: ${entry.earned})`);
  }

  console.log('\n═══════════════════════════════════════════════════════════════');
  console.log('         Demo Complete');
  console.log('═══════════════════════════════════════════════════════════════\n');
}

// Run CLI
if (import.meta.main) {
  main().catch(console.error);
}
