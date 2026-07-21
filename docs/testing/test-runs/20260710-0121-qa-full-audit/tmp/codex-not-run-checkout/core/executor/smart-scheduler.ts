#!/usr/bin/env bun
/**
 * Smart Scheduler - 配额感知智能调度器
 *
 * 功能:
 * 1. 配额检查 - 剩余配额/重置时间
 * 2. Token 估算 - 基于历史数据和任务类型
 * 3. 紧急度判断 - 自动评估 + 记录准确性
 * 4. 调度决策 - 立即执行/延迟/拒绝
 */

import Database from 'bun:sqlite';

const DB_PATH = process.env.SOLAR_DB_PATH || `${process.env.HOME}/.solar/db/solar.db`;

// 任务类型的 Token 估算 (基于历史平均值)
const TOKEN_ESTIMATES: Record<string, { input: number; output: number; variance: number }> = {
  // Shortcut 类 - 几乎不消耗 token
  'solar_get_weather': { input: 50, output: 100, variance: 0.1 },
  'solar_set_reminder': { input: 30, output: 50, variance: 0.1 },

  // Agent 类 - 消耗较多 token
  '@Coder': { input: 2000, output: 4000, variance: 0.5 },
  '@Researcher': { input: 1500, output: 3000, variance: 0.4 },
  '@Reviewer': { input: 1000, output: 2000, variance: 0.3 },
  '@Reporter': { input: 2000, output: 5000, variance: 0.6 },

  // 默认
  'default': { input: 500, output: 1000, variance: 0.5 },
};

// 紧急度级别
type UrgencyLevel = 'critical' | 'high' | 'normal' | 'low';

// 调度决策
type ScheduleDecision = 'execute_now' | 'delay_short' | 'delay_long' | 'defer_to_reset' | 'reject';

interface QuotaStatus {
  periodType: string;
  maxTokens: number;
  usedTokens: number;
  reservedTokens: number;
  remainingTokens: number;
  usagePct: number;
  status: 'ok' | 'warning' | 'critical' | 'exceeded';
  resetTime: Date;
  minutesToReset: number;
}

interface TaskEstimate {
  intent: string;
  estimatedInputTokens: number;
  estimatedOutputTokens: number;
  estimatedTotalTokens: number;
  confidence: number;  // 0-1，基于历史数据量
}

interface UrgencyAssessment {
  level: UrgencyLevel;
  score: number;       // 0-100
  reasons: string[];
  isAccurate?: boolean;  // 后续验证填充
}

interface ScheduleResult {
  decision: ScheduleDecision;
  executeAt?: Date;
  reason: string;
  quotaStatus: QuotaStatus;
  taskEstimate: TaskEstimate;
  urgency: UrgencyAssessment;
}

/**
 * 智能调度器
 */
export class SmartScheduler {
  private db: Database;

  constructor() {
    this.db = new Database(DB_PATH);
    this.ensureTables();
  }

