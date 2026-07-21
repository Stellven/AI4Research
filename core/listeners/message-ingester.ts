/**
 * Message Ingester - 消息入口
 * 去重 → 意图解析 → 优先级计算 → 入队
 */

import Database from 'bun:sqlite';
import { BacklogManager, type MessageTask } from '../backlog/backlog-manager';

export interface IncomingMessage {
  source: MessageTask['source'];
  sourceId: string;
  sender?: string;
  content: string;
  timestamp?: Date;
  metadata?: Record<string, any>;
}

export interface IngestResult {
  success: boolean;
  taskId?: number;
  duplicate?: boolean;
  error?: string;
}

export class MessageIngester {
  private manager: BacklogManager;
  private db: Database;

  constructor(dbPath: string = process.env.SOLAR_DB_PATH || `${process.env.HOME}/.solar/db/solar.db`) {
    this.manager = new BacklogManager(dbPath);
    this.db = new Database(dbPath);
  }

  /**
   * Ingest a single message
   */
  async ingest(message: IncomingMessage): Promise<IngestResult> {
    try {
      // Check for duplicate
      const existing = this.db.prepare(
        'SELECT task_id FROM bl_message_tasks WHERE source = ? AND source_id = ?'
      ).get(message.source, message.sourceId) as { task_id: string } | undefined;

      if (existing) {
        return { success: false, duplicate: true };
      }

      // Parse intent and triggers
      const { intent, priorityBoost } = this.parseIntent(message.content);

      // Calculate base priority from source
      const basePriority = this.getSourcePriority(message.source);
      const finalPriority = Math.min(100, basePriority + priorityBoost);

      // Estimate tokens
      const estimatedTokens = this.estimateTokens(message.content);

      // Generate task_id
      const taskId = `${message.source}-${message.sourceId}`;

      // Insert into queue
      const result = this.db.prepare(`
        INSERT INTO bl_message_tasks (
          task_id, source, source_id, sender, content, parsed_intent,
          priority, estimated_tokens, metadata
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
      `).run(
        taskId,
        message.source,
        message.sourceId,
        message.sender || 'unknown',
        message.content,
        intent,
        finalPriority.toString(),
        estimatedTokens,
        message.metadata ? JSON.stringify(message.metadata) : null
      );

      console.log(`[Ingester] Queued: ${message.source}/${message.sourceId} -> priority=${finalPriority}`);

      return {
        success: true,
        taskId: result.lastInsertRowid as number
      };

    } catch (error) {
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error'
      };
    }
  }

  /**
   * Batch ingest multiple messages
   */
  async ingestBatch(messages: IncomingMessage[]): Promise<IngestResult[]> {
    return Promise.all(messages.map(m => this.ingest(m)));
  }

  /**
   * Parse intent from content and match triggers
   */
  private parseIntent(content: string): { intent: string; priorityBoost: number } {
    const triggers = this.db.prepare(
      'SELECT * FROM bl_message_triggers WHERE enabled = 1'
    ).all() as any[];

    let intent = 'general';
    let priorityBoost = 0;
    const matchedTriggers: string[] = [];

    for (const trigger of triggers) {
      let matches = false;

      switch (trigger.pattern_type) {
        case 'keyword':
          matches = content.toLowerCase().includes(trigger.pattern.toLowerCase());
          break;
        case 'regex':
          try {
            matches = new RegExp(trigger.pattern, 'i').test(content);
          } catch {}
          break;
        case 'intent':
          // Future: semantic matching
          break;
      }

      if (matches) {
        matchedTriggers.push(trigger.trigger_id);
        priorityBoost = Math.max(priorityBoost, trigger.priority_boost);

        // Use most specific trigger as intent
        if (trigger.action_target.startsWith('/') || trigger.action_target.startsWith('@')) {
          intent = trigger.action_target;
        }
      }
    }

    return { intent, priorityBoost };
  }

  /**
   * Get base priority from source type
   */
  private getSourcePriority(source: MessageTask['source']): number {
    const priorities: Record<string, number> = {
      imessage: 60,   // Direct messages are high priority
      telegram: 55,   // Bot messages
      gmail: 50,      // Email is lower priority
      webhook: 45,    // API calls
      manual: 40      // Manual entries
    };
    return priorities[source] || 50;
  }

  /**
   * Estimate token usage for a message
   */
  private estimateTokens(content: string): number {
    // Rough estimation: ~4 chars per token, multiply by processing overhead
    const baseTokens = Math.ceil(content.length / 4);
    const overhead = 5; // System prompt, context, etc.
    return baseTokens * overhead;
  }

  /**
   * Get queue statistics
   */
  getQueueStats(): {
    pending: number;
    queued: number;
    processing: number;
    completed: number;
    failed: number;
  } {
    const result = this.db.prepare(`
      SELECT status, COUNT(*) as count
      FROM bl_message_tasks
      GROUP BY status
    `).all() as { status: string; count: number }[];

    const stats = {
      pending: 0,
      queued: 0,
      processing: 0,
      completed: 0,
      failed: 0
    };

    for (const row of result) {
      if (row.status in stats) {
        stats[row.status as keyof typeof stats] = row.count;
      }
    }

    return stats;
  }

  close(): void {
    this.db.close();
    this.manager.close();
  }
}

// CLI support
if (import.meta.main) {
  const ingester = new MessageIngester();
  const [cmd, ...args] = process.argv.slice(2);

  switch (cmd) {
    case 'ingest':
      // ingest <source> <source_id> <content> [sender]
      const [source, sourceId, content, sender] = args;
      if (!source || !sourceId || !content) {
        console.error('Usage: message-ingester.ts ingest <source> <source_id> <content> [sender]');
        process.exit(1);
      }
      ingester.ingest({
        source: source as MessageTask['source'],
        sourceId,
        content,
        sender
      }).then(result => {
        console.log(JSON.stringify(result, null, 2));
        ingester.close();
      });
      break;

    case 'stats':
      console.log(JSON.stringify(ingester.getQueueStats(), null, 2));
      ingester.close();
      break;

    default:
      console.log('Usage: message-ingester.ts <ingest|stats> [args]');
      ingester.close();
  }
}
