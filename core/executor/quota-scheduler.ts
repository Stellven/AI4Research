/**
 * Quota-Aware Scheduler - 配额感知调度器
 *
 * 调度算法:
 * - exceeded (超限): 0 并发 (暂停)
 * - critical (95%+): 1 并发 (最小)
 * - warning (80%+): 2 并发 (保守)
 * - ok: 4 并发 (正常)
 *
 * 执行前预留配额，执行后释放并结算
 */

import Database from 'bun:sqlite';
import { randomUUID } from 'crypto';

export interface QuotaStatus {
  periodType: string;
  model: string;
  maxTokens: number;
  usedTokens: number;
  reservedTokens: number;
  availableTokens: number;
  usagePct: number;
  status: 'exceeded' | 'critical' | 'warning' | 'ok';
}

export interface SchedulerDecision {
  maxConcurrent: number;
  quotaStatus: string;
  usagePct: number;
  availableTokens: number;
  currentProcessing: number;
  pendingTasks: number;
  canExecute: boolean;
}

export interface TaskExecution {
  taskId: number | string;
  reservationId?: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  startedAt?: Date;
  completedAt?: Date;
  actualTokens?: number;
  result?: any;
  error?: string;
}

export class QuotaScheduler {
  private db: Database;
  private executions: Map<number | string, TaskExecution> = new Map();
  private running: boolean = false;
  private schedulerInterval?: Timer;

  constructor(dbPath: string = process.env.SOLAR_DB_PATH || `${process.env.HOME}/.solar/db/solar.db`) {
    this.db = new Database(dbPath);
    this.db.exec('PRAGMA journal_mode = WAL');
  }

  /**
   * Get current quota status
   */
  getQuotaStatus(periodType: string = 'daily'): QuotaStatus | null {
    const row = this.db.prepare(`
      SELECT * FROM v_quota_realtime WHERE period_type = ?
    `).get(periodType) as any;

    if (!row) {
      // Return default if no quota configured
      return {
        periodType,
        model: 'claude',
        maxTokens: 1000000,
        usedTokens: 0,
        reservedTokens: 0,
        availableTokens: 1000000,
        usagePct: 0,
        status: 'ok'
      };
    }

    return {
      periodType: row.period_type,
      model: row.model,
      maxTokens: row.max_tokens,
      usedTokens: row.used_tokens,
      reservedTokens: row.reserved_tokens,
      availableTokens: row.max_tokens - row.used_tokens - row.reserved_tokens,
      usagePct: row.usage_pct,
      status: row.status
    };
  }

  /**
   * Get scheduler decision
   */
  getSchedulerDecision(): SchedulerDecision {
    const quota = this.getQuotaStatus();

    if (!quota) {
      return {
        maxConcurrent: 4,
        quotaStatus: 'ok',
        usagePct: 0,
        availableTokens: 1000000,
        currentProcessing: 0,
        pendingTasks: 0,
        canExecute: true
      };
    }

    // Calculate max concurrent based on quota status
    const maxConcurrentMap: Record<string, number> = {
      exceeded: 0,
      critical: 1,
      warning: 2,
      ok: 4
    };

    const currentProcessing = this.db.prepare(`
      SELECT COUNT(*) as count FROM bl_message_tasks WHERE status = 'processing'
    `).get() as { count: number };

    const pendingTasks = this.db.prepare(`
      SELECT COUNT(*) as count FROM bl_message_tasks WHERE status IN ('pending', 'queued')
    `).get() as { count: number };

    const maxConcurrent = maxConcurrentMap[quota.status] || 4;

    return {
      maxConcurrent,
      quotaStatus: quota.status,
      usagePct: quota.usagePct,
      availableTokens: quota.availableTokens,
      currentProcessing: currentProcessing.count,
      pendingTasks: pendingTasks.count,
      canExecute: quota.status !== 'exceeded' && currentProcessing.count < maxConcurrent
    };
  }

