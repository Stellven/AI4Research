/**
 * Solar Scheduler - 定时任务调度器
 */

type TaskCallback = () => Promise<void> | void;

interface ScheduledTask {
  id: string;
  type: "interval" | "timeout" | "daily";
  callback: TaskCallback;
  timer: Timer | null;
  lastRun: Date | null;
  runCount: number;
  isRunning: boolean;
}

export class Scheduler {
  private tasks: Map<string, ScheduledTask> = new Map();

  /**
   * 创建定时间隔任务
   */
  interval(id: string, ms: number, callback: TaskCallback): void {
    this.cancel(id);

    const task: ScheduledTask = {
      id,
      type: "interval",
      callback,
      timer: null,
      lastRun: null,
      runCount: 0,
      isRunning: false,
    };

    task.timer = setInterval(async () => {
      await this.runTask(task);
    }, ms);

    this.tasks.set(id, task);
  }

  /**
   * 创建一次性延迟任务
   */
  timeout(id: string, ms: number, callback: TaskCallback): void {
    this.cancel(id);

    const task: ScheduledTask = {
      id,
      type: "timeout",
      callback,
      timer: null,
      lastRun: null,
      runCount: 0,
      isRunning: false,
    };

    task.timer = setTimeout(async () => {
      await this.runTask(task);
      this.tasks.delete(id);
    }, ms);

    this.tasks.set(id, task);
  }

  /**
   * 创建每日定时任务
   */
  daily(
    id: string,
    hour: number,
    minute: number,
    callback: TaskCallback,
  ): void {
    this.cancel(id);

    const task: ScheduledTask = {
      id,
      type: "daily",
      callback,
      timer: null,
      lastRun: null,
      runCount: 0,
      isRunning: false,
    };

    const scheduleNext = () => {
      const now = new Date();
      const next = new Date(now);
      next.setHours(hour, minute, 0, 0);

      // 如果今天的时间已过，安排到明天
      if (next <= now) {
        next.setDate(next.getDate() + 1);
      }

      const delay = next.getTime() - now.getTime();

      task.timer = setTimeout(async () => {
        await this.runTask(task);
        scheduleNext(); // 安排下一次
      }, delay);
    };

    scheduleNext();
    this.tasks.set(id, task);
  }

  /**
   * 执行任务
   */
  private async runTask(task: ScheduledTask): Promise<void> {
    if (task.isRunning) {
      console.warn(`Task ${task.id} is still running, skipping`);
      return;
    }

    task.isRunning = true;
    task.lastRun = new Date();
    task.runCount++;

    try {
      await task.callback();
    } catch (e) {
      console.error(`Task ${task.id} error:`, e);
    } finally {
      task.isRunning = false;
    }
  }

  /**
   * 取消任务
   */
  cancel(id: string): boolean {
    const task = this.tasks.get(id);
    if (task) {
      if (task.timer) {
        clearInterval(task.timer);
        clearTimeout(task.timer);
      }
      this.tasks.delete(id);
      return true;
    }
    return false;
  }

  /**
   * 停止所有任务
   */
  stopAll(): void {
    for (const [id] of this.tasks) {
      this.cancel(id);
    }
  }

  /**
   * 获取任务状态
   */
  getStatus(id: string): ScheduledTask | undefined {
    return this.tasks.get(id);
  }

  /**
   * 获取所有任务
   */
  listTasks(): Array<{
    id: string;
    type: string;
    lastRun: Date | null;
    runCount: number;
  }> {
    return Array.from(this.tasks.values()).map((t) => ({
      id: t.id,
      type: t.type,
      lastRun: t.lastRun,
      runCount: t.runCount,
    }));
  }

  /**
   * 立即执行任务
   */
  async runNow(id: string): Promise<boolean> {
    const task = this.tasks.get(id);
    if (task) {
      await this.runTask(task);
      return true;
    }
    return false;
  }
}
