/**
 * Solar Ontology Scheduler
 * 定时任务 - 定期反思、归纳、清理
 */

import { Database } from "bun:sqlite";
import { getOntologyReflector } from "./reflection";
import { getOntologyTimeline } from "./timeline";
import { OntologyManager, getOntologyManager } from "./manager";

export interface ScheduledTask {
  task_id: string;
  task_type: "reflection" | "consolidation" | "cleanup" | "snapshot";
  interval: "hourly" | "daily" | "weekly";
  last_run?: string;
  next_run: string;
  enabled: boolean;
}

export class OntologyScheduler {
  private db: Database;
  private tasks: Map<string, NodeJS.Timeout> = new Map();
  private running = false;

  constructor(db: Database) {
    this.db = db;
    this.initializeTasks();
  }

  private initializeTasks(): void {
    // 确保任务表存在
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS ont_scheduled_tasks (
        task_id TEXT PRIMARY KEY,
        task_type TEXT NOT NULL,
        interval_type TEXT NOT NULL,
        interval_ms INTEGER NOT NULL,
        last_run DATETIME,
        next_run DATETIME,
        enabled BOOLEAN DEFAULT 1,
        config JSON
      );

      -- 默认任务
      INSERT OR IGNORE INTO ont_scheduled_tasks (task_id, task_type, interval_type, interval_ms, next_run)
      VALUES
        ('daily_reflection', 'reflection', 'daily', 86400000, datetime('now', '+1 day', 'start of day', '+3 hours')),
        ('weekly_reflection', 'reflection', 'weekly', 604800000, datetime('now', 'weekday 0', '+3 hours')),
        ('hourly_consolidation', 'consolidation', 'hourly', 3600000, datetime('now', '+1 hour')),
        ('daily_snapshot', 'snapshot', 'daily', 86400000, datetime('now', '+1 day', 'start of day')),
        ('weekly_cleanup', 'cleanup', 'weekly', 604800000, datetime('now', 'weekday 0'));
    `);
  }

  /**
   * 启动调度器
   */
  start(): void {
    if (this.running) return;
    this.running = true;

    console.log("[OntologyScheduler] 启动定时任务调度器");

    // 获取所有启用的任务
    const tasks = this.db
      .query("SELECT * FROM ont_scheduled_tasks WHERE enabled = 1")
      .all() as any[];

    for (const task of tasks) {
      this.scheduleTask(task);
    }
  }

  /**
   * 停止调度器
   */
  stop(): void {
    this.running = false;
    for (const [taskId, timer] of this.tasks) {
      clearTimeout(timer);
      console.log(`[OntologyScheduler] 停止任务: ${taskId}`);
    }
    this.tasks.clear();
  }

  /**
   * 调度单个任务
   */
  private scheduleTask(task: any): void {
    const now = Date.now();
    const nextRun = new Date(task.next_run).getTime();
    const delay = Math.max(0, nextRun - now);

    const timer = setTimeout(async () => {
      await this.executeTask(task);
      // 重新调度
      if (this.running) {
        this.updateNextRun(task.task_id, task.interval_ms);
        const updatedTask = this.getTask(task.task_id);
        if (updatedTask) {
          this.scheduleTask(updatedTask);
        }
      }
    }, delay);

    this.tasks.set(task.task_id, timer);
    console.log(`[OntologyScheduler] 任务 ${task.task_id} 将在 ${Math.round(delay / 1000 / 60)} 分钟后执行`);
  }

  /**
   * 执行任务
   */
  private async executeTask(task: any): Promise<void> {
    console.log(`[OntologyScheduler] 执行任务: ${task.task_id}`);

    const startTime = Date.now();

    try {
      switch (task.task_type) {
        case "reflection":
          await this.executeReflection(task);
          break;
        case "consolidation":
          await this.executeConsolidation(task);
          break;
        case "cleanup":
          await this.executeCleanup(task);
          break;
        case "snapshot":
          await this.executeSnapshot(task);
          break;
      }

      // 记录执行
      this.db.run(
        `
        UPDATE ont_scheduled_tasks
        SET last_run = CURRENT_TIMESTAMP
        WHERE task_id = ?
        `,
        [task.task_id]
      );

      const duration = Date.now() - startTime;
      console.log(`[OntologyScheduler] 任务 ${task.task_id} 完成，耗时 ${duration}ms`);
    } catch (error) {
      console.error(`[OntologyScheduler] 任务 ${task.task_id} 失败:`, error);
    }
  }

  /**
   * 执行反思任务
   */
  private async executeReflection(task: any): Promise<void> {
    const reflector = getOntologyReflector(this.db);

    if (task.interval_type === "daily") {
      await reflector.dailyReflection();
    } else if (task.interval_type === "weekly") {
      await reflector.weeklyReflection();
    }
  }

  /**
   * 执行归纳任务
   */
  private async executeConsolidation(task: any): Promise<void> {
    // 归纳最近的记忆
    // 1. 合并相似的语义记忆
    await this.consolidateSemanticMemories();

    // 2. 更新程序记忆的成功率
    await this.updateProceduralStats();

    // 3. 衰减旧的情景记忆
    await this.decayEpisodicMemories();
  }

  /**
   * 执行清理任务
   */
  private async executeCleanup(task: any): Promise<void> {
    // 清理旧的快照 (保留最近 20 个)
    this.db.run(`
      DELETE FROM ont_snapshots
      WHERE version_number < (
        SELECT version_number FROM ont_snapshots
        ORDER BY version_number DESC
        LIMIT 1 OFFSET 20
      )
    `);

    // 清理旧的时间线记录 (保留最近 30 天)
    this.db.run(`
      DELETE FROM ont_preference_timeline
      WHERE recorded_at < datetime('now', '-30 days')
    `);

    // 清理旧的学习事件 (保留最近 30 天)
    this.db.run(`
      DELETE FROM ont_learning_events
      WHERE occurred_at < datetime('now', '-30 days')
    `);

    // 归档低重要性的情景记忆
    this.db.run(`
      UPDATE evo_memory_episodic
      SET importance = importance * 0.9
      WHERE occurred_at < datetime('now', '-30 days')
        AND importance < 0.3
    `);

    console.log("[OntologyScheduler] 清理完成");
  }

  /**
   * 执行快照任务
   */
  private async executeSnapshot(task: any): Promise<void> {
    const timeline = getOntologyTimeline(this.db);
    timeline.createSnapshot("auto", "每日自动快照");
  }

  /**
   * 合并相似语义记忆
   */
  private async consolidateSemanticMemories(): Promise<void> {
    // 查找相似记忆并合并置信度
    // 简化实现 - 实际应该使用向量相似度
    this.db.run(`
      UPDATE evo_memory_semantic
      SET confidence = MIN(1.0, confidence + 0.01),
          updated_at = CURRENT_TIMESTAMP
      WHERE access_count > 5
    `);
  }

  /**
   * 更新程序记忆统计
   */
  private async updateProceduralStats(): Promise<void> {
    // 更新成功率计算
    // 这里是简化实现
  }

  /**
   * 衰减情景记忆
   */
  private async decayEpisodicMemories(): Promise<void> {
    this.db.run(`
      UPDATE evo_memory_episodic
      SET importance = importance * (1 - decay_rate)
      WHERE occurred_at < datetime('now', '-7 days')
        AND recall_count = 0
    `);
  }

  private updateNextRun(taskId: string, intervalMs: number): void {
    this.db.run(
      `
      UPDATE ont_scheduled_tasks
      SET next_run = datetime('now', '+' || (? / 1000) || ' seconds')
      WHERE task_id = ?
      `,
      [intervalMs, taskId]
    );
  }

  private getTask(taskId: string): any {
    return this.db
      .query("SELECT * FROM ont_scheduled_tasks WHERE task_id = ?")
      .get([taskId]);
  }

  /**
   * 手动触发任务
   */
  async triggerTask(taskId: string): Promise<void> {
    const task = this.getTask(taskId);
    if (task) {
      await this.executeTask(task);
    }
  }

  /**
   * 获取任务状态
   */
  getTaskStatus(): any[] {
    return this.db.query("SELECT * FROM ont_scheduled_tasks").all();
  }
}

// ==================== Factory ====================

let _scheduler: OntologyScheduler | null = null;

export function getOntologyScheduler(db: Database): OntologyScheduler {
  if (!_scheduler) {
    _scheduler = new OntologyScheduler(db);
  }
  return _scheduler;
}

// ==================== CLI 测试 ====================

if (import.meta.main) {
  const db = new Database(process.env.SOLAR_DB_PATH || `${process.env.HOME}/.solar/db/solar.db`);
  const scheduler = getOntologyScheduler(db);

  console.log("任务状态:");
  console.table(scheduler.getTaskStatus());

  // 手动触发测试
  if (process.argv.includes("--trigger")) {
    const taskId = process.argv[process.argv.indexOf("--trigger") + 1];
    if (taskId) {
      console.log(`\n手动触发任务: ${taskId}`);
      scheduler.triggerTask(taskId).then(() => {
        console.log("任务完成");
        db.close();
      });
    }
  } else {
    db.close();
  }
}