  /**
   * Reserve quota for a task
   */
  reserveQuota(taskId: number, estimatedTokens: number): string | null {
    const quota = this.getQuotaStatus();

    if (!quota || quota.availableTokens < estimatedTokens) {
      console.log(`[Scheduler] Cannot reserve ${estimatedTokens} tokens (available: ${quota?.availableTokens || 0})`);
      return null;
    }

    const reservationId = randomUUID();

    this.db.prepare(`
      INSERT INTO bl_quota_reservations (reservation_id, task_id, reserved_tokens)
      VALUES (?, ?, ?)
    `).run(reservationId, taskId, estimatedTokens);

    console.log(`[Scheduler] Reserved ${estimatedTokens} tokens for task ${taskId} (${reservationId})`);

    return reservationId;
  }

  /**
   * Release quota reservation
   */
  releaseReservation(reservationId: string, actualTokens?: number): void {
    // Release the reservation
    this.db.prepare(`
      UPDATE bl_quota_reservations
      SET status = 'released', released_at = CURRENT_TIMESTAMP
      WHERE reservation_id = ?
    `).run(reservationId);

    // Update actual usage if provided
    if (actualTokens !== undefined) {
      this.updateQuotaUsage(actualTokens);
    }

    console.log(`[Scheduler] Released reservation ${reservationId} (actual: ${actualTokens || 'unknown'})`);
  }

  /**
   * Update quota usage
   */
  updateQuotaUsage(tokens: number, model: string = 'claude'): void {
    const today = new Date().toISOString().split('T')[0];

    // Upsert daily usage
    this.db.prepare(`
      INSERT INTO bl_quota_usage (period_start, period_type, model, input_tokens, total_requests)
      VALUES (?, 'daily', ?, ?, 1)
      ON CONFLICT(period_start, period_type, model)
      DO UPDATE SET
        input_tokens = input_tokens + excluded.input_tokens,
        total_requests = total_requests + 1,
        updated_at = CURRENT_TIMESTAMP
    `).run(today, model, tokens);
  }

  /**
   * Get next tasks to execute
   */
  getNextTasks(limit?: number): Array<{
    id: number | string;
    content: string;
    priority: string;
    estimatedTokens: number;
    parsedIntent: string;
  }> {
    const decision = this.getSchedulerDecision();

    if (!decision.canExecute) {
      return [];
    }

    const availableSlots = decision.maxConcurrent - decision.currentProcessing;
    const maxTasks = limit ? Math.min(limit, availableSlots) : availableSlots;

    if (maxTasks <= 0) {
      return [];
    }

    const tasks = this.db.prepare(`
      SELECT task_id, content, priority, estimated_tokens, parsed_intent
      FROM bl_message_tasks
      WHERE status IN ('pending', 'queued')
      ORDER BY priority DESC, created_at ASC
      LIMIT ?
    `).all(maxTasks) as any[];

    return tasks.map(t => ({
      id: t.task_id,
      content: t.content,
      priority: t.priority,
      estimatedTokens: t.estimated_tokens || 1000,
      parsedIntent: t.parsed_intent
    }));
  }

  /**
   * Start processing a task
   */
  startTask(taskId: number | string): TaskExecution | null {
    const task = this.db.prepare(`
      SELECT * FROM bl_message_tasks WHERE task_id = ?
    `).get(taskId) as any;

    if (!task) {
      return null;
    }

    // Reserve quota
    const reservationId = this.reserveQuota(taskId, task.estimated_tokens || 1000);

    if (!reservationId) {
      // Mark as queued to try later
      this.db.prepare(`
        UPDATE bl_message_tasks SET status = 'queued' WHERE task_id = ?
      `).run(taskId);
      return null;
    }

    // Update status to processing
    this.db.prepare(`
      UPDATE bl_message_tasks SET status = 'processing' WHERE task_id = ?
    `).run(taskId);

    const execution: TaskExecution = {
      taskId,
      reservationId,
      status: 'running',
      startedAt: new Date()
    };

    this.executions.set(taskId, execution);

    console.log(`[Scheduler] Started task ${taskId}`);

    return execution;
  }

