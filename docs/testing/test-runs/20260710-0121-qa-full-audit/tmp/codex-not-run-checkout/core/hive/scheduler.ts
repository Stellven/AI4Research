/**
 * HIVE Protocol - Task Scheduler
 * 任务调度、竞标管理、结果验证
 */

import { randomUUID } from 'crypto';
import type {
  HiveTask,
  TaskStatus,
  TaskResult,
  HiveMessage,
  BidPayload,
  HiveConfig,
} from './types';
import { DEFAULT_HIVE_CONFIG } from './types';
import { NodeRegistry, CapabilityMatcher } from './node';
import { MessageFactory, createTask } from './protocol';

// ============================================================
// 竞标会话
// ============================================================

interface BiddingSession {
  taskId: string;
  task: HiveTask;
  bids: BidPayload[];
  deadline: Date;
  resolved: boolean;
  winnerId?: string;
}

// ============================================================
// 任务调度器
// ============================================================

export class TaskScheduler {
  private tasks: Map<string, HiveTask> = new Map();
  private biddingSessions: Map<string, BiddingSession> = new Map();
  private matcher: CapabilityMatcher;
  private config: HiveConfig;

  // 事件回调
  public onTaskAssigned?: (task: HiveTask, nodeId: string) => void;
  public onTaskCompleted?: (task: HiveTask, result: TaskResult) => void;
  public onBiddingTimeout?: (taskId: string) => void;

  constructor(
    private registry: NodeRegistry,
    private messageFactory: MessageFactory,
    config: Partial<HiveConfig> = {}
  ) {
    this.config = { ...DEFAULT_HIVE_CONFIG, ...config };
    this.matcher = new CapabilityMatcher(registry);
  }

  // ============================================================
  // 任务生命周期
  // ============================================================

  // 1. 创建并广播任务
  submitTask(params: {
    title: string;
    description: string;
    requiredAgents: string[];
    minTier?: 'edge' | 'local' | 'cloud';
    priority?: 'low' | 'normal' | 'high' | 'urgent';
    deadline?: Date;
  }): { task: HiveTask; offerMessage: HiveMessage } {
    const task = createTask(params);
    task.createdBy = this.messageFactory['nodeId'];
    task.status = 'bidding';

    this.tasks.set(task.taskId, task);

    // 创建竞标会话
    const session: BiddingSession = {
      taskId: task.taskId,
      task,
      bids: [],
      deadline: new Date(Date.now() + this.config.biddingTimeoutMs),
      resolved: false,
    };
    this.biddingSessions.set(task.taskId, session);

    // 创建广播消息
    const offerMessage = this.messageFactory.taskOffer(task, this.config.biddingTimeoutMs);

    // 设置超时处理
    setTimeout(() => this.resolveBidding(task.taskId), this.config.biddingTimeoutMs);

    return { task, offerMessage };
  }

  // 2. 接收竞标
  receiveBid(bid: BidPayload): boolean {
    const session = this.biddingSessions.get(bid.taskId);
    if (!session || session.resolved) {
      return false;
    }

    // 检查是否在截止时间内
    if (new Date() > session.deadline) {
      return false;
    }

    session.bids.push(bid);
    return true;
  }

  // 3. 解决竞标（选择最佳节点）
  resolveBidding(taskId: string): { winnerId?: string; assignMessage?: HiveMessage } {
    const session = this.biddingSessions.get(taskId);
    if (!session || session.resolved) {
      return {};
    }

    session.resolved = true;
    const task = this.tasks.get(taskId);
    if (!task) {
      return {};
    }

    if (session.bids.length === 0) {
      // 没有竞标，尝试自动匹配
      const candidates = this.matcher.findBestNodes({
        requiredAgents: task.requirements.requiredAgents,
        minTier: task.requirements.minTier,
        limit: 1,
      });

      if (candidates.length === 0) {
        task.status = 'failed';
        task.result = { success: false, output: 'No available nodes for this task' };
        this.onBiddingTimeout?.(taskId);
        return {};
      }

      session.winnerId = candidates[0].node.nodeId;
    } else {
      // 选择最佳竞标
      const winner = this.selectWinner(session.bids);
      session.winnerId = winner.nodeId;
    }

    // 更新任务状态
    task.status = 'assigned';
    task.assignedTo = session.winnerId;

    // 创建分配消息
    const winningBid = session.bids.find(b => b.nodeId === session.winnerId);
    const credits = winningBid?.estimatedCredits || this.config.creditSettings.taskBaseReward;
    const assignMessage = this.messageFactory.assign(taskId, session.winnerId, credits);

    this.onTaskAssigned?.(task, session.winnerId);

    return { winnerId: session.winnerId, assignMessage };
  }

