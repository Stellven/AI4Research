#!/usr/bin/env bun
/**
 * Solar 任务调度器
 * 根据优先级、Rate Limit、Token 成本智能调度任务
 */

import Database from 'bun:sqlite';

// ============================================================
// Types
// ============================================================

export type TaskPriority = 'high' | 'scheduled' | 'temporary';

export interface ScheduleDecision {
  should_execute: boolean;
  reason: string;
  estimated_wait_time_sec?: number;
  recommended_time?: string;
}

export interface RateLimitStatus {
  current_usage: number;
  limit: number;
  reset_time: Date;
  minutes_until_reset: number;
  usage_percent: number;
}

export interface TaskInfo {
  task_id: string;
  priority: TaskPriority;
  estimated_tokens: number;
  description: string;
}

// ============================================================
// Task Scheduler
// ============================================================

export class TaskScheduler {
  private db: Database;

  // Rate Limit 配置 (Sonnet 4.5)
  private readonly RATE_LIMIT = 1000000; // 1M tokens per window
  private readonly RESET_INTERVAL_MS = 300000; // 5 minutes

  // 优先级阈值
  private readonly HIGH_PRIORITY_THRESHOLD = 0.95; // 95% 也执行高优先级
  private readonly TEMP_PRIORITY_THRESHOLD = 0.70; // 70% 以下执行临时任务

  constructor(dbPath: string = process.env.SOLAR_DB_PATH || `${process.env.HOME}/.solar/db/solar.db`) {
    this.db = new Database(dbPath);
  }

  /**
   * 分析任务优先级
   */
  analyzePriority(message: string): TaskPriority {
    const msg = message.toLowerCase();

    // 高优先级口令
    const highKeywords = ['马上', '立即', '快点', '给我', '现在', '赶紧', '急'];
    if (highKeywords.some(kw => msg.includes(kw))) {
      return 'high';
    }

    // 常设级口令 (定期任务)
    const scheduledKeywords = ['定时', '定期', '经常看看', '每天', '每周', '定时检查'];
    if (scheduledKeywords.some(kw => msg.includes(kw))) {
      return 'scheduled';
    }

    // 临时级口令
    const tempKeywords = ['你看看', '看看', '分析下', '分析一下', '研究下', '帮我查'];
    if (tempKeywords.some(kw => msg.includes(kw))) {
      return 'temporary';
    }

    // 默认临时级
    return 'temporary';
  }

  /**
   * 决策是否执行任务
   */
  async decide(task: TaskInfo): Promise<ScheduleDecision> {
    const rateLimitStatus = this.getRateLimitStatus();

    // 1. 高优先级任务 - 几乎总是执行
    if (task.priority === 'high') {
      if (rateLimitStatus.usage_percent < this.HIGH_PRIORITY_THRESHOLD) {
        return {
          should_execute: true,
          reason: `高优先级任务，当前使用率 ${rateLimitStatus.usage_percent.toFixed(1)}%`
        };
      } else {
        return {
          should_execute: true,
          reason: `高优先级任务强制执行 (已用 ${rateLimitStatus.usage_percent.toFixed(1)}%，可能触发限流)`
        };
      }
    }

    // 2. 常设级任务 - 检查是否到执行时间
    if (task.priority === 'scheduled') {
      const shouldRun = this.checkScheduledTask(task.task_id);
      if (!shouldRun) {
        return {
          should_execute: false,
          reason: '常设任务未到执行时间',
          recommended_time: this.getNextScheduledTime(task.task_id)
        };
      }

      if (rateLimitStatus.usage_percent < 0.80) {
        return {
          should_execute: true,
          reason: `常设任务到期执行 (使用率 ${rateLimitStatus.usage_percent.toFixed(1)}%)`
        };
      } else {
        return {
          should_execute: false,
          reason: `常设任务延迟执行 (使用率过高 ${rateLimitStatus.usage_percent.toFixed(1)}%)`,
          estimated_wait_time_sec: rateLimitStatus.minutes_until_reset * 60
        };
      }
    }

    // 3. 临时级任务 - 智能决策
    return this.decideTemporaryTask(task, rateLimitStatus);
  }

  /**
   * 临时任务智能决策
   */
  private decideTemporaryTask(task: TaskInfo, rateLimit: RateLimitStatus): ScheduleDecision {
    const usagePercent = rateLimit.usage_percent;
    const minutesUntilReset = rateLimit.minutes_until_reset;
    const estimatedTokens = task.estimated_tokens;

    const projectedUsage = (rateLimit.current_usage + estimatedTokens) / this.RATE_LIMIT;
    const projectedPercent = projectedUsage * 100;

    if (usagePercent < this.TEMP_PRIORITY_THRESHOLD) {
      return {
        should_execute: true,
        reason: `使用率较低 (${usagePercent.toFixed(1)}%)，立即执行`
      };
    }

    if (usagePercent >= this.TEMP_PRIORITY_THRESHOLD && usagePercent < 0.85) {
      if (projectedPercent < 0.90) {
        return {
          should_execute: true,
          reason: `执行后预计使用率 ${projectedPercent.toFixed(1)}%，可接受`
        };
      } else {
        return {
          should_execute: false,
          reason: `执行后预计使用率 ${projectedPercent.toFixed(1)}%，建议等待`,
          estimated_wait_time_sec: minutesUntilReset * 60,
          recommended_time: this.formatResetTime(rateLimit.reset_time)
        };
      }
    }

    if (minutesUntilReset < 2) {
      return {
        should_execute: false,
        reason: `使用率高 (${usagePercent.toFixed(1)}%)，${minutesUntilReset.toFixed(0)}分钟后重置，建议等待`,
        estimated_wait_time_sec: minutesUntilReset * 60
      };
    } else {
      return {
        should_execute: false,
        reason: `使用率过高 (${usagePercent.toFixed(1)}%)，建议 ${minutesUntilReset.toFixed(0)} 分钟后重试`,
        estimated_wait_time_sec: minutesUntilReset * 60,
        recommended_time: this.formatResetTime(rateLimit.reset_time)
      };
    }
  }

