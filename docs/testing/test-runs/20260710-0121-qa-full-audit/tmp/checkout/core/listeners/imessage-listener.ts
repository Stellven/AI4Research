/**
 * iMessage Listener
 * 监听 Shortcut 转发的 JSON 文件
 *
 * 工作流程:
 * 1. Shortcut 收到 iMessage → 写入 JSON 到 ~/.solar/incoming/imessage/
 * 2. 本监听器轮询目录 → 读取 JSON → 发送到 Ingester → 删除文件
 */

import { watch } from 'fs';
import { readdir, readFile, unlink, mkdir } from 'fs/promises';
import { join } from 'path';
import { MessageIngester } from './message-ingester';

const INCOMING_DIR = `${process.env.HOME}/.solar/incoming/imessage`;
const POLL_INTERVAL = 2000; // 2 seconds
const PROCESSED_DIR = `${process.env.HOME}/.solar/processed/imessage`;

interface iMessagePayload {
  id: string;
  sender: string;
  text: string;
  timestamp?: string;
  conversation?: string;
  attachments?: string[];
}

export class iMessageListener {
  private ingester: MessageIngester;
  private running: boolean = false;
  private pollTimer?: Timer;

  constructor() {
    this.ingester = new MessageIngester();
  }

  async start(): Promise<void> {
    if (this.running) return;
    this.running = true;

    // Ensure directories exist
    await mkdir(INCOMING_DIR, { recursive: true });
    await mkdir(PROCESSED_DIR, { recursive: true });

    console.log(`[iMessage] Listening on ${INCOMING_DIR}`);

    // Initial scan
    await this.processDirectory();

    // Start polling
    this.pollTimer = setInterval(() => this.processDirectory(), POLL_INTERVAL);
  }

  stop(): void {
    this.running = false;
    if (this.pollTimer) {
      clearInterval(this.pollTimer);
      this.pollTimer = undefined;
    }
    this.ingester.close();
    console.log('[iMessage] Stopped');
  }

  private async processDirectory(): Promise<void> {
    if (!this.running) return;

    try {
      const files = await readdir(INCOMING_DIR);
      const jsonFiles = files.filter(f => f.endsWith('.json'));

      for (const file of jsonFiles) {
        await this.processFile(join(INCOMING_DIR, file));
      }
    } catch (error) {
      // Directory might not exist yet
      if ((error as any).code !== 'ENOENT') {
        console.error('[iMessage] Error scanning directory:', error);
      }
    }
  }

  private async processFile(filepath: string): Promise<void> {
    try {
      const content = await readFile(filepath, 'utf-8');
      const payload: iMessagePayload = JSON.parse(content);

      // Validate payload
      if (!payload.id || !payload.text) {
        console.warn(`[iMessage] Invalid payload in ${filepath}`);
        await unlink(filepath);
        return;
      }

      // Ingest message
      const result = await this.ingester.ingest({
        source: 'imessage',
        sourceId: payload.id,
        sender: payload.sender,
        content: payload.text,
        timestamp: payload.timestamp ? new Date(payload.timestamp) : undefined,
        metadata: {
          conversation: payload.conversation,
          attachments: payload.attachments
        }
      });

      if (result.success) {
        console.log(`[iMessage] Ingested: ${payload.id} from ${payload.sender}`);
      } else if (result.duplicate) {
        console.log(`[iMessage] Duplicate: ${payload.id}`);
      } else {
        console.error(`[iMessage] Failed to ingest: ${result.error}`);
      }

      // Delete processed file
      await unlink(filepath);

    } catch (error) {
      console.error(`[iMessage] Error processing ${filepath}:`, error);
      // Move to error directory or retry later
    }
  }
}

// CLI / standalone mode
if (import.meta.main) {
  const listener = new iMessageListener();

  process.on('SIGINT', () => {
    listener.stop();
    process.exit(0);
  });

  process.on('SIGTERM', () => {
    listener.stop();
    process.exit(0);
  });

  listener.start().then(() => {
    console.log('[iMessage] Listener started. Press Ctrl+C to stop.');
  });
}