  private ensureTables() {
    // 紧急度判断历史表 - 用于学习和校准
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS bl_urgency_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id INTEGER,
        predicted_level TEXT,
        predicted_score INTEGER,
        actual_level TEXT,
        is_accurate INTEGER,
        reasons TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
      )
    `);

    // Token 估算历史表 - 用于改进估算
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS bl_token_estimates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        intent TEXT NOT NULL,
        estimated_tokens INTEGER,
        actual_tokens INTEGER,
        error_pct REAL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
      )
    `);
  }

  /**
   * 获取当前配额状态
   */
  getQuotaStatus(periodType: string = 'daily'): QuotaStatus {
    const row = this.db.prepare(`
      SELECT * FROM v_quota_realtime WHERE period_type = ? LIMIT 1
    `).get(periodType) as any;

    if (!row) {
      // 默认配额 (如果没有配置)
      return {
        periodType,
        maxTokens: 100000,
        usedTokens: 0,
        reservedTokens: 0,
        remainingTokens: 100000,
        usagePct: 0,
        status: 'ok',
        resetTime: this.getNextResetTime(periodType),
        minutesToReset: this.getMinutesToReset(periodType),
      };
    }

    const remaining = row.max_tokens - row.used_tokens - row.reserved_tokens;

    return {
      periodType,
      maxTokens: row.max_tokens,
      usedTokens: row.used_tokens,
      reservedTokens: row.reserved_tokens,
      remainingTokens: Math.max(0, remaining),
      usagePct: row.usage_pct || 0,
      status: row.status,
      resetTime: this.getNextResetTime(periodType),
      minutesToReset: this.getMinutesToReset(periodType),
    };
  }

  /**
   * 估算任务 Token 消耗
   */
  estimateTokens(intent: string, content: string): TaskEstimate {
    // 获取基础估算
    const baseEstimate = TOKEN_ESTIMATES[intent] || TOKEN_ESTIMATES['default'];

    // 根据内容长度调整
    const contentTokens = Math.ceil(content.length / 4);
    const adjustedInput = baseEstimate.input + contentTokens;

    // 查询历史数据改进估算
    const history = this.db.prepare(`
      SELECT AVG(actual_tokens) as avg_tokens, COUNT(*) as count
      FROM bl_token_estimates
      WHERE intent = ? AND actual_tokens IS NOT NULL
      AND created_at > datetime('now', '-30 days')
    `).get(intent) as any;

    let estimatedTotal = adjustedInput + baseEstimate.output;
    let confidence = 0.5;  // 基础置信度

    if (history && history.count >= 5) {
      // 有足够历史数据，使用历史平均值
      estimatedTotal = Math.round(history.avg_tokens);
      confidence = Math.min(0.95, 0.5 + (history.count / 100));
    }

    return {
      intent,
      estimatedInputTokens: adjustedInput,
      estimatedOutputTokens: baseEstimate.output,
      estimatedTotalTokens: estimatedTotal,
      confidence,
    };
  }

  /**
   * 评估任务紧急度
   */
  assessUrgency(content: string, source: string, createdAt: Date): UrgencyAssessment {
    const reasons: string[] = [];
    let score = 50;  // 基础分数

    // 关键词检测
    if (/紧急|urgent|asap|马上|立刻|急|critical/i.test(content)) {
      score += 30;
      reasons.push('包含紧急关键词');
    }

    if (/重要|important|必须|务必/i.test(content)) {
      score += 15;
      reasons.push('包含重要关键词');
    }

    // 来源加权 - iMessage 通常更紧急
    if (source === 'imessage') {
      score += 10;
      reasons.push('来自 iMessage');
    }

    // 时间因素 - 等待时间越长优先级越高
    const waitMinutes = (Date.now() - createdAt.getTime()) / 60000;
    if (waitMinutes > 30) {
      score += 10;
      reasons.push(`等待 ${Math.round(waitMinutes)} 分钟`);
    }

    // 工作时间加权 (9-18点)
    const hour = new Date().getHours();
    if (hour >= 9 && hour <= 18) {
      score += 5;
      reasons.push('工作时间');
    }

    // 确定级别
    let level: UrgencyLevel;
    if (score >= 80) {
      level = 'critical';
    } else if (score >= 60) {
      level = 'high';
    } else if (score >= 40) {
      level = 'normal';
    } else {
      level = 'low';
    }

    return { level, score: Math.min(100, score), reasons };
  }

  /**
   * 做出调度决策
   */
  schedule(task: {
    id: number;
    intent: string;
    content: string;
    source: string;
    createdAt: Date;
  }): ScheduleResult {
    // 1. 获取配额状态
    const quotaStatus = this.getQuotaStatus('daily');

    // 2. 估算 Token 消耗
    const taskEstimate = this.estimateTokens(task.intent, task.content);

    // 3. 评估紧急度
    const urgency = this.assessUrgency(task.content, task.source, task.createdAt);

    // 4. 做出决策
    let decision: ScheduleDecision;
    let reason: string;
    let executeAt: Date | undefined;

    // Shortcut 类任务不消耗配额，直接执行
    if (task.intent.startsWith('solar_')) {
      decision = 'execute_now';
      reason = 'Shortcut 任务，不消耗 LLM 配额';
    }
    // 配额已超限
    else if (quotaStatus.status === 'exceeded') {
      if (urgency.level === 'critical') {
        decision = 'defer_to_reset';
        executeAt = quotaStatus.resetTime;
        reason = `配额已超限，critical 任务将在 ${quotaStatus.minutesToReset} 分钟后执行`;
      } else {
        decision = 'reject';
        reason = `配额已超限，非紧急任务将被拒绝`;
      }
    }
    // 配额临界
    else if (quotaStatus.status === 'critical') {
      if (urgency.level === 'critical' || urgency.level === 'high') {
        decision = 'execute_now';
        reason = '配额临界，但任务紧急，立即执行';
      } else {
        decision = 'delay_long';
        executeAt = new Date(Date.now() + 30 * 60000);  // 30分钟后
        reason = '配额临界，非紧急任务延迟 30 分钟';
      }
    }
    // 配额警告
    else if (quotaStatus.status === 'warning') {
      if (urgency.level === 'critical') {
        decision = 'execute_now';
        reason = '配额警告，但任务紧急，立即执行';
      } else if (urgency.level === 'high') {
        decision = 'delay_short';
        executeAt = new Date(Date.now() + 5 * 60000);  // 5分钟后
        reason = '配额警告，高优先级任务延迟 5 分钟';
      } else {
        decision = 'delay_long';
        executeAt = new Date(Date.now() + 15 * 60000);  // 15分钟后
        reason = '配额警告，普通任务延迟 15 分钟';
      }
    }
    // 剩余配额不足以执行此任务
    else if (quotaStatus.remainingTokens < taskEstimate.estimatedTotalTokens) {
      if (urgency.level === 'critical') {
        decision = 'execute_now';
        reason = '剩余配额可能不足，但任务紧急，尝试执行';
      } else {
        decision = 'defer_to_reset';
        executeAt = quotaStatus.resetTime;
        reason = `剩余配额不足 (需要 ${taskEstimate.estimatedTotalTokens}，剩余 ${quotaStatus.remainingTokens})`;
      }
    }
    // 配额充足
    else {
      decision = 'execute_now';
      reason = '配额充足，立即执行';
    }

    // 记录紧急度判断 (用于后续校准)
    this.recordUrgencyPrediction(task.id, urgency);

    return {
      decision,
      executeAt,
      reason,
      quotaStatus,
      taskEstimate,
      urgency,
    };
  }

  /**
   * 记录紧急度预测 (用于后续验证)
   */
  private recordUrgencyPrediction(taskId: number, urgency: UrgencyAssessment) {
    this.db.prepare(`
      INSERT INTO bl_urgency_history (task_id, predicted_level, predicted_score, reasons)
      VALUES (?, ?, ?, ?)
    `).run(taskId, urgency.level, urgency.score, JSON.stringify(urgency.reasons));
  }

  /**
   * 记录实际 Token 消耗 (用于改进估算)
   */
  recordActualTokens(intent: string, estimated: number, actual: number) {
    const errorPct = Math.abs(actual - estimated) / estimated * 100;
    this.db.prepare(`
      INSERT INTO bl_token_estimates (intent, estimated_tokens, actual_tokens, error_pct)
      VALUES (?, ?, ?, ?)
    `).run(intent, estimated, actual, errorPct);
  }

  /**
   * 验证紧急度判断准确性 (由系统分析任务调用)
   */
  validateUrgencyPrediction(taskId: number, actualLevel: UrgencyLevel): boolean {
    const prediction = this.db.prepare(`
      SELECT * FROM bl_urgency_history WHERE task_id = ? ORDER BY id DESC LIMIT 1
    `).get(taskId) as any;

    if (!prediction) return false;

    const isAccurate = prediction.predicted_level === actualLevel;

    this.db.prepare(`
      UPDATE bl_urgency_history
      SET actual_level = ?, is_accurate = ?
      WHERE id = ?
    `).run(actualLevel, isAccurate ? 1 : 0, prediction.id);

    return isAccurate;
  }

  /**
   * 获取下一个重置时间
   */
  private getNextResetTime(periodType: string): Date {
    const now = new Date();

    switch (periodType) {
      case 'hourly':
        return new Date(now.getFullYear(), now.getMonth(), now.getDate(), now.getHours() + 1, 0, 0);
      case 'daily':
        return new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1, 0, 0, 0);
      case 'monthly':
        return new Date(now.getFullYear(), now.getMonth() + 1, 1, 0, 0, 0);
      default:
        return new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1, 0, 0, 0);
    }
  }

  /**
   * 获取距离重置的分钟数
   */
  private getMinutesToReset(periodType: string): number {
    const resetTime = this.getNextResetTime(periodType);
    return Math.ceil((resetTime.getTime() - Date.now()) / 60000);
  }

  close() {
    this.db.close();
  }
}

// CLI 测试
if (import.meta.main) {
  const scheduler = new SmartScheduler();

  // 测试配额状态
  console.log('配额状态:');
  console.log(scheduler.getQuotaStatus());

  // 测试调度决策
  console.log('\n调度决策:');
  const result = scheduler.schedule({
    id: 1,
    intent: '@Researcher',
    content: '分析这个技术方案',
    source: 'imessage',
    createdAt: new Date(),
  });
  console.log(JSON.stringify(result, null, 2));

  scheduler.close();
}