  /**
   * 获取 Rate Limit 状态
   */
  getRateLimitStatus(): RateLimitStatus {
    const fiveMinutesAgo = new Date(Date.now() - this.RESET_INTERVAL_MS);

    const usage = this.db.prepare(`
      SELECT COALESCE(SUM(execution_tokens), 0) as total
      FROM bl_message_tasks
      WHERE created_at >= ?
    `).get(fiveMinutesAgo.toISOString()) as { total: number };

    const currentUsage = usage.total || 0;
    const usagePercent = (currentUsage / this.RATE_LIMIT) * 100;

    const now = Date.now();
    const windowStart = Math.floor(now / this.RESET_INTERVAL_MS) * this.RESET_INTERVAL_MS;
    const resetTime = new Date(windowStart + this.RESET_INTERVAL_MS);
    const minutesUntilReset = (resetTime.getTime() - now) / 60000;

    return {
      current_usage: currentUsage,
      limit: this.RATE_LIMIT,
      reset_time: resetTime,
      minutes_until_reset: minutesUntilReset,
      usage_percent: usagePercent
    };
  }

  private checkScheduledTask(taskId: string): boolean {
    const task = this.db.prepare(`
      SELECT last_executed, schedule_interval_sec
      FROM bl_scheduled_tasks
      WHERE task_id = ?
    `).get(taskId) as { last_executed: string; schedule_interval_sec: number } | undefined;

    if (!task) return true;

    const lastExecuted = new Date(task.last_executed);
    const intervalMs = task.schedule_interval_sec * 1000;
    const nextRunTime = lastExecuted.getTime() + intervalMs;

    return Date.now() >= nextRunTime;
  }

  private getNextScheduledTime(taskId: string): string {
    const task = this.db.prepare(`
      SELECT last_executed, schedule_interval_sec
      FROM bl_scheduled_tasks
      WHERE task_id = ?
    `).get(taskId) as { last_executed: string; schedule_interval_sec: number } | undefined;

    if (!task) return '立即';

    const lastExecuted = new Date(task.last_executed);
    const intervalMs = task.schedule_interval_sec * 1000;
    const nextRunTime = new Date(lastExecuted.getTime() + intervalMs);

    return this.formatResetTime(nextRunTime);
  }

  estimateTokens(message: string, intentAction: string): number {
    let tokens = 1000;

    const actionCosts: Record<string, number> = {
      'list_backlog': 500,
      'show_status': 300,
      'weather_query': 1000,
      'hn_fetch': 2000,
      'email_search': 3000,
      'file_search': 1500,
      'moltbook_check': 5000,
      'zhihu_analysis': 8000
    };

    tokens += actionCosts[intentAction] || 2000;
    tokens += Math.floor(message.length / 4);

    return tokens;
  }

  private formatResetTime(date: Date): string {
    const now = Date.now();
    const diff = date.getTime() - now;
    const minutes = Math.floor(diff / 60000);

    if (minutes < 1) return '马上';
    if (minutes < 60) return `${minutes} 分钟后`;

    const hours = Math.floor(minutes / 60);
    const mins = minutes % 60;
    return `${hours} 小时 ${mins} 分钟后`;
  }

  recordExecution(taskId: string, tokensUsed: number) {
    this.db.prepare(`
      UPDATE bl_message_tasks
      SET execution_tokens = ?
      WHERE task_id = ?
    `).run(tokensUsed, taskId);
  }

  createScheduledTask(name: string, description: string, action: string, intervalSeconds: number): string {
    const taskId = `scheduled-${Date.now()}`;
    this.db.prepare(`
      INSERT INTO bl_scheduled_tasks (
        task_id, name, description, action, schedule_interval_sec, enabled
      ) VALUES (?, ?, ?, ?, ?, 1)
    `).run(taskId, name, description, action, intervalSeconds);
    return taskId;
  }

  getPendingScheduledTasks(): Array<any> {
    return this.db.prepare(`
      SELECT *
      FROM bl_scheduled_tasks
      WHERE enabled = 1
        AND (last_executed IS NULL
             OR datetime(last_executed, '+' || schedule_interval_sec || ' seconds') <= datetime('now'))
      ORDER BY priority DESC, last_executed ASC
    `).all();
  }

  close() {
    this.db.close();
  }
}
