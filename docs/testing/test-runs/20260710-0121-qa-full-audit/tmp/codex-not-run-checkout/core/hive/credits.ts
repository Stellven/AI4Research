/**
 * HIVE Protocol - Credit System
 * Solar Credits 积分系统
 *
 * 激励机制：贡献算力获得积分，使用算力消耗积分
 */

import { randomUUID } from 'crypto';
import type {
  CreditTransaction,
  CreditAccount,
  HiveConfig,
} from './types';
import { DEFAULT_HIVE_CONFIG } from './types';

// ============================================================
// 积分账本
// ============================================================

export class CreditLedger {
  private accounts: Map<string, CreditAccount> = new Map();
  private transactions: CreditTransaction[] = [];
  private config: HiveConfig;

  constructor(config: Partial<HiveConfig> = {}) {
    this.config = { ...DEFAULT_HIVE_CONFIG, ...config };
  }

  // 创建账户
  createAccount(nodeId: string): CreditAccount {
    if (this.accounts.has(nodeId)) {
      return this.accounts.get(nodeId)!;
    }

    const account: CreditAccount = {
      nodeId,
      balance: this.config.creditSettings.initialCredits,
      earned: 0,
      spent: 0,
      transactions: [],
    };

    this.accounts.set(nodeId, account);

    // 记录初始积分
    this.recordTransaction({
      from: 'system',
      to: nodeId,
      amount: this.config.creditSettings.initialCredits,
      type: 'bonus',
    });

    return account;
  }

  // 获取账户
  getAccount(nodeId: string): CreditAccount | undefined {
    return this.accounts.get(nodeId);
  }

  // 获取余额
  getBalance(nodeId: string): number {
    return this.accounts.get(nodeId)?.balance || 0;
  }

  // ============================================================
  // 交易操作
  // ============================================================

  // 任务支付（任务发起者支付）
  payForTask(fromNodeId: string, toNodeId: string, amount: number, taskId: string): boolean {
    return this.transfer(fromNodeId, toNodeId, amount, 'task_payment', taskId);
  }

  // 任务奖励（任务完成者获得）
  rewardForTask(nodeId: string, amount: number, taskId: string): void {
    this.credit(nodeId, amount, 'task_reward', taskId);
  }

  // 惩罚（任务失败）
  penalty(nodeId: string, amount: number, taskId: string): void {
    this.debit(nodeId, amount, 'penalty', taskId);
  }

  // 奖励（系统奖励）
  bonus(nodeId: string, amount: number, reason: string): void {
    this.credit(nodeId, amount, 'bonus');
  }

  // ============================================================
  // 基础操作
  // ============================================================

  private transfer(
    from: string,
    to: string,
    amount: number,
    type: CreditTransaction['type'],
    taskId?: string
  ): boolean {
    const fromAccount = this.accounts.get(from);
    const toAccount = this.accounts.get(to);

    if (!fromAccount || !toAccount) {
      return false;
    }

    if (fromAccount.balance < amount) {
      return false; // 余额不足
    }

    // 扣款
    fromAccount.balance -= amount;
    fromAccount.spent += amount;

    // 入账
    toAccount.balance += amount;
    toAccount.earned += amount;

    // 记录交易
    this.recordTransaction({ from, to, amount, type, taskId });

    return true;
  }

  private credit(nodeId: string, amount: number, type: CreditTransaction['type'], taskId?: string): void {
    const account = this.accounts.get(nodeId);
    if (!account) return;

    account.balance += amount;
    account.earned += amount;

    this.recordTransaction({ from: 'system', to: nodeId, amount, type, taskId });
  }

  private debit(nodeId: string, amount: number, type: CreditTransaction['type'], taskId?: string): void {
    const account = this.accounts.get(nodeId);
    if (!account) return;

    account.balance = Math.max(0, account.balance - amount);
    account.spent += amount;

    this.recordTransaction({ from: nodeId, to: 'system', amount, type, taskId });
  }

  private recordTransaction(params: {
    from: string;
    to: string;
    amount: number;
    type: CreditTransaction['type'];
    taskId?: string;
  }): CreditTransaction {
    const tx: CreditTransaction = {
      txId: randomUUID(),
      from: params.from,
      to: params.to,
      amount: params.amount,
      type: params.type,
      taskId: params.taskId,
      timestamp: new Date(),
    };

    this.transactions.push(tx);

    // 更新账户交易记录
    const fromAccount = this.accounts.get(params.from);
    const toAccount = this.accounts.get(params.to);
    if (fromAccount) fromAccount.transactions.push(tx);
    if (toAccount && params.from !== params.to) toAccount.transactions.push(tx);

    return tx;
  }