  // 4. 接收结果
  receiveResult(taskId: string, result: TaskResult): { verifyMessage?: HiveMessage } {
    const task = this.tasks.get(taskId);
    if (!task || task.status !== 'assigned') {
      return {};
    }

    task.status = 'completed';
    task.result = result;
    task.completedAt = new Date();

    // 自动验证（简单策略：成功则通过）
    const verified = result.success;
    const creditsAwarded = verified
      ? this.config.creditSettings.taskBaseReward
      : -Math.floor(this.config.creditSettings.taskBaseReward * this.config.creditSettings.penaltyRate);

    task.status = verified ? 'verified' : 'failed';

    const verifyMessage = this.messageFactory.verify(
      taskId,
      verified,
      creditsAwarded,
      verified ? 'Task completed successfully' : 'Task verification failed'
    );

    this.onTaskCompleted?.(task, result);

    return { verifyMessage };
  }

  // ============================================================
  // 选择最佳竞标
  // ============================================================

  private selectWinner(bids: BidPayload[]): BidPayload {
    // 评分规则：
    // - 置信度 40%
    // - 延迟 30%
    // - 成本 30%

    const scored = bids.map(bid => {
      const confidenceScore = bid.confidence * 40;
      const latencyScore = Math.max(0, 30 - bid.estimatedLatencyMs / 100);
      const costScore = Math.max(0, 30 - bid.estimatedCredits / 2);
      const totalScore = confidenceScore + latencyScore + costScore;
      return { bid, score: totalScore };
    });

    scored.sort((a, b) => b.score - a.score);
    return scored[0].bid;
  }

  // ============================================================
  // 查询方法
  // ============================================================

  getTask(taskId: string): HiveTask | undefined {
    return this.tasks.get(taskId);
  }

  getTasksByStatus(status: TaskStatus): HiveTask[] {
    return Array.from(this.tasks.values()).filter(t => t.status === status);
  }

  getPendingTasks(): HiveTask[] {
    return this.getTasksByStatus('pending').concat(this.getTasksByStatus('bidding'));
  }

  getActiveTasks(): HiveTask[] {
    return this.getTasksByStatus('assigned').concat(this.getTasksByStatus('running'));
  }

  getCompletedTasks(limit?: number): HiveTask[] {
    const completed = this.getTasksByStatus('verified');
    return limit ? completed.slice(-limit) : completed;
  }

  // 获取调度统计
  getStats(): {
    total: number;
    byStatus: Record<TaskStatus, number>;
    avgCompletionTimeMs: number;
    successRate: number;
  } {
    const tasks = Array.from(this.tasks.values());
    const byStatus: Record<TaskStatus, number> = {
      pending: 0, bidding: 0, assigned: 0, running: 0, completed: 0, failed: 0, verified: 0
    };

    let totalCompletionTime = 0;
    let completedCount = 0;
    let successCount = 0;
    let finishedCount = 0;

    for (const task of tasks) {
      byStatus[task.status]++;
      if (task.completedAt && task.createdAt) {
        totalCompletionTime += task.completedAt.getTime() - task.createdAt.getTime();
        completedCount++;
      }
      if (task.status === 'verified' || task.status === 'failed') {
        finishedCount++;
        if (task.status === 'verified') {
          successCount++;
        }
      }
    }

    return {
      total: tasks.length,
      byStatus,
      avgCompletionTimeMs: completedCount > 0 ? totalCompletionTime / completedCount : 0,
      successRate: finishedCount > 0 ? successCount / finishedCount : 0,
    };
  }
}

// ============================================================
// 快速任务调度（单节点模式）
// ============================================================

export class QuickScheduler {
  private scheduler: TaskScheduler;

  constructor(
    registry: NodeRegistry,
    nodeId: string,
    config?: Partial<HiveConfig>
  ) {
    const factory = new MessageFactory(nodeId);
    this.scheduler = new TaskScheduler(registry, factory, config);
  }

  // 快速提交任务（自动选择最佳节点）
  async quickSubmit(params: {
    title: string;
    description: string;
    requiredAgents: string[];
  }): Promise<{ task: HiveTask; assignedTo?: string }> {
    const { task } = this.scheduler.submitTask(params);

    // 立即解决（不等待竞标）
    const { winnerId } = this.scheduler.resolveBidding(task.taskId);

    return {
      task: this.scheduler.getTask(task.taskId)!,
      assignedTo: winnerId,
    };
  }

  // 报告结果
  reportResult(taskId: string, result: TaskResult): void {
    this.scheduler.receiveResult(taskId, result);
  }

  // 获取统计
  getStats() {
    return this.scheduler.getStats();
  }
}