  /**
   * Complete a task
   */
  completeTask(taskId: number | string, result: any, actualTokens?: number): void {
    const execution = this.executions.get(taskId);

    // Release reservation
    if (execution?.reservationId) {
      this.releaseReservation(execution.reservationId, actualTokens);
    }

    // Update task status
    this.db.prepare(`
      UPDATE bl_message_tasks
      SET status = 'done', result = ?, execution_tokens = ?
      WHERE task_id = ?
    `).run(JSON.stringify(result), actualTokens, taskId);

    // Update execution tracking
    if (execution) {
      execution.status = 'completed';
      execution.completedAt = new Date();
      execution.result = result;
      execution.actualTokens = actualTokens;
    }

    this.executions.delete(taskId);

    console.log(`[Scheduler] Completed task ${taskId}`);
  }

  /**
   * Fail a task
   */
  failTask(taskId: number | string, error: string): void {
    const execution = this.executions.get(taskId);

    // Release reservation without updating usage
    if (execution?.reservationId) {
      this.db.prepare(`
        UPDATE bl_quota_reservations SET status = 'released', released_at = CURRENT_TIMESTAMP
        WHERE reservation_id = ?
      `).run(execution.reservationId);
    }

    // Check retry - table doesn't have retry columns, so skip retry logic
    const task = this.db.prepare(`
      SELECT task_id FROM bl_message_tasks WHERE task_id = ?
    `).get(taskId) as any;

    if (task) {
      // Mark as failed
      this.db.prepare(`
        UPDATE bl_message_tasks SET status = 'failed', error = ? WHERE task_id = ?
      `).run(error, taskId);
      console.log(`[Scheduler] Task ${taskId} failed: ${error}`);
    }

    this.executions.delete(taskId);
  }

  /**
   * Start scheduler loop
   */
  start(intervalMs: number = 5000): void {
    if (this.running) return;
    this.running = true;

    console.log('[Scheduler] Starting scheduler loop');

    this.schedulerInterval = setInterval(() => this.schedulerTick(), intervalMs);
  }

  /**
   * Stop scheduler
   */
  stop(): void {
    this.running = false;
    if (this.schedulerInterval) {
      clearInterval(this.schedulerInterval);
      this.schedulerInterval = undefined;
    }
    console.log('[Scheduler] Stopped');
  }

  /**
   * Scheduler tick - called periodically
   */
  private schedulerTick(): void {
    if (!this.running) return;

    const decision = this.getSchedulerDecision();

    // Expire old reservations (> 10 minutes)
    this.db.prepare(`
      UPDATE bl_quota_reservations
      SET status = 'expired'
      WHERE status = 'active'
      AND datetime(reserved_at, '+10 minutes') < datetime('now')
    `).run();

    // Log status periodically
    if (decision.pendingTasks > 0 || decision.currentProcessing > 0) {
      console.log(
        `[Scheduler] Status: ${decision.quotaStatus} | ` +
        `Usage: ${decision.usagePct.toFixed(1)}% | ` +
        `Processing: ${decision.currentProcessing}/${decision.maxConcurrent} | ` +
        `Pending: ${decision.pendingTasks}`
      );
    }
  }

  /**
   * Get scheduler stats
   */
  getStats(): {
    quota: QuotaStatus | null;
    decision: SchedulerDecision;
    activeExecutions: number;
  } {
    return {
      quota: this.getQuotaStatus(),
      decision: this.getSchedulerDecision(),
      activeExecutions: this.executions.size
    };
  }

  close(): void {
    this.stop();
    this.db.close();
  }
}

// CLI support
if (import.meta.main) {
  const scheduler = new QuotaScheduler();
  const [cmd, ...args] = process.argv.slice(2);

  switch (cmd) {
    case 'status':
      console.log(JSON.stringify(scheduler.getQuotaStatus(), null, 2));
      break;
    case 'decision':
      console.log(JSON.stringify(scheduler.getSchedulerDecision(), null, 2));
      break;
    case 'next':
      console.log(JSON.stringify(scheduler.getNextTasks(parseInt(args[0]) || 5), null, 2));
      break;
    case 'stats':
      console.log(JSON.stringify(scheduler.getStats(), null, 2));
      break;
    default:
      console.log('Usage: quota-scheduler.ts <status|decision|next|stats> [args]');
  }

  scheduler.close();
}