  // ============================================================
  // 查询方法
  // ============================================================

  // 获取所有账户
  getAllAccounts(): CreditAccount[] {
    return Array.from(this.accounts.values());
  }

  // 获取排行榜
  getLeaderboard(limit: number = 10): Array<{ nodeId: string; balance: number; earned: number }> {
    return this.getAllAccounts()
      .sort((a, b) => b.balance - a.balance)
      .slice(0, limit)
      .map(a => ({ nodeId: a.nodeId, balance: a.balance, earned: a.earned }));
  }

  // 获取交易历史
  getTransactions(nodeId?: string, limit?: number): CreditTransaction[] {
    let txs = nodeId
      ? this.transactions.filter(tx => tx.from === nodeId || tx.to === nodeId)
      : this.transactions;

    txs = txs.sort((a, b) => b.timestamp.getTime() - a.timestamp.getTime());

    return limit ? txs.slice(0, limit) : txs;
  }

  // 获取统计
  getStats(): {
    totalAccounts: number;
    totalCreditsInCirculation: number;
    totalTransactions: number;
    avgBalance: number;
  } {
    const accounts = this.getAllAccounts();
    const totalCredits = accounts.reduce((sum, a) => sum + a.balance, 0);

    return {
      totalAccounts: accounts.length,
      totalCreditsInCirculation: totalCredits,
      totalTransactions: this.transactions.length,
      avgBalance: accounts.length > 0 ? totalCredits / accounts.length : 0,
    };
  }

  // ============================================================
  // 序列化
  // ============================================================

  toJSON(): { accounts: CreditAccount[]; transactions: CreditTransaction[] } {
    return {
      accounts: this.getAllAccounts(),
      transactions: this.transactions,
    };
  }

  static fromJSON(
    data: { accounts: CreditAccount[]; transactions: CreditTransaction[] },
    config?: Partial<HiveConfig>
  ): CreditLedger {
    const ledger = new CreditLedger(config);

    for (const account of data.accounts) {
      ledger.accounts.set(account.nodeId, {
        ...account,
        transactions: account.transactions.map(tx => ({
          ...tx,
          timestamp: new Date(tx.timestamp),
        })),
      });
    }

    ledger.transactions.push(...data.transactions.map(tx => ({
      ...tx,
      timestamp: new Date(tx.timestamp),
    })));

    return ledger;
  }
}

// ============================================================
// 积分激励策略
// ============================================================

export class IncentiveStrategy {
  constructor(private config: HiveConfig['creditSettings']) {}

  // 计算任务奖励
  calculateTaskReward(params: {
    baseDifficulty: number;      // 1-10
    completionTimeMs: number;
    expectedTimeMs: number;
    successRate: number;
  }): number {
    const { baseDifficulty, completionTimeMs, expectedTimeMs, successRate } = params;

    // 基础奖励
    let reward = this.config.taskBaseReward * (baseDifficulty / 5);

    // 时间奖励/惩罚
    if (completionTimeMs < expectedTimeMs * 0.8) {
      reward *= 1.2; // 提前20%以上完成，奖励20%
    } else if (completionTimeMs > expectedTimeMs * 1.5) {
      reward *= 0.8; // 超时50%以上，扣减20%
    }

    // 成功率加成
    if (successRate > 0.95) {
      reward *= 1.1;
    }

    return Math.floor(reward);
  }

  // 计算惩罚
  calculatePenalty(params: {
    baseReward: number;
    failureReason: 'timeout' | 'error' | 'rejected';
  }): number {
    const { baseReward, failureReason } = params;

    const penaltyRates: Record<string, number> = {
      timeout: this.config.penaltyRate * 0.5,   // 超时：50%惩罚率
      error: this.config.penaltyRate,            // 错误：100%惩罚率
      rejected: this.config.penaltyRate * 1.5,   // 被拒：150%惩罚率
    };

    return Math.floor(baseReward * penaltyRates[failureReason]);
  }

  // 计算活跃度奖励
  calculateActivityBonus(params: {
    tasksCompletedToday: number;
    consecutiveDays: number;
  }): number {
    const { tasksCompletedToday, consecutiveDays } = params;

    // 每日任务奖励
    const dailyBonus = Math.min(tasksCompletedToday, 10) * 2;

    // 连续活跃奖励
    const streakBonus = Math.min(consecutiveDays, 30) * 1;

    return dailyBonus + streakBonus;
  }
}
