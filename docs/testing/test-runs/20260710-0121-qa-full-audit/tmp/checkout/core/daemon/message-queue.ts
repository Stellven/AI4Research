/**
 * Solar Message Queue - 消息队列
 * 收集系统消息，定时同步到 SQLite
 */

import type { StateManager, SolarQueries } from "../nerve/state-manager";

export interface Message {
  type: string; // 'hook', 'agent', 'workflow', 'plugin', 'error', 'system'
  source: string; // 来源组件
  level?: string; // 'debug', 'info', 'warn', 'error'
  content: any; // 消息内容
  timestamp?: string;
}

export class MessageQueue {
  private queue: Message[] = [];
  private state: StateManager;
  private queries: SolarQueries;
  private maxQueueSize = 1000;
  private batchSize = 100;

  constructor(state: StateManager, queries: SolarQueries) {
    this.state = state;
    this.queries = queries;
  }

  /**
   * 入队消息
   */
  async enqueue(msg: Message): Promise<void> {
    // 添加时间戳
    if (!msg.timestamp) {
      msg.timestamp = new Date().toISOString();
    }

    // 默认级别
    if (!msg.level) {
      msg.level = "info";
    }

    this.queue.push(msg);

    // 防止队列过大
    if (this.queue.length > this.maxQueueSize) {
      await this.sync();
    }
  }

  /**
   * 快捷方法 - 记录日志
   */
  log(
    type: string,
    source: string,
    content: any,
    level: string = "info",
  ): void {
    this.enqueue({ type, source, content, level });
  }

  /**
   * 同步到数据库
   */
  async sync(): Promise<number> {
    if (this.queue.length === 0) return 0;

    // 取出一批
    const batch = this.queue.splice(0, this.batchSize);

    // 批量写入
    const db = this.state.getDb();
    const stmt = db.prepare(`
      INSERT INTO messages (type, source, level, content, timestamp)
      VALUES (?, ?, ?, ?, ?)
    `);

    db.transaction(() => {
      for (const msg of batch) {
        stmt.run(
          msg.type,
          msg.source,
          msg.level || "info",
          JSON.stringify(msg.content),
          msg.timestamp || new Date().toISOString(),
        );
      }
    })();

    return batch.length;
  }

  /**
   * 刷新所有消息
   */
  async flush(): Promise<number> {
    let total = 0;
    while (this.queue.length > 0) {
      total += await this.sync();
    }
    return total;
  }

  /**
   * 获取队列大小
   */
  size(): number {
    return this.queue.length;
  }

  /**
   * 清空队列 (不写入数据库)
   */
  clear(): void {
    this.queue = [];
  }

  /**
   * 获取未处理的消息 (从数据库)
   */
  getUnprocessed(limit: number = 100): any[] {
    return this.queries.getUnprocessedMessages(limit);
  }

  /**
   * 标记消息已处理
   */
  markProcessed(ids: number[]): void {
    this.queries.markMessagesProcessed(ids);
  }

  /**
   * 处理消息 (从数据库读取并处理)
   */
  async processMessages(handler: (msg: any) => Promise<void>): Promise<number> {
    const messages = this.getUnprocessed();
    const processedIds: number[] = [];

    for (const msg of messages) {
      try {
        await handler(msg);
        processedIds.push(msg.id);
      } catch (e) {
        console.error(`Error processing message ${msg.id}:`, e);
      }
    }

    if (processedIds.length > 0) {
      this.markProcessed(processedIds);
    }

    return processedIds.length;
  }
}
